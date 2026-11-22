from collections.abc import Mapping

from apps.accounts.domain.consents import CONSENT_DOCUMENTS, ConsentKind
from apps.content.facades import NewsletterFacade, SiteContentFacade
from core.container import container

# the same value as `apps.content.domain.retention.ACCOUNT_SOURCE`: such subscriptions follow the
# account's marketing consent
NEWSLETTER_SOURCE = "compte"


class ContentPolicyVersions:
    """Versions of the policy pages each consent is given on, from the content app."""

    def current(self) -> Mapping[ConsentKind, str]:
        versions = container.resolve(SiteContentFacade).policy_versions(
            tuple(CONSENT_DOCUMENTS.values())
        )
        return {kind: versions.get(slug, "") for kind, slug in CONSENT_DOCUMENTS.items()}


class ContentNewsletter:
    def subscribe(self, email: str) -> None:
        container.resolve(NewsletterFacade).subscribe(email, source=NEWSLETTER_SOURCE)

    def unsubscribe(self, email: str) -> None:
        container.resolve(NewsletterFacade).unsubscribe_email(email)

    def email_of(self, subscriber_id: int) -> str | None:
        return container.resolve(NewsletterFacade).email_of(subscriber_id)
