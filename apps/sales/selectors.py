from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    QuerySet,
    Sum,
)
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.orders.domain.enums import PaymentMethod
from apps.sales.domain.commands import SaleFilters
from apps.sales.domain.enums import CommissionKind, CommissionRule, RefundKind, SaleStatus
from apps.sales.domain.errors import SaleNotFound, StatementNotFound
from apps.sales.domain.payouts import (
    PAYOUT_THRESHOLD,
    CommissionStatus,
    DeliveryCreditKind,
    PayoutCalendar,
    StatementLineKind,
    StatementStatus,
)
from apps.sales.domain.read_models import (
    CommissionEntryView,
    CommissionSummary,
    MonthlyCommission,
    PayoutView,
    PersonRef,
    RefundView,
    SalesStats,
    SaleView,
    SellerPerformance,
    StatementLineView,
    StatementView,
)
from apps.sales.domain.rules import ZERO, cents, profit_for
from apps.sales.models import CommissionEntry, DeliveryCredit, Payout, PayoutStatement, Sale
from core.domain.actor import Actor

MONEY = DecimalField(max_digits=14, decimal_places=2)


def scoped_sales(actor: Actor) -> QuerySet[Sale]:
    if actor.is_staff:
        return Sale.objects.all()
    if actor.is_backoffice:
        return Sale.objects.filter(seller_id=actor.user_id)
    return Sale.objects.none()


class SaleSelector:
    def __init__(self, *, clock: Callable[[], datetime] = timezone.now) -> None:
        self._clock = clock

    def page(
        self, actor: Actor, filters: SaleFilters, *, offset: int, limit: int
    ) -> tuple[list[SaleView], int, SalesStats]:
        sales = self._filtered(scoped_sales(actor), filters)
        page = list(
            sales.select_related("seller", "buyer", "order").order_by("-sold_at", "-pk")[
                offset : offset + limit
            ]
        )
        return [to_sale_view(sale) for sale in page], sales.count(), _stats(sales)

    def detail(self, actor: Actor, sale_id: int) -> SaleView:
        sale = (
            scoped_sales(actor)
            .select_related("seller", "buyer", "order")
            .prefetch_related("refunds__by")
            .filter(pk=sale_id)
            .first()
        )
        if sale is None:
            raise SaleNotFound
        return to_sale_view(sale, with_refunds=True)

    def visible(self, actor: Actor, sale_id: int) -> bool:
        return scoped_sales(actor).filter(pk=sale_id).exists()

    def converted_item_ids(self, item_ids: Iterable[int]) -> set[int]:
        return set(
            Sale.objects.filter(order_item_id__in=list(item_ids)).values_list(
                "order_item_id", flat=True
            )
        )

    def _filtered(self, sales: QuerySet[Sale], filters: SaleFilters) -> QuerySet[Sale]:
        if filters.period is not None:
            sales = sales.filter(sold_at__gte=self._clock() - timedelta(days=filters.period.days))
        if filters.date_from is not None:
            sales = sales.filter(sold_at__gte=_start(filters.date_from))
        if filters.date_to is not None:
            sales = sales.filter(sold_at__lte=_end(filters.date_to))
        if filters.payment_method is not None:
            sales = sales.filter(payment_method=filters.payment_method.value)
        if filters.seller_id is not None:
            sales = sales.filter(seller_id=filters.seller_id)
        if filters.product_id is not None:
            sales = sales.filter(product_id=filters.product_id)
        if filters.status is not None:
            sales = sales.filter(status=filters.status.value)
        if filters.search:
            term = filters.search.strip()
            sales = sales.filter(
                Q(product_name__icontains=term)
                | Q(sold_to__icontains=term)
                | Q(order__number__icontains=term)
                | Q(seller__first_name__icontains=term)
                | Q(seller__last_name__icontains=term)
            )
        return sales


