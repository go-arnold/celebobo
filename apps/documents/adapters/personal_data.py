"""One collector per app for the personal data export, each through that app's public API.

Only the subject's own data, and only what they can already see in the app: no other person's
contact details (a reseller's name on an order, never their phone or e-mail; no customer
identity on a reseller's sales), no internal fields (purchase costs, delivery code).
"""

from collections.abc import Callable
from typing import Any

from apps.accounts.domain.read_models import AddressView
from apps.accounts.facades import PreferencesFacade
from apps.accounts.selectors import AccountRecordSelector
from apps.catalog.selectors import FavoriteSelector, ReviewSelector
from apps.documents.domain.personal_data import DataSubject, day, instant, money
from apps.documents.domain.read_models import ReceiptRef
from apps.documents.selectors import ReceiptSelector
from apps.loyalty.facades import PointsFacade
from apps.messaging.selectors import ConversationSelector
from apps.orders.domain.enums import DeliveryMethod, OrderStatus
from apps.orders.domain.read_models import OrderDetail
from apps.orders.selectors import OrderSelector
from apps.resellers.selectors import ApplicationSelector
from apps.sales.domain.commands import SaleFilters
from apps.sales.domain.read_models import PersonRef, SaleView
from apps.sales.selectors import (
    CommissionSelector,
    PayoutSelector,
    SaleSelector,
    StatementSelector,
)
from core.container import container
from core.domain.actor import Actor, Role

BATCH = 500
# far above any real history: the export is never cut short in practice
MAX_ROWS = 50_000
SYSTEM_SENDER = "Celebobo"


def paged[T](fetch: Callable[[int, int], tuple[list[T], int]], *, limit: int = MAX_ROWS) -> list[T]:
    rows: list[T] = []
    while len(rows) < limit:
        page, total = fetch(len(rows), min(BATCH, limit - len(rows)))
        rows.extend(page)
        if not page or len(rows) >= total:
            break
    return rows


def address(view: AddressView) -> dict[str, Any]:
    return {
        "label": view.label.value,
        "recipient": view.recipient,
        "phone": view.phone,
        "line1": view.line1,
        "quarter": view.quarter,
        "city": view.city,
        "country": view.country,
        "is_default": view.is_default,
    }


class AccountCollector:
    def collect(self, subject: DataSubject) -> dict[str, Any]:
        record = AccountRecordSelector().record(subject.user_id)
        inviter = record.invited_by
        return {
            "id": record.id,
            "email": record.email,
            "email_verified": record.email_verified,
            "first_name": record.first_name,
            "last_name": record.last_name,
            "phone_number": record.phone_number,
            "avatar": record.avatar or None,
            "role": record.role.value,
            "date_joined": instant(record.date_joined),
            "last_login": instant(record.last_login),
            # the user's own code, for resellers
            "referral_code": record.referral_code,
            "invited_by": {"referral_code": inviter.referral_code, "first_name": inviter.first_name}
            if inviter
            else None,
            "invited_at": instant(record.invited_at),
            "addresses": [address(item) for item in record.addresses],
        }


class PreferencesCollector:
    def collect(self, subject: DataSubject) -> dict[str, Any]:
        actor = Actor(role=subject.role, user_id=subject.user_id)
        return dict(container.resolve(PreferencesFacade).current(actor))


