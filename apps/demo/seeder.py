import random
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any

from allauth.account.models import EmailAddress
from django.conf import settings
from django.test.utils import override_settings
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.domain.commands import AddressFields, CreateUser, OnboardReseller, RegisterUser
from apps.accounts.domain.enums import AddressLabel
from apps.accounts.facades import (
    AccountFacade,
    AddressBookFacade,
    ResellerAccountFacade,
    UserAdminFacade,
)
from apps.accounts.models import User
from apps.analytics.facades import FactsFacade
from apps.assistant.facades import AssistantInsightsFacade
from apps.catalog.domain.management import CategoryDraft, OptionInput, ProductDraft, VariantDraft
from apps.catalog.domain.queries import PostReview
from apps.catalog.facades import CategoryAdminFacade, ProductAdminFacade, ReviewFacade
from apps.catalog.services.indexing import ProductIndexer
from apps.content.domain.commands import (
    BannerFields,
    FaqFields,
    PageFields,
    SendContactMessage,
    SettingsChanges,
)
from apps.content.domain.enums import ContactSubject
from apps.content.facades import ContactFacade, NewsletterFacade, SiteContentFacade
from apps.demo import catalogue, content, people
from apps.demo.images import banner_image, category_image, product_image
from apps.demo.uploads import ImageStore
from apps.media.models import UploadedMedia
from apps.messaging.domain.commands import OpenSupport, PostMessage
from apps.messaging.facades import ConversationFacade
from apps.orders.domain.commands import (
    AssignOrder,
    CancelOrder,
    CouponFields,
    OrderLineInput,
    PlaceOrder,
    TransitionOrder,
)
from apps.orders.domain.enums import CancelReason, OrderStatus, PaymentMethod
from apps.orders.facades import CheckoutFacade, ClientOrderFacade, DispatchFacade, PromotionFacade
from apps.orders.models import Order, OrderStatusEvent
from apps.resellers.domain.commands import SubmitApplication
from apps.resellers.facades import ApplicationFacade
from apps.sales.domain.commands import ConvertOrder, RecordPayout, RecordSale
from apps.sales.facades import CommissionFacade, SalesFacade
from config.celery import app as celery_app
from core.api.actor import actor_from_user
from core.container import container
from core.domain.actor import Actor, Role
from core.domain.errors import DomainError

DOMAIN = "celebobo.test"
LISTED_CLIENTS = 3
STREETS = ("Kasa-Vubu", "Lumumba", "de la Paix", "du 30 Juin")
SHOP_BUYERS = ("Client boutique", "Jean Mukendi", "Mama Thérèse", "Entreprise Kin Services")
DISCOUNTS = (Decimal("1"), Decimal("1"), Decimal("0.97"), Decimal("0.95"))
FLOW = (OrderStatus.CONFIRMED, OrderStatus.PAID, OrderStatus.SHIPPING, OrderStatus.DELIVERED)
TARGETS = (
    *([OrderStatus.DELIVERED] * 12),
    *([OrderStatus.SHIPPING] * 3),
    *([OrderStatus.PAID] * 3),
    *([OrderStatus.CONFIRMED] * 3),
    *([OrderStatus.ASSIGNED] * 2),
    *([OrderStatus.PENDING] * 3),
    *([OrderStatus.CANCELLED] * 2),
    OrderStatus.RETURNED,
)
PAYMENTS = (
    PaymentMethod.ORANGE_MONEY,
    PaymentMethod.MPESA,
    PaymentMethod.AIRTEL_MONEY,
    PaymentMethod.CASH,
)
REVIEWS = (
    (5, "Excellent produit, livré rapidement à Kinshasa. Je recommande !"),
    (5, "Conforme à la description, le conseiller a été très patient."),
    (4, "Très bon rapport qualité-prix, l'emballage était soigné."),
    (4, "Bon produit, livraison un peu longue mais le suivi était clair."),
    (3, "Correct pour le prix, mais la batterie pourrait être meilleure."),
)
MESSAGES = (
    "Bonjour, ma commande est-elle bien confirmée ?",
    "Bonjour ! Oui, elle part aujourd'hui. Je vous appelle à la livraison.",
    "Merci beaucoup, à tout à l'heure.",
)


