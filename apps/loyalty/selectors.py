from apps.loyalty.domain.points import PointTransactionView
from apps.loyalty.domain.settings import AppLinks, CashbackTerms, Programmes
from apps.loyalty.models import LoyaltySettings, PointTransaction


def to_programmes(settings: LoyaltySettings) -> Programmes:
    return Programmes(
        cashback=CashbackTerms(
            enabled=settings.cashback_enabled,
            members_only=settings.cashback_members_only,
            percent=settings.cashback_percent,
            max_share=settings.cashback_max_share,
            min_balance=settings.cashback_min_balance,
            validity_months=settings.cashback_validity_months,
        ),
        app_links=AppLinks(app_store=settings.app_store_url, play_store=settings.play_store_url),
    )


def to_point_transaction_view(tx: PointTransaction) -> PointTransactionView:
    return PointTransactionView(
        id=tx.pk,
        points=tx.points,
        reason=tx.reason,
        rule_id=tx.rule_id,
        rule_name=tx.rule.name if tx.rule else None,
        reference_type=tx.reference_type or None,
        reference_id=tx.reference_id or None,
        created_at=tx.created_at,
    )
