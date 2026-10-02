from collections.abc import Callable, Iterator
from uuid import UUID

from django.db import transaction

from apps.content.domain.commands import (
    BannerChanges,
    BannerFields,
    ContactFilters,
    FaqChanges,
    FaqFields,
    HandleContactMessage,
    PageChanges,
    PageFields,
    SendContactMessage,
    SettingsChanges,
)
from apps.content.domain.events import (
    ContactMessageReceived,
    NewsletterSubscribed,
    SiteContentChanged,
)
from apps.content.domain.read_models import (
    BannerView,
    ContactMessageView,
    FaqGroup,
    FaqView,
    HomePage,
    PageView,
    SiteSettingsView,
    SubscriberView,
    Subscription,
)
from apps.content.models import Banner, FaqEntry, Page
from apps.content.selectors import (
    BannerSelector,
    ContactSelector,
    FaqSelector,
    PageSelector,
    SubscriberSelector,
    to_banner_view,
    to_faq_view,
    to_page_view,
    to_settings_view,
)
from apps.content.services.contact import ContactService
from apps.content.services.contracts import ShippingSource
from apps.content.services.editors import Editor
from apps.content.services.home import HomeService
from apps.content.services.mailer import ContentMailer
from apps.content.services.newsletter import NewsletterService
from apps.content.services.site import SiteSettingsService
from core.cache import VersionedCache
from core.domain.actor import Actor
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@logged_facade
class ContactFacade:
    def __init__(
        self,
        *,
        contact: ContactService,
        selector: ContactSelector,
        site: SiteSettingsService,
        mailer: ContentMailer,
        publisher: EventPublisher,
    ) -> None:
        self._contact = contact
        self._selector = selector
        self._site = site
        self._mailer = mailer
        self._publisher = publisher

    def send(self, actor: Actor, command: SendContactMessage, *, spam: bool) -> None:
        with transaction.atomic():
            message = self._contact.submit(actor, command, spam=spam)
            if not spam:
                self._publisher.publish(
                    ContactMessageReceived(message_id=message.pk, actor_id=actor.user_id)
                )

    def acknowledge(self, message_id: int) -> None:
        self._mailer.contact_received(self._contact.get(message_id), self._site.current())

    def inbox(
        self, filters: ContactFilters, *, offset: int, limit: int
    ) -> tuple[list[ContactMessageView], int, dict[str, int]]:
        return self._selector.page(filters, offset=offset, limit=limit)

    def detail(self, message_id: int) -> ContactMessageView:
        return self._selector.one(message_id)

    def handle(
        self, actor: Actor, message_id: int, command: HandleContactMessage
    ) -> ContactMessageView:
        with transaction.atomic():
            self._contact.handle(actor, message_id, command)
        return self._selector.one(message_id)


@logged_facade
class NewsletterFacade:
    def __init__(
        self,
        *,
        newsletter: NewsletterService,
        selector: SubscriberSelector,
        site: SiteSettingsService,
        mailer: ContentMailer,
        publisher: EventPublisher,
    ) -> None:
        self._newsletter = newsletter
        self._selector = selector
        self._site = site
        self._mailer = mailer
        self._publisher = publisher

    def subscribe(self, email: str, *, source: str) -> Subscription:
        with transaction.atomic():
            result = self._newsletter.subscribe(email, source=source)
            if result.created:
                self._publisher.publish(NewsletterSubscribed(subscriber_id=result.subscriber.pk))
        settings = self._site.current()
        return Subscription(
            email=result.subscriber.email,
            code=settings.newsletter_code,
            discount=settings.newsletter_discount,
            already_subscribed=not result.created,
        )

    def welcome(self, subscriber_id: int) -> None:
        subscriber = self._newsletter.get(subscriber_id)
        if subscriber is not None and subscriber.is_active:
            self._mailer.welcome(subscriber, self._site.current())

    def unsubscribe(self, token: UUID) -> None:
        with transaction.atomic():
            self._newsletter.unsubscribe(token)

    def subscribers(
        self, *, active: bool | None, search: str | None, offset: int, limit: int
    ) -> tuple[list[SubscriberView], int]:
        return self._selector.page(active=active, search=search, offset=offset, limit=limit)

    def export(self, *, active: bool | None) -> Iterator[SubscriberView]:
        return self._selector.export(active=active)