class CommissionSelector:
    def __init__(self, *, clock: Callable[[], datetime] = timezone.now) -> None:
        self._clock = clock

    def summary(self, reseller: PersonRef) -> CommissionSummary:
        now = self._clock()
        entries = CommissionEntry.objects.filter(reseller_id=reseller.id)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        validated = _sum(entries.filter(available_at__lte=now), "amount")
        fees = _sum(
            DeliveryCredit.objects.filter(reseller_id=reseller.id, available_at__lte=now), "amount"
        )
        paid_total = _sum(Payout.objects.filter(reseller_id=reseller.id), "amount")
        return CommissionSummary(
            reseller=reseller,
            earned_this_month=_sum(entries.filter(created_at__gte=month_start), "amount"),
            earned_total=_sum(entries, "amount"),
            paid_total=paid_total,
            due=validated + fees - paid_total,
            pending=_sum(entries.filter(available_at__gt=now), "amount"),
            validated=validated,
            delivery_fees=fees,
            next_payout_date=PayoutCalendar().next(timezone.localdate(now)),
            payout_threshold=PAYOUT_THRESHOLD,
        )

    def entries(
        self, reseller_id: int, *, offset: int, limit: int
    ) -> tuple[list[CommissionEntryView], int]:
        entries = CommissionEntry.objects.filter(reseller_id=reseller_id)
        page = list(
            entries.select_related("statement").order_by("-created_at", "-pk")[
                offset : offset + limit
            ]
        )
        nets = _sale_nets(entry.sale_id for entry in page)
        now = self._clock()
        return [_entry_view(entry, nets, now) for entry in page], entries.count()

    def monthly(self, reseller_id: int, *, months: int = 6) -> list[MonthlyCommission]:
        now = self._clock()
        starts = _month_starts(now, months)
        earned = _by_month(
            CommissionEntry.objects.filter(reseller_id=reseller_id), "created_at", starts[0]
        )
        paid = _by_month(Payout.objects.filter(reseller_id=reseller_id), "paid_at", starts[0])
        return [
            MonthlyCommission(
                month=start.strftime("%Y-%m"),
                earned=earned.get(start.strftime("%Y-%m"), ZERO),
                paid=paid.get(start.strftime("%Y-%m"), ZERO),
            )
            for start in starts
        ]


class PayoutSelector:
    def page(
        self, reseller_id: int | None, *, offset: int, limit: int
    ) -> tuple[list[PayoutView], int]:
        payouts = Payout.objects.select_related("reseller", "paid_by", "statement")
        if reseller_id is not None:
            payouts = payouts.filter(reseller_id=reseller_id)
        page = payouts.order_by("-paid_at", "-pk")[offset : offset + limit]
        return [to_payout_view(payout) for payout in page], payouts.count()

    def one(self, payout_id: int) -> PayoutView:
        return to_payout_view(
            Payout.objects.select_related("reseller", "paid_by", "statement").get(pk=payout_id)
        )


class StatementSelector:
    def page(
        self,
        reseller_id: int | None,
        status: StatementStatus | None,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[StatementView], int]:
        statements = PayoutStatement.objects.select_related("reseller", "payout")
        if reseller_id is not None:
            statements = statements.filter(reseller_id=reseller_id)
        if status is not None:
            statements = statements.filter(status=status.value)
        page = statements.order_by("-payout_date", "-pk")[offset : offset + limit]
        return [_statement_view(statement) for statement in page], statements.count()

    # a reseller only reaches their own statements
    def detail(self, statement_id: int, *, reseller_id: int | None = None) -> StatementView:
        statements = PayoutStatement.objects.select_related("reseller", "payout")
        if reseller_id is not None:
            statements = statements.filter(reseller_id=reseller_id)
        statement = statements.filter(pk=statement_id).first()
        if statement is None:
            raise StatementNotFound
        return _statement_view(statement, lines=_statement_lines(statement))


def to_sale_view(sale: Sale, *, with_refunds: bool = False) -> SaleView:
    return SaleView(
        id=sale.pk,
        product_id=sale.product_id,
        variant_id=sale.variant_id,
        product_name=sale.product_name,
        variant_label=sale.variant_label,
        product_image=sale.product_image,
        quantity=sale.quantity,
        unit_price=sale.unit_price,
        unit_cost=sale.unit_cost,
        total=sale.total,
        refunded_amount=sale.refunded_amount,
        profit=_net_profit(sale),
        payment_method=PaymentMethod(sale.payment_method),
        status=SaleStatus(sale.status),
        sold_to=sale.sold_to,
        buyer=_person(sale.buyer) if sale.buyer else None,
        seller=_person(sale.seller),
        order_id=sale.order_id,
        order_number=sale.order.number if sale.order else None,
        sold_at=sale.sold_at,
        recorded_at=sale.recorded_at,
        refunds=tuple(
            RefundView(
                id=refund.pk,
                kind=RefundKind(refund.kind),
                amount=refund.amount,
                reason=refund.reason,
                by=_person(refund.by) if refund.by else None,
                created_at=refund.created_at,
            )
            for refund in sale.refunds.all()
        )
        if with_refunds
        else (),
    )


def to_payout_view(payout: Payout) -> PayoutView:
    statement: PayoutStatement | None = getattr(payout, "statement", None)
    return PayoutView(
        id=payout.pk,
        reseller=_person(payout.reseller),
        amount=payout.amount,
        note=payout.note,
        paid_at=payout.paid_at,
        paid_by=_person(payout.paid_by) if payout.paid_by else None,
        statement_id=statement.pk if statement else None,
        payout_date=statement.payout_date if statement else None,
    )


