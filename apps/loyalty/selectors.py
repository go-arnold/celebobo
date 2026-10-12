from apps.loyalty.domain.settings import AppLinks, CashbackTerms, MembershipTerms, Programmes
from apps.loyalty.models import LoyaltySettings


def to_programmes(settings: LoyaltySettings) -> Programmes:
    return Programmes(
        membership=MembershipTerms(
            enabled=settings.membership_enabled,
            monthly_price=settings.membership_monthly_price,
            yearly_price=settings.membership_yearly_price,
            trial_days=settings.membership_trial_days,
            reminder_days=settings.membership_reminder_days,
        ),
        cashback=CashbackTerms(
            enabled=settings.cashback_enabled,
            percent=settings.cashback_percent,
            max_share=settings.cashback_max_share,
            min_balance=settings.cashback_min_balance,
            validity_months=settings.cashback_validity_months,
        ),
        app_links=AppLinks(app_store=settings.app_store_url, play_store=settings.play_store_url),
    )
