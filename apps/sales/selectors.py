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
from apps.sales.domain.enums import CommissionKind, RefundKind, SaleStatus
from apps.sales.domain.errors import SaleNotFound
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
)
from apps.sales.domain.rules import ZERO, cents, profit_for
from apps.sales.models import CommissionEntry, Payout, Sale
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

    def summary(self, reseller: PersonRef, rate: Decimal) -> CommissionSummary:
        entries = CommissionEntry.objects.filter(reseller_id=reseller.id)
        month_start = self._clock().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        earned_total = _sum(entries, "amount")
        paid_total = _sum(Payout.objects.filter(reseller_id=reseller.id), "amount")
        return CommissionSummary(
            reseller=reseller,
            rate=rate,
            earned_this_month=_sum(entries.filter(created_at__gte=month_start), "amount"),
            earned_total=earned_total,
            paid_total=paid_total,
            due=earned_total - paid_total,
        )

    def entries(
        self, reseller_id: int, *, offset: int, limit: int
    ) -> tuple[list[CommissionEntryView], int]:
        entries = CommissionEntry.objects.filter(reseller_id=reseller_id)
        page = entries.order_by("-created_at", "-pk")[offset : offset + limit]
        return [_entry_view(entry) for entry in page], entries.count()

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
        payouts = Payout.objects.select_related("reseller", "paid_by")
        if reseller_id is not None:
            payouts = payouts.filter(reseller_id=reseller_id)
        page = payouts.order_by("-paid_at", "-pk")[offset : offset + limit]
        return [to_payout_view(payout) for payout in page], payouts.count()

    def one(self, payout_id: int) -> PayoutView:
        return to_payout_view(
            Payout.objects.select_related("reseller", "paid_by").get(pk=payout_id)
        )


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
    return PayoutView(
        id=payout.pk,
        reseller=_person(payout.reseller),
        amount=payout.amount,
        note=payout.note,
        paid_at=payout.paid_at,
        paid_by=_person(payout.paid_by) if payout.paid_by else None,
    )


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


def _entry_view(entry: CommissionEntry) -> CommissionEntryView:
    return CommissionEntryView(
        id=entry.pk,
        kind=CommissionKind(entry.kind),
        sale_id=entry.sale_id,
        rate=entry.rate,
        base_amount=entry.base_amount,
        amount=entry.amount,
        created_at=entry.created_at,
    )


def _person(user: object) -> PersonRef:
    first = getattr(user, "first_name", "")
    last = getattr(user, "last_name", "")
    return PersonRef(
        id=int(getattr(user, "pk", 0)),
        name=f"{first} {last}".strip() or str(getattr(user, "email", "")),
    )


def _sum(queryset: QuerySet[CommissionEntry] | QuerySet[Payout], field: str) -> Decimal:
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
    earned = _totals_by_reseller(CommissionEntry.objects.filter(reseller_id__in=ids))
    paid = _totals_by_reseller(Payout.objects.filter(reseller_id__in=ids))
    return {
        seller_id: SellerPerformance(
            seller_id=seller_id,
            sales_count=counts.get(seller_id, 0),
            revenue=cents(revenue.get(seller_id, ZERO)),
            commission_earned=cents(earned.get(seller_id, ZERO)),
            commission_due=cents(earned.get(seller_id, ZERO) - paid.get(seller_id, ZERO)),
        )
        for seller_id in ids
    }


def _totals_by_reseller(
    queryset: QuerySet[CommissionEntry] | QuerySet[Payout],
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
