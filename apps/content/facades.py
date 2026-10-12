from collections.abc import Callable, Iterator, Sequence
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
from apps.content.domain.errors import BannersOutsidePlacement
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
    Sitemap,
    SiteSettingsView,
    SubscriberView,
    Subscription,
)
from apps.content.domain.storefront import category_tags, product_tags, section_tags
from apps.content.models import Banner, FaqEntry, Page
from apps.content.repositories import BannerRepository
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
from apps.content.services.banners import with_products
from apps.content.services.contact import ContactService
from apps.content.services.contracts import PageRevalidator, ShippingSource, Showcase
from apps.content.services.editors import Editor
from apps.content.services.home import HomeService
from apps.content.services.mailer import ContentMailer
from apps.content.services.newsletter import NewsletterService
from apps.content.services.site import SiteSettingsService
from apps.content.services.storefront import PendingTags
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
        banner_repository: BannerRepository,
        page_selector: PageSelector,
        faq_selector: FaqSelector,
        banner_selector: BannerSelector,
        site: SiteSettingsService,
        shipping: ShippingSource,
        home: HomeService,
        showcase: Showcase,
        cache: VersionedCache,
        publisher: EventPublisher,
    ) -> None:
        self._pages = pages
        self._faq = faq
        self._banners = banners
        self._banner_repository = banner_repository
        self._page_selector = page_selector
        self._faq_selector = faq_selector
        self._banner_selector = banner_selector
        self._site = site
        self._shipping = shipping
        self._home = home
        self._showcase = showcase
        self._cache = cache
        self._publisher = publisher

    def home(self, actor: Actor) -> HomePage:
        return self._home.page(actor)

    def sitemap(self) -> Sitemap:
        catalog = self._showcase.sitemap()
        return Sitemap(
            products=catalog.products,
            categories=catalog.categories,
            pages=self._page_selector.sitemap(),
        )

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

    def banners(self, actor: Actor, placement: str | None = None) -> list[BannerView]:
        return with_products(self._banner_selector.all(placement), self._showcase, actor)

    def create_banner(self, actor: Actor, fields: BannerFields) -> BannerView:
        banner = self._edit(actor, "banners", lambda: self._banners.create(fields))
        return self._with_product(actor, to_banner_view(banner))

    def update_banner(self, actor: Actor, banner_id: int, changes: BannerChanges) -> BannerView:
        banner = self._edit(actor, "banners", lambda: self._banners.update(banner_id, changes))
        return self._with_product(actor, to_banner_view(banner))

    def reorder_banners(self, actor: Actor, placement: str, ids: Sequence[int]) -> list[BannerView]:
        def reorder() -> None:
            if not self._banner_repository.reorder(placement, ids):
                raise BannersOutsidePlacement

        self._edit(actor, "banners", reorder)
        return self.banners(actor, placement)

    def _with_product(self, actor: Actor, banner: BannerView) -> BannerView:
        return with_products([banner], self._showcase, actor)[0]

    def delete_banner(self, actor: Actor, banner_id: int) -> None:
        self._edit(actor, "banners", lambda: self._banners.delete(banner_id))

    def _edit[T](self, actor: Actor, section: str, change: Callable[[], T]) -> T:
        with transaction.atomic():
            result = change()
            self._changed(actor, section)
        return result

    def _changed(self, actor: Actor, section: str) -> None:
        self._publisher.publish(SiteContentChanged(section=section, actor_id=actor.user_id))


@logged_facade
class StorefrontFacade:
    def __init__(
        self,
        *,
        catalog: Showcase,
        pending: PendingTags,
        revalidator: PageRevalidator | None,
        schedule: Callable[[int], object],
        debounce: int,
    ) -> None:
        self._catalog = catalog
        self._pending = pending
        self._revalidator = revalidator
        self._schedule = schedule
        self._debounce = debounce

    def products_changed(self, product_ids: Sequence[int]) -> None:
        if not self._enabled:
            return
        locations = self._catalog.product_locations(product_ids)
        tags = dict.fromkeys(tag for location in locations for tag in product_tags(*location))
        if tags:
            self._queue(tuple(tags))

    def category_changed(self, category_id: int) -> None:
        slug = self._enabled and self._catalog.category_slug(category_id)
        if slug:
            self._queue(category_tags(slug))

    def section_changed(self, section: str) -> None:
        if self._enabled:
            self._queue(section_tags(section))

    def due_tags(self) -> list[str]:
        wait = self._pending.wait()
        if wait:
            self._schedule(wait)
            return []
        return self._pending.drain()

    def send(self, tags: list[str]) -> None:
        if self._revalidator is not None and tags:
            self._revalidator.revalidate(tags)

    @property
    def _enabled(self) -> bool:
        return self._revalidator is not None

    def _queue(self, tags: tuple[str, ...]) -> None:
        if self._pending.add(tags):
            self._schedule(self._debounce)