def _statement_view(
    statement: PayoutStatement, *, lines: tuple[StatementLineView, ...] = ()
) -> StatementView:
    return StatementView(
        id=statement.pk,
        reseller=_person(statement.reseller),
        payout_date=statement.payout_date,
        status=StatementStatus(statement.status),
        commissions=statement.commissions,
        delivery_fees=statement.delivery_fees,
        total=statement.total,
        prepared_at=statement.prepared_at,
        paid_at=statement.payout.paid_at if statement.payout else None,
        payout_id=statement.payout_id,
        lines=lines,
    )


def _statement_lines(statement: PayoutStatement) -> tuple[StatementLineView, ...]:
    entries = (
        CommissionEntry.objects.filter(statement=statement)
        .select_related("sale__order")
        .order_by("available_at", "pk")
    )
    credits = DeliveryCredit.objects.filter(statement=statement).order_by("available_at", "pk")
    lines = [_commission_line(entry) for entry in entries]
    lines.extend(
        StatementLineView(
            kind=StatementLineKind.DELIVERY_FEE
            if credit.kind == DeliveryCreditKind.CREDIT.value
            else StatementLineKind.DELIVERY_FEE_REVERSAL,
            label=f"{credit.note or 'Frais de livraison'} — commande {credit.order_number}",
            sale_id=None,
            order_number=credit.order_number,
            base_amount=None,
            amount=credit.amount,
            at=credit.available_at,
        )
        for credit in credits
    )
    return tuple(lines)


def _commission_line(entry: CommissionEntry) -> StatementLineView:
    sale = entry.sale
    earned = entry.kind == CommissionKind.EARNED.value
    product = sale.product_name if sale else "vente supprimée"
    return StatementLineView(
        kind=StatementLineKind.COMMISSION if earned else StatementLineKind.REVERSAL,
        label=f"Commission — {product}" if earned else f"{entry.note or 'Annulation'} — {product}",
        sale_id=entry.sale_id,
        order_number=sale.order.number if sale and sale.order else None,
        base_amount=entry.base_amount,
        amount=entry.amount,
        at=entry.available_at,
    )


def _sale_nets(sale_ids: Iterable[int | None]) -> dict[int, Decimal]:
    ids = {sale_id for sale_id in sale_ids if sale_id is not None}
    rows = (
        CommissionEntry.objects.filter(sale_id__in=ids)
        .values("sale_id")
        .annotate(total=Sum("amount"))
    )
    return {row["sale_id"]: Decimal(row["total"] or 0) for row in rows}


# cancelled once its sale is gone or fully reversed; paid once its statement is paid
def commission_status(
    entry: CommissionEntry, nets: dict[int, Decimal], now: datetime
) -> CommissionStatus:
    if entry.sale_id is None or nets.get(entry.sale_id, ZERO) <= ZERO:
        return CommissionStatus.CANCELLED
    statement = entry.statement
    if statement is not None and statement.status == StatementStatus.PAID.value:
        return CommissionStatus.PAID
    return CommissionStatus.PENDING if entry.available_at > now else CommissionStatus.VALIDATED


def _stats(sales: QuerySet[Sale]) -> SalesStats:
    gross = ExpressionWrapper(F("unit_price") * F("quantity"), output_field=MONEY)
    margin = ExpressionWrapper(
        (F("unit_price") - F("unit_cost")) * F("quantity"), output_field=MONEY
    )
    totals = sales.aggregate(
        gross=Coalesce(Sum(gross), ZERO, output_field=MONEY),
        refunded=Coalesce(Sum("refunded_amount"), ZERO, output_field=MONEY),
        margin=Coalesce(Sum(margin, filter=Q(unit_cost__isnull=False)), ZERO, output_field=MONEY),
        units=Coalesce(Sum("quantity", filter=~Q(status=SaleStatus.RETURNED.value)), 0),
        count=Count("pk", filter=~Q(status=SaleStatus.RETURNED.value)),
    )
    revenue = cents(totals["gross"] - totals["refunded"])
    count = int(totals["count"])
    return SalesStats(
        revenue=revenue,
        profit=cents(totals["margin"] - totals["refunded"]),
        count=count,
        units=int(totals["units"]),
        average=cents(revenue / count) if count else ZERO,
    )


def _net_profit(sale: Sale) -> Decimal | None:
    profit = profit_for(sale.unit_price, sale.unit_cost, sale.quantity)
    return None if profit is None else cents(profit - sale.refunded_amount)


def _entry_view(
    entry: CommissionEntry, nets: dict[int, Decimal], now: datetime
) -> CommissionEntryView:
    return CommissionEntryView(
        id=entry.pk,
        kind=CommissionKind(entry.kind),
        sale_id=entry.sale_id,
        rule=CommissionRule(entry.rule),
        base_amount=entry.base_amount,
        amount=entry.amount,
        created_at=entry.created_at,
        status=commission_status(entry, nets, now),
        available_at=entry.available_at,
        statement_id=entry.statement_id,
    )