@logged_facade
class SiteContentFacade:
    def __init__(
        self,
        *,
        pages: Editor[Page],
        faq: Editor[FaqEntry],
        banners: Editor[Banner],
        page_selector: PageSelector,
        faq_selector: FaqSelector,
        banner_selector: BannerSelector,
        site: SiteSettingsService,
        shipping: ShippingSource,
        home: HomeService,
        cache: VersionedCache,
        publisher: EventPublisher,
    ) -> None:
        self._pages = pages
        self._faq = faq
        self._banners = banners
        self._page_selector = page_selector
        self._faq_selector = faq_selector
        self._banner_selector = banner_selector
        self._site = site
        self._shipping = shipping
        self._home = home
        self._cache = cache
        self._publisher = publisher

    def home(self, actor: Actor) -> HomePage:
        return self._home.page(actor)

    def public_settings(self) -> SiteSettingsView:
        return self._cache.get_or_set(
            "settings", lambda: to_settings_view(self._site.current(), self._shipping.shipping())
        )

    def admin_settings(self) -> SiteSettingsView:
        return to_settings_view(
            self._site.current(), self._shipping.shipping(), include_private=True
        )

    def update_settings(self, actor: Actor, changes: SettingsChanges) -> SiteSettingsView:
        with transaction.atomic():
            _, changed = self._site.update(changes)
            if changed:
                self._changed(actor, "settings")
        return self.admin_settings()

    def page(self, slug: str) -> PageView:
        return self._cache.get_or_set(f"page:{slug}", lambda: self._page_selector.published(slug))

    def pages(self, *, published_only: bool) -> list[PageView]:
        return self._page_selector.listing(published_only=published_only)

    def create_page(self, actor: Actor, fields: PageFields) -> PageView:
        return to_page_view(self._edit(actor, "pages", lambda: self._pages.create(fields)))

    def update_page(self, actor: Actor, page_id: int, changes: PageChanges) -> PageView:
        return to_page_view(
            self._edit(actor, "pages", lambda: self._pages.update(page_id, changes))
        )

    def delete_page(self, actor: Actor, page_id: int) -> None:
        self._edit(actor, "pages", lambda: self._pages.delete(page_id))

    def faq(self) -> list[FaqGroup]:
        return self._cache.get_or_set("faq", self._faq_selector.groups)

    def faq_entries(self) -> list[FaqView]:
        return self._faq_selector.all()

    def create_faq(self, actor: Actor, fields: FaqFields) -> FaqView:
        return to_faq_view(self._edit(actor, "faq", lambda: self._faq.create(fields)))

    def update_faq(self, actor: Actor, entry_id: int, changes: FaqChanges) -> FaqView:
        return to_faq_view(self._edit(actor, "faq", lambda: self._faq.update(entry_id, changes)))

    def delete_faq(self, actor: Actor, entry_id: int) -> None:
        self._edit(actor, "faq", lambda: self._faq.delete(entry_id))

    def banners(self) -> list[BannerView]:
        return self._banner_selector.all()

    def create_banner(self, actor: Actor, fields: BannerFields) -> BannerView:
        return to_banner_view(self._edit(actor, "banners", lambda: self._banners.create(fields)))

    def update_banner(self, actor: Actor, banner_id: int, changes: BannerChanges) -> BannerView:
        return to_banner_view(
            self._edit(actor, "banners", lambda: self._banners.update(banner_id, changes))
        )

    def delete_banner(self, actor: Actor, banner_id: int) -> None:
        self._edit(actor, "banners", lambda: self._banners.delete(banner_id))

    def _edit[T](self, actor: Actor, section: str, change: Callable[[], T]) -> T:
        with transaction.atomic():
            result = change()
            self._changed(actor, section)
        return result

    def _changed(self, actor: Actor, section: str) -> None:
        self._publisher.publish(SiteContentChanged(section=section, actor_id=actor.user_id))