@dataclass(slots=True)
class SeedReport:
    counts: dict[str, int] = field(default_factory=dict)
    accounts: list[tuple[str, str, str]] = field(default_factory=list)

    def add(self, name: str, amount: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + amount


class DemoSeeder:
    def __init__(
        self, *, admin_email: str, password: str, images: bool, log: Callable[[str], None]
    ) -> None:
        self._admin_email = admin_email
        self._password = password
        self._images_enabled = images
        self._log = log
        self._random = random.Random(2026)
        self._now = timezone.now()
        self.report = SeedReport()

    def run(self) -> SeedReport:
        with self._quiet_side_effects():
            admin = self._admin()
            self._store = ImageStore(owner_id=admin.pk) if self._images_enabled else None
            self._actor = actor_from_user(admin)
            self._site_content()
            products = self._catalogue()
            managers = [self._staff(person, Role.MANAGER) for person in people.MANAGERS]
            resellers = [self._reseller(person, managers) for person in people.RESELLERS]
            clients = [
                self._client(index, person, resellers)
                for index, person in enumerate(people.CLIENTS)
            ]
            self._coupons()
            delivered = self._orders(products, managers[0], resellers, clients)
            self._direct_sales(products, managers[0], resellers)
            self._payouts(resellers)
            self._reviews(delivered)
            self._community(clients)
            self._refresh()
        self._embed()
        return self.report

    @contextmanager
    def _quiet_side_effects(self) -> Iterator[None]:
        eager, propagates = celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates
        celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates = True, False
        overrides = {
            "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            "CORE": {**settings.CORE, "EVENTS_DISPATCHER": "inline"},
            "ASSISTANT": {**settings.ASSISTANT, "PROVIDER": "offline"},
            "PUSH": {},
        }
        try:
            with override_settings(**overrides):
                yield
        finally:
            celery_app.conf.task_always_eager = eager
            celery_app.conf.task_eager_propagates = propagates

    def _admin(self) -> User:
        admin = User.objects.filter(email__iexact=self._admin_email).first()
        if admin is None:
            admin = User.objects.create_superuser(
                email=self._admin_email,
                password=self._password,
                first_name="Admin",
                last_name="Celebobo",
            )
        self._verified(admin)
        self.report.accounts.append(("admin", admin.email, self._password))
        return admin

    def _image(self, name: str, content: Callable[[], bytes], purpose: str) -> int | None:
        if self._store is None:
            return None
        media_id = self._store.upload(name, content(), purpose=purpose)
        self.report.add("images")
        return media_id

    def _site_content(self) -> None:
        site = container.resolve(SiteContentFacade)
        site.update_settings(
            self._actor,
            SettingsChanges(
                usd_to_cdf=Decimal("2850.00"),
                hotline="+250 791 449 879",
                whatsapp="+250791449879",
                email="support@celebobo.com",
                address="Avenue du Commerce 12, Gombe, Kinshasa",
                opening_hours=[dict(item) for item in content.OPENING_HOURS],
                payment_methods=[method.value for method in PAYMENTS],
                social_links={
                    "facebook": "https://facebook.com/celebobo",
                    "instagram": "https://instagram.com/celebobo",
                    "tiktok": "https://tiktok.com/@celebobo",
                },
                newsletter_code="BIENVENUE10",
                newsletter_discount=10,
            ),
        )
        for position, (slug, title, summary, body) in enumerate(content.PAGES, start=1):
            site.create_page(
                self._actor,
                PageFields(slug=slug, title=title, summary=summary, body=body, position=position),
            )
            self.report.add("pages")
        for position, (category, question, answer) in enumerate(content.FAQ, start=1):
            site.create_faq(
                self._actor,
                FaqFields(question=question, answer=answer, category=category, position=position),
            )
            self.report.add("faq")
        shapes = ("phone", "laptop", "speaker")
        palette = (("#1d4ed8", "#60a5fa"), ("#0f766e", "#5eead4"), ("#b45309", "#fcd34d"))
        for position, ((title, subtitle, link, label), shape, colors) in enumerate(
            zip(content.BANNERS, shapes, palette, strict=True), start=1
        ):
            media_id = self._image(
                f"banner-{position}",
                partial(banner_image, title, subtitle, shape, colors),
                "category_image",
            )
            image = (
                self._media_url(media_id)
                or "https://res.cloudinary.com/demo/image/upload/sample.jpg"
            )
            site.create_banner(
                self._actor,
                BannerFields(
                    title=title,
                    subtitle=subtitle,
                    image=image,
                    link_url=link,
                    link_label=label,
                    position=position,
                ),
            )
            self.report.add("banners")

    def _catalogue(self) -> list[dict[str, Any]]:
        categories = container.resolve(CategoryAdminFacade)
        admin_products = container.resolve(ProductAdminFacade)
        category_ids: dict[str, int] = {}
        first_shape = {product.category: product.shape for product in reversed(catalogue.PRODUCTS)}
        for item in catalogue.CATEGORIES:
            media_id = self._image(
                f"category-{item.key}",
                partial(category_image, first_shape[item.key], item.name, item.color),
                "category_image",
            )
            created = categories.create(
                self._actor,
                CategoryDraft(
                    name=item.name, icon=item.icon, description=item.description, image_id=media_id
                ),
            )
            category_ids[item.key] = created.id
            self.report.add("categories")
        colors = {item.key: item.color for item in catalogue.CATEGORIES}
        products = []
        for product in catalogue.PRODUCTS:
            price, sale_price, cost = product.money
            media_id = self._image(
                f"product-{slugify(product.name)}",
                partial(product_image, product.shape, product.brand, colors[product.category]),
                "product_image",
            )
            detail = admin_products.create(
                self._actor,
                ProductDraft(
                    name=product.name,
                    description=product.description,
                    long_description=product.description,
                    category_id=category_ids[product.category],
                    price=price,
                    sale_price=sale_price,
                    cost_price=cost,
                    badge=product.badge,
                    free_shipping=product.free_shipping,
                    stock=0 if product.variants else product.stock,
                    stock_threshold=5,
                    features=product.features,
                    options=tuple(
                        OptionInput(name=name, values=values)
                        for name, values in product.options.items()
                    ),
                    image_ids=(media_id,) if media_id else (),
                    delivery_policy_primary="Livraison en 24 à 48 h à Kinshasa",
                    delivery_policy_secondary="Retour gratuit sous 7 jours",
                ),
            )
            variant_ids = []
            for attributes, variant_price, stock in product.variants:
                after = admin_products.add_variant(
                    self._actor,
                    detail.row.id,
                    VariantDraft(
                        attributes=attributes,
                        price=Decimal(variant_price) if variant_price else None,
                        stock=stock,
                    ),
                )
                variant_ids.append(after.variants[-1].id)
                self.report.add("variants")
            products.append({"id": detail.row.id, "slug": detail.row.slug, "variants": variant_ids})
            self.report.add("products")
        return products

    def _staff(self, person: people.DemoPerson, role: Role) -> User:
        email = people.email_for(person, DOMAIN)
        row = container.resolve(UserAdminFacade).create(
            self._actor,
            CreateUser(
                first_name=person.first_name,
                last_name=person.last_name,
                email=email,
                phone_number=person.phone,
                role=role,
            ),
        )
        user = self._with_password(row.id)
        self.report.accounts.append((role.value, email, self._password))
        self.report.add("managers")
        return user

    def _reseller(self, person: people.DemoPerson, managers: list[User]) -> User:
        email = people.email_for(person, DOMAIN)
        onboarded = container.resolve(ResellerAccountFacade).onboard(
            self._actor,
            OnboardReseller(
                email=email,
                first_name=person.first_name,
                last_name=person.last_name,
                phone_number=person.phone,
                commission_rate=self._random.choice(
                    (Decimal("0.070"), Decimal("0.080"), Decimal("0.100"))
                ),
                manager_id=self._random.choice(managers).pk,
            ),
        )
        user = self._with_password(onboarded.user_id)
        self.report.accounts.append(("reseller", email, self._password))
        self.report.add("resellers")
        return user

    def _client(self, index: int, person: people.DemoPerson, resellers: list[User]) -> User:
        email = people.email_for(person, DOMAIN)
        inviter = resellers[index % len(resellers)] if index % 3 else None
        registration = container.resolve(AccountFacade).register(
            RegisterUser(
                first_name=person.first_name,
                last_name=person.last_name,
                email=email,
                password=self._password,
                phone_number=person.phone,
                referral_code=inviter.referral_code if inviter else None,
            )
        )
        user = User.objects.get(pk=registration.user_id)
        self._verified(user)
        container.resolve(AddressBookFacade).add(
            actor_from_user(user),
            AddressFields(
                label=AddressLabel.HOME,
                recipient=f"{person.first_name} {person.last_name}",
                phone=person.phone,
                line1=f"Avenue {self._random.choice(STREETS)} n°{self._random.randint(1, 120)}",
                quarter=person.quarter,
                city=person.city,
                country="RD Congo",
                is_default=True,
            ),
        )
        User.objects.filter(pk=user.pk).update(date_joined=self._days_ago(90, 20))
        self.report.add("clients")
        if index < LISTED_CLIENTS:
            self.report.accounts.append(("client", email, self._password))
        return user

    def _coupons(self) -> None:
        promotions = container.resolve(PromotionFacade)
        for code, description, kind, value, cap, minimum, per_user, usage in content.COUPONS:
            promotions.create_coupon(
                CouponFields(
                    code=code,
                    description=description,
                    kind=kind,
                    value=Decimal(value),
                    max_discount=Decimal(cap) if cap else None,
                    min_subtotal=Decimal(minimum),
                    per_user_limit=per_user,
                    usage_limit=usage,
                )
            )
            self.report.add("coupons")

    def _orders(
        self,
        products: list[dict[str, Any]],
        manager: User,
        resellers: list[User],
        clients: list[User],
    ) -> list[tuple[User, dict[str, Any]]]:
        checkout = container.resolve(CheckoutFacade)
        dispatch = container.resolve(DispatchFacade)
        staff = actor_from_user(manager)
        delivered: list[tuple[User, dict[str, Any]]] = []
        for index, target in enumerate(TARGETS):
            client = clients[index % len(clients)]
            actor = actor_from_user(client)
            picks = self._random.sample(products, k=self._random.choice((1, 1, 2)))
            lines = tuple(
                OrderLineInput(
                    product_id=item["id"],
                    variant_id=self._random.choice(item["variants"]) if item["variants"] else None,
                    quantity=1,
                )
                for item in picks
            )
            try:
                order = checkout.place(
                    actor,
                    PlaceOrder(
                        lines=lines,
                        payment_method=self._random.choice(PAYMENTS),
                        address_id=client.addresses.get().pk,
                        note="Merci d'appeler avant de passer." if index % 4 == 0 else "",
                        coupon_code="BIENVENUE10" if index == 1 else None,
                    ),
                )
            except DomainError as error:
                self._log(f"  commande ignorée : {error.detail}")
                continue
            order_id, number = order.summary.id, order.summary.number
            reseller = resellers[index % len(resellers)]
            if target is OrderStatus.CANCELLED:
                container.resolve(ClientOrderFacade).cancel(
                    actor, number, CancelOrder(reason=CancelReason.CHANGED_MIND)
                )
            elif target is not OrderStatus.PENDING:
                dispatch.assign(staff, order_id, AssignOrder(reseller_id=reseller.pk))
                if order.conversation_id and index % 3 == 0:
                    self._chat(order.conversation_id, client, reseller)
                for status in FLOW[: self._steps(target)]:
                    dispatch.transition(staff, order_id, TransitionOrder(to=status))
                if target is OrderStatus.RETURNED:
                    dispatch.transition(
                        staff,
                        order_id,
                        TransitionOrder(to=OrderStatus.RETURNED, reason="Produit défectueux"),
                    )
            self._backdate(order_id, target)
            if target is OrderStatus.DELIVERED:
                delivered.append(
                    (client, {"order_id": order_id, "reseller": reseller, "lines": picks})
                )
            self.report.add("orders")
        sales = container.resolve(SalesFacade)
        for _client, item in delivered[::2]:
            sales.convert(actor_from_user(item["reseller"]), item["order_id"], ConvertOrder())
            self.report.add("converted orders")
        return delivered

    def _steps(self, target: OrderStatus) -> int:
        if target in (OrderStatus.DELIVERED, OrderStatus.RETURNED):
            return len(FLOW)
        if target is OrderStatus.ASSIGNED:
            return 0
        return FLOW.index(target) + 1

    def _chat(self, conversation_id: int, client: User, staff: User) -> None:
        conversations = container.resolve(ConversationFacade)
        for author, body in zip((client, staff, client), MESSAGES, strict=True):
            conversations.post(actor_from_user(author), conversation_id, PostMessage(body=body))
            self.report.add("messages")

    def _direct_sales(
        self, products: list[dict[str, Any]], manager: User, resellers: list[User]
    ) -> None:
        sales = container.resolve(SalesFacade)
        sellers = [*resellers, manager]
        for index in range(45):
            seller = sellers[index % len(sellers)]
            item = self._random.choice(products)
            detail = container.resolve(ProductAdminFacade).detail(item["id"])
            price = detail.row.current_price
            try:
                sales.record(
                    actor_from_user(seller),
                    RecordSale(
                        product_id=item["id"],
                        variant_id=self._random.choice(item["variants"])
                        if item["variants"]
                        else None,
                        quantity=self._random.choice((1, 1, 1, 2)),
                        unit_price=(price * self._random.choice(DISCOUNTS)).quantize(
                            Decimal("0.01")
                        ),
                        payment_method=self._random.choice(PAYMENTS),
                        sold_at=self._days_ago(88, 0),
                        sold_to=self._random.choice(SHOP_BUYERS),
                    ),
                )
            except DomainError as error:
                self._log(f"  vente ignorée : {error.detail}")
                continue
            self.report.add("sales")

    def _payouts(self, resellers: list[User]) -> None:
        commissions = container.resolve(CommissionFacade)
        for reseller in resellers[:2]:
            due = commissions.summary(self._actor, reseller.pk).due
            if due >= Decimal("5"):
                commissions.record_payout(
                    self._actor,
                    RecordPayout(
                        reseller_id=reseller.pk,
                        amount=(due / 2).quantize(Decimal("0.01")),
                        note="Paiement Orange Money",
                    ),
                )
                self.report.add("payouts")

    def _reviews(self, delivered: list[tuple[User, dict[str, Any]]]) -> None:
        reviews = container.resolve(ReviewFacade)
        for index, (client, item) in enumerate(delivered):
            rating, message = REVIEWS[index % len(REVIEWS)]
            for line in item["lines"]:
                try:
                    reviews.post(
                        actor_from_user(client),
                        line["slug"],
                        PostReview(rating=rating, message=message),
                    )
                except DomainError:
                    continue
                self.report.add("reviews")

    def _community(self, clients: list[User]) -> None:
        conversations = container.resolve(ConversationFacade)
        conversations.open_support(
            actor_from_user(clients[0]),
            OpenSupport(
                subject="Garantie",
                message="Bonjour, comment fonctionne la garantie sur les smartphones ?",
            ),
        )
        self.report.add("support conversations")
        newsletter = container.resolve(NewsletterFacade)
        for client in clients[:8]:
            newsletter.subscribe(client.email, source="pied de page")
            self.report.add("subscribers")
        contact = container.resolve(ContactFacade)
        anonymous = Actor.anonymous()
        for person, subject, message in (
            (
                people.CLIENTS[3],
                ContactSubject.ORDER,
                "Bonjour, je souhaite modifier l'adresse de ma commande.",
            ),
            (
                people.CLIENTS[6],
                ContactSubject.PRODUCT,
                "Le Galaxy S24 sera-t-il bientôt disponible en violet ?",
            ),
            (
                people.APPLICANTS[0],
                ContactSubject.PARTNERSHIP,
                "Nous aimerions distribuer vos produits à Kananga.",
            ),
        ):
            contact.send(
                anonymous,
                SendContactMessage(
                    name=f"{person.first_name} {person.last_name}",
                    email=people.email_for(person, DOMAIN),
                    phone=person.phone,
                    subject=subject,
                    message=message,
                ),
                spam=False,
            )
            self.report.add("contact messages")
        applications = container.resolve(ApplicationFacade)
        for person in people.APPLICANTS:
            applications.submit(
                anonymous,
                SubmitApplication(
                    first_name=person.first_name,
                    last_name=person.last_name,
                    email=people.email_for(person, DOMAIN),
                    phone_number=person.phone,
                    city=person.city,
                    message="Je vends déjà des téléphones dans mon quartier et je souhaite rejoindre le réseau.",
                ),
            )
            self.report.add("reseller applications")

    def _refresh(self) -> None:
        container.resolve(ProductIndexer).rebuild()
        container.resolve(FactsFacade).refresh()

    def _embed(self) -> None:
        try:
            result = container.resolve(AssistantInsightsFacade).reindex()
        except DomainError as error:
            self._log(f"  vecteurs non calculés : {error.detail}")
            return
        self.report.add(
            "product embeddings", result.get("embedded", 0) + result.get("unchanged", 0)
        )

    def _with_password(self, user_id: int) -> User:
        user = User.objects.get(pk=user_id)
        user.set_password(self._password)
        user.save(update_fields=["password"])
        self._verified(user)
        return user

    @staticmethod
    def _verified(user: User) -> None:
        EmailAddress.objects.update_or_create(
            user=user, email=user.email, defaults={"verified": True, "primary": True}
        )

    def _backdate(self, order_id: int, target: OrderStatus) -> None:
        placed = self._days_ago(75, 2 if target is OrderStatus.DELIVERED else 0)
        Order.objects.filter(pk=order_id).update(created_at=placed)
        events = OrderStatusEvent.objects.filter(order_id=order_id).order_by("pk")
        for step, event in enumerate(events):
            OrderStatusEvent.objects.filter(pk=event.pk).update(
                created_at=placed + timedelta(hours=6 * step)
            )

    def _days_ago(self, oldest: int, newest: int) -> datetime:
        days = self._random.uniform(newest, oldest)
        moment = self._now - timedelta(days=days)
        return moment.replace(hour=self._random.randint(8, 19), minute=self._random.randint(0, 59))

    def _media_url(self, media_id: int | None) -> str | None:
        if media_id is None:
            return None
        return UploadedMedia.objects.filter(pk=media_id).values_list("url", flat=True).first()
