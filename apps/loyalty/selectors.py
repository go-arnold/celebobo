from apps.loyalty.domain.settings import AppLinks, PointsTerms, Programmes
from apps.loyalty.models import LoyaltySettings


def to_programmes(settings: LoyaltySettings) -> Programmes:
    return Programmes(
        points=PointsTerms(
            enabled=settings.points_enabled,
            percent=settings.points_percent,
            validity_months=settings.points_validity_months,
            referral_percent=settings.referral_percent,
            referral_months=settings.referral_months,
        ),
        app_links=AppLinks(app_store=settings.app_store_url, play_store=settings.play_store_url),
    )