class OrdersCollector:
    def __init__(self, *, limit: int) -> None:
        self._limit = limit

    def collect(self, subject: DataSubject) -> list[dict[str, Any]]:
        orders = OrderSelector().client_history(subject.user_id, limit=self._limit)
        receipts = ReceiptSelector().for_orders(order.summary.id for order in orders)
        return [self._order(order, receipts.get(order.summary.id)) for order in orders]

    @staticmethod
    def _order(order: OrderDetail, receipt: ReceiptRef | None) -> dict[str, Any]:
        summary = order.summary
        pickup = order.delivery_method is DeliveryMethod.PICKUP
        refunded = order.refund_due > 0 or order.refunded_at is not None
        return {
            "number": summary.number,
            "status": summary.status.value,
            "created_at": instant(summary.created_at),
            "items": [
                {
                    "product": item.name,
                    "variant": item.variant_label,
                    "sku": item.sku,
                    "quantity": item.quantity,
                    "unit_price": money(item.unit_price),
                    "total": money(item.total),
                    "discount": money(item.discount),
                    "points": money(item.points),
                    "amount_paid": money(item.amount_paid),
                    "returned_quantity": item.returned_quantity,
                    "returned_amount": money(item.returned_amount),
                }
                for item in order.items
            ],
            "subtotal": money(order.subtotal),
            "discount": money(order.discount),
            "coupon_code": order.coupon_code or None,
            "points": money(order.points),
            "shipping_fee": money(order.shipping_fee),
            "total": money(summary.total),
            "points_earned": money(order.points_earned),
            "payment_method": order.payment_method.value,
            "delivery": {
                "delivery_method": order.delivery_method.value,
                "address": None
                if pickup
                else {
                    "recipient": order.address.recipient,
                    "phone": order.address.phone,
                    "line1": order.address.line1,
                    "quarter": order.address.quarter,
                    "city": order.address.city,
                    "country": order.address.country,
                },
                "pickup_address": order.pickup_address or None,
                "shipping_zone": order.shipping_zone or None,
                "delivery_estimate": order.delivery_estimate or None,
                "attempts": [
                    {
                        "at": instant(attempt.at),
                        "reason": attempt.reason_label,
                        "note": attempt.note,
                    }
                    for attempt in order.delivery_attempts
                ],
            },
            "note": order.note or None,
            # the client sees the reseller's name only
            "reseller": {"name": order.reseller.name} if order.reseller else None,
            "refund": {
                "refund_due": money(order.refund_due),
                "refunded_at": instant(order.refunded_at),
                "note": order.refund_note or None,
            }
            if refunded
            else None,
            "cancel_reason": order.cancel_reason or None,
            "history": [
                {
                    "status": entry.status.value,
                    "at": instant(entry.at),
                    "by": entry.actor_name,
                    "note": entry.note or None,
                }
                for entry in order.history
            ],
            "rating": {
                "score": order.rating.score,
                "comment": order.rating.comment,
                "created_at": instant(order.rating.created_at),
            }
            if order.rating
            else None,
            "documents": {
                # issued on request from the order page, for any order not cancelled
                "invoice": None
                if summary.status is OrderStatus.CANCELLED
                else f"facture-{summary.number}.pdf",
                "delivery_receipt": {
                    "number": receipt.number,
                    "issued_at": instant(receipt.issued_at),
                }
                if receipt
                else None,
            },
        }


class PointsCollector:
    def collect(self, subject: DataSubject) -> dict[str, Any]:
        points = container.resolve(PointsFacade)
        balance = points.mine(Actor(role=subject.role, user_id=subject.user_id))
        return {
            "balance": {
                "available": money(balance.available),
                "pending": money(balance.pending),
                "next_expiry": instant(balance.next_expiry),
                "orders_count": balance.orders_count,
                "orders_total": money(balance.orders_total),
            },
            "movements": [
                {
                    "kind": movement.kind.value,
                    "amount": money(movement.amount),
                    "at": instant(movement.at),
                    "order_number": movement.order_number,
                    "pending": movement.pending,
                }
                for movement in points.history(subject.user_id, limit=MAX_ROWS)
            ],
        }


class ReviewsCollector:
    def collect(self, subject: DataSubject) -> list[dict[str, Any]]:
        return [
            {
                "product": review.product_name,
                "rating": review.rating,
                "message": review.message,
                "verified": review.verified,
                "moderation": review.status.value,
                "created_at": instant(review.created_at),
            }
            for review in ReviewSelector().by_author(subject.user_id)
        ]


class FavoritesCollector:
    def collect(self, subject: DataSubject) -> list[dict[str, Any]]:
        return [
            {"product": entry.product_name, "added_at": instant(entry.added_at)}
            for entry in FavoriteSelector().entries(subject.user_id)
        ]


class MessagesCollector:
    def __init__(self, *, limit: int) -> None:
        self._limit = limit

    def collect(self, subject: DataSubject) -> dict[str, Any]:
        threads = ConversationSelector().threads_of(subject.user_id, limit=self._limit)
        count = sum(len(thread.messages) for thread in threads)
        return {
            "truncated": count >= self._limit,
            "threads": [
                {
                    "kind": thread.conversation.kind.value,
                    "status": thread.conversation.status.value,
                    "subject": thread.conversation.subject or None,
                    "order_number": thread.conversation.order_number,
                    "created_at": instant(thread.conversation.created_at),
                    "own_messages_only": thread.own_messages_only,
                    "messages": [
                        {
                            "at": instant(message.created_at),
                            "sender": message.sender.name if message.sender else SYSTEM_SENDER,
                            "kind": message.kind.value,
                            "body": message.body,
                            "attachment": message.attachment or None,
                        }
                        for message in thread.messages
                    ],
                }
                for thread in threads
            ],
        }