def _person(user: object) -> PersonRef:
    first = getattr(user, "first_name", "")
    last = getattr(user, "last_name", "")
    return PersonRef(
        id=int(getattr(user, "pk", 0)),
        name=f"{first} {last}".strip() or str(getattr(user, "email", "")),
    )


def _sum(
    queryset: QuerySet[CommissionEntry] | QuerySet[Payout] | QuerySet[DeliveryCredit], field: str
) -> Decimal:
    total = queryset.aggregate(total=Sum(field))["total"]
    return cents(Decimal(total or 0))


def _by_month(
    queryset: QuerySet[CommissionEntry] | QuerySet[Payout], field: str, since: datetime
) -> dict[str, Decimal]:
    rows = (
        queryset.filter(**{f"{field}__gte": since})
        .annotate(month=TruncMonth(field))
        .values("month")
        .annotate(total=Sum("amount"))
    )
    return {row["month"].strftime("%Y-%m"): cents(Decimal(row["total"])) for row in rows}


def _month_starts(now: datetime, months: int) -> list[datetime]:
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    starts = []
    for _ in range(months):
        starts.append(first)
        first = (first - timedelta(days=1)).replace(day=1)
    return list(reversed(starts))


def _start(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def _end(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.max))


def seller_performance(
    seller_ids: Iterable[int], *, since: datetime | None = None
) -> dict[int, SellerPerformance]:
    ids = list(seller_ids)
    sales = Sale.objects.filter(seller_id__in=ids).exclude(status=SaleStatus.RETURNED.value)
    if since is not None:
        sales = sales.filter(sold_at__gte=since)
    net = ExpressionWrapper(
        F("unit_price") * F("quantity") - F("refunded_amount"), output_field=MONEY
    )
    rows = sales.values("seller_id").annotate(count=Count("pk"), revenue=Sum(net))
    counts = {row["seller_id"]: int(row["count"]) for row in rows}
    revenue = {row["seller_id"]: Decimal(row["revenue"] or 0) for row in rows}
    entries = CommissionEntry.objects.filter(reseller_id__in=ids)
    now = timezone.now()
    earned = _totals_by_reseller(entries)
    validated = _totals_by_reseller(entries.filter(available_at__lte=now))
    fees = _totals_by_reseller(
        DeliveryCredit.objects.filter(reseller_id__in=ids, available_at__lte=now)
    )
    paid = _totals_by_reseller(Payout.objects.filter(reseller_id__in=ids))
    return {
        seller_id: SellerPerformance(
            seller_id=seller_id,
            sales_count=counts.get(seller_id, 0),
            revenue=cents(revenue.get(seller_id, ZERO)),
            commission_earned=cents(earned.get(seller_id, ZERO)),
            # payable now: validated commissions and delivery fees, minus what was paid
            commission_due=cents(
                validated.get(seller_id, ZERO)
                + fees.get(seller_id, ZERO)
                - paid.get(seller_id, ZERO)
            ),
        )
        for seller_id in ids
    }


def _totals_by_reseller(
    queryset: QuerySet[CommissionEntry] | QuerySet[Payout] | QuerySet[DeliveryCredit],
) -> dict[int, Decimal]:
    rows = queryset.values("reseller_id").annotate(total=Sum("amount"))
    return {row["reseller_id"]: Decimal(row["total"] or 0) for row in rows}


def top_sellers(
    seller_ids: Iterable[int], *, since: datetime, limit: int = 1
) -> list[SellerPerformance]:
    ranked = sorted(
        seller_performance(seller_ids, since=since).values(),
        key=lambda performance: (-performance.revenue, performance.seller_id),
    )
    return [performance for performance in ranked[:limit] if performance.revenue > ZERO]


# validated sales of each reseller over a period (reseller policy, section 9): valid sales whose
# 7-day validation is over, net of refunds
def validated_sales(
    reseller_ids: Iterable[int], *, since: datetime, validated_before: datetime
) -> dict[int, Decimal]:
    ids = list(reseller_ids)
    rows = (
        Sale.objects.filter(
            seller_id__in=ids,
            status=SaleStatus.VALID.value,
            sold_at__gte=since,
            sold_at__lte=validated_before,
        )
        .values("seller_id")
        .annotate(
            gross=Sum(F("unit_price") * F("quantity")),
            refunded=Sum("refunded_amount"),
        )
    )
    found = {
        row["seller_id"]: (row["gross"] or Decimal(0)) - (row["refunded"] or Decimal(0))
        for row in rows
    }
    return {pk: found.get(pk, Decimal(0)) for pk in ids}