class ResellerApplicationsCollector:
    def collect(self, subject: DataSubject) -> list[dict[str, Any]]:
        return [
            {
                "created_at": instant(application.created_at),
                "status": application.status.value,
                "first_name": application.first_name,
                "last_name": application.last_name,
                "email": application.email,
                "phone_number": application.phone_number,
                "city": application.city,
                "message": application.message,
                "reviewed_at": instant(application.reviewed_at),
                "decision_note": application.decision_note or None,
            }
            for application in ApplicationSelector().for_user(subject.user_id)
        ]


class ResellerCollector:
    """Sales, commissions, statements and payouts: for resellers, or anyone who has some."""

    def collect(self, subject: DataSubject) -> dict[str, Any] | None:
        reseller_id = subject.user_id
        sales = paged(lambda offset, limit: self._sales(reseller_id, offset, limit))
        commissions = paged(
            lambda offset, limit: CommissionSelector().entries(
                reseller_id, offset=offset, limit=limit
            )
        )
        if subject.role is not Role.RESELLER and not sales and not commissions:
            return None
        statements = StatementSelector()
        summary = CommissionSelector().summary(PersonRef(id=reseller_id, name=""))
        return {
            "summary": {
                "earned_total": money(summary.earned_total),
                "paid_total": money(summary.paid_total),
                "due": money(summary.due),
                "pending": money(summary.pending),
                "validated": money(summary.validated),
                "delivery_fees": money(summary.delivery_fees),
            },
            "sales": [
                {
                    "sold_at": instant(sale.sold_at),
                    "product": sale.product_name,
                    "variant": sale.variant_label,
                    "quantity": sale.quantity,
                    "unit_price": money(sale.unit_price),
                    "total": money(sale.total),
                    "refunded_amount": money(sale.refunded_amount),
                    "payment_method": sale.payment_method.value,
                    "status": sale.status.value,
                    "order_number": sale.order_number,
                }
                for sale in sales
            ],
            "commissions": [
                {
                    "created_at": instant(entry.created_at),
                    "kind": entry.kind.value,
                    "rule": entry.rule.value,
                    "base_amount": money(entry.base_amount),
                    "amount": money(entry.amount),
                    "status": entry.status.value,
                    "available_at": instant(entry.available_at),
                    "statement_id": entry.statement_id,
                }
                for entry in commissions
            ],
            "statements": [
                {
                    "id": statement.id,
                    "payout_date": day(statement.payout_date),
                    "status": statement.status.value,
                    "commissions": money(statement.commissions),
                    "delivery_fees": money(statement.delivery_fees),
                    "total": money(statement.total),
                    "prepared_at": instant(statement.prepared_at),
                    "paid_at": instant(statement.paid_at),
                    "lines": [
                        {
                            "kind": line.kind.value,
                            "label": line.label,
                            "order_number": line.order_number,
                            "base_amount": money(line.base_amount),
                            "amount": money(line.amount),
                            "at": instant(line.at),
                        }
                        for line in statements.detail(statement.id, reseller_id=reseller_id).lines
                    ],
                }
                for statement in paged(
                    lambda offset, limit: statements.page(
                        reseller_id, None, offset=offset, limit=limit
                    )
                )
            ],
            "payouts": [
                {
                    "paid_at": instant(payout.paid_at),
                    "amount": money(payout.amount),
                    "note": payout.note or None,
                    "statement_id": payout.statement_id,
                    "payout_date": day(payout.payout_date),
                }
                for payout in paged(
                    lambda offset, limit: PayoutSelector().page(
                        reseller_id, offset=offset, limit=limit
                    )
                )
            ],
        }

    @staticmethod
    def _sales(reseller_id: int, offset: int, limit: int) -> tuple[list[SaleView], int]:
        # the system scope, narrowed to the user's own sales: works whatever their role
        sales, total, _ = SaleSelector().page(
            Actor.system(), SaleFilters(seller_id=reseller_id), offset=offset, limit=limit
        )
        return sales, total
