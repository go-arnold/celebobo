from dataclasses import dataclass
from decimal import Decimal

from allauth.account.models import EmailAddress
from django.core.cache import cache
from django.core.management import call_command

from apps.accounts.domain.commands import AddressFields, CreateUser, OnboardReseller, RegisterUser
from apps.accounts.domain.enums import AddressLabel
from apps.accounts.facades import (
    AccountFacade,
    AddressBookFacade,
    ResellerAccountFacade,
    UserAdminFacade,
)
from apps.accounts.models import User
from apps.catalog.domain.enums import CategoryIcon
from apps.catalog.domain.management import CategoryDraft, OptionInput, ProductDraft, VariantDraft
from apps.catalog.facades import CategoryAdminFacade, ProductAdminFacade
from apps.catalog.services.indexing import ProductIndexer
from apps.content.domain.commands import SettingsChanges
from apps.content.facades import SiteContentFacade
from apps.demo.seeder import SeedReport, quiet_side_effects
from apps.orders.domain.commands import CouponFields, ZoneFields
from apps.orders.domain.pricing import CouponKind
from apps.orders.facades import PromotionFacade
from core.api.actor import actor_from_user
from core.container import container
from core.domain.actor import Actor, Role

REFERRAL_CODE = "4821"
COUPON_CODE = "E2E10"
# city zones first, the last one is the default for every other city
SHIPPING_ZONES = (
    ("Bukavu", "3.00", "24 h"),
    ("Goma", "3.00", "24 h"),
    ("Reste du pays", "7.50", "3 à 7 jours"),
)


@dataclass(frozen=True, slots=True)
class E2eAccount:
    role: Role
    email: str
    first_name: str
    last_name: str
    phone: str


ACCOUNTS = (
    E2eAccount(Role.ADMIN, "admin@e2e.celebobo.test", "Admin", "E2E", "+243810000001"),
    E2eAccount(Role.MANAGER, "responsable@e2e.celebobo.test", "Joël", "Mpiana", "+243810000002"),
    E2eAccount(Role.RESELLER, "revendeur@e2e.celebobo.test", "Patrick", "Kabila", "+243810000003"),
    E2eAccount(Role.CLIENT, "client@e2e.celebobo.test", "Aline", "Mbuyi", "+243810000004"),
)


def reset_database() -> None:
    call_command("flush", interactive=False, verbosity=0)
    cache.clear()


# small fixed data set for browser tests: same accounts, slugs and ids after every reset
class E2eSeeder:
    def __init__(self, *, password: str) -> None:
        self._password = password
        self.report = SeedReport()

    def run(self) -> SeedReport:
        with quiet_side_effects():
            admin_account, manager_account, reseller_account, client_account = ACCOUNTS
            admin = self._admin(admin_account)
            actor = actor_from_user(admin)
            self._settings(actor)
            self._catalogue(actor)
            manager = self._manager(actor, manager_account)
            self._reseller(actor, reseller_account, manager)
            self._client(client_account)
            self._promotions()
            container.resolve(ProductIndexer).rebuild()
        return self.report

    def _admin(self, account: E2eAccount) -> User:
        admin = User.objects.create_superuser(
            email=account.email,
            password=self._password,
            first_name=account.first_name,
            last_name=account.last_name,
        )
        return self._ready(admin, account)

    def _settings(self, actor: Actor) -> None:
        container.resolve(SiteContentFacade).update_settings(
            actor,
            SettingsChanges(
                usd_to_cdf=Decimal("2850.00"),
                hotline="+243 81 000 0000",
                whatsapp="+243810000000",
                email="support@e2e.celebobo.test",
                payment_methods=["orange_money", "cash"],
            ),
        )

    def _catalogue(self, actor: Actor) -> None:
        categories = container.resolve(CategoryAdminFacade)
        products = container.resolve(ProductAdminFacade)
        phones = categories.create(actor, CategoryDraft(name="Smartphones")).id
        audio = categories.create(
            actor, CategoryDraft(name="Audio", icon=CategoryIcon.HEADPHONE)
        ).id
        drafts = (
            ProductDraft(
                name="Galaxy A55",
                description="Smartphone 5G en promotion, écran 6,6 pouces.",
                category_id=phones,
                price=Decimal("300.00"),
                sale_price=Decimal("250.00"),
                stock=20,
            ),
            ProductDraft(
                name="Redmi Note 13",
                description="Smartphone en rupture de stock pour les tests.",
                category_id=phones,
                price=Decimal("180.00"),
            ),
            ProductDraft(
                name="iPhone 15",
                description="Smartphone avec variantes de couleur.",
                category_id=phones,
                price=Decimal("900.00"),
                options=(OptionInput(name="Couleur", values=("Noir", "Bleu")),),
            ),
            ProductDraft(
                name="Écouteurs Bluetooth",
                description="Écouteurs sans fil, autonomie 30 heures.",
                category_id=audio,
                price=Decimal("25.00"),
                stock=50,
            ),
        )
        created = [products.create(actor, draft).row.id for draft in drafts]
        for color, price in (("Noir", None), ("Bleu", Decimal("950.00"))):
            products.add_variant(
                actor, created[2], VariantDraft(attributes={"Couleur": color}, price=price, stock=5)
            )
        self.report.add("categories", 2)
        self.report.add("products", len(created))
        self.report.add("variants", 2)

    def _manager(self, actor: Actor, account: E2eAccount) -> User:
        row = container.resolve(UserAdminFacade).create(
            actor,
            CreateUser(
                first_name=account.first_name,
                last_name=account.last_name,
                email=account.email,
                phone_number=account.phone,
                role=account.role,
            ),
        )
        return self._ready(User.objects.get(pk=row.id), account)

    def _reseller(self, actor: Actor, account: E2eAccount, manager: User) -> None:
        onboarded = container.resolve(ResellerAccountFacade).onboard(
            actor,
            OnboardReseller(
                email=account.email,
                first_name=account.first_name,
                last_name=account.last_name,
                phone_number=account.phone,
                commission_rate=Decimal("0.080"),
                manager_id=manager.pk,
            ),
        )
        User.objects.filter(pk=onboarded.user_id).update(referral_code=REFERRAL_CODE)
        self._ready(User.objects.get(pk=onboarded.user_id), account)

    def _client(self, account: E2eAccount) -> None:
        registration = container.resolve(AccountFacade).register(
            RegisterUser(
                first_name=account.first_name,
                last_name=account.last_name,
                email=account.email,
                password=self._password,
                phone_number=account.phone,
                referral_code=REFERRAL_CODE,
            )
        )
        client = self._ready(User.objects.get(pk=registration.user_id), account)
        container.resolve(AddressBookFacade).add(
            actor_from_user(client),
            AddressFields(
                label=AddressLabel.HOME,
                recipient=f"{account.first_name} {account.last_name}",
                phone=account.phone,
                line1="Avenue du Commerce n°12",
                quarter="Ibanda",
                city="Bukavu",
                country="RD Congo",
                is_default=True,
            ),
        )

    def _promotions(self) -> None:
        promotions = container.resolve(PromotionFacade)
        promotions.create_coupon(
            CouponFields(
                code=COUPON_CODE,
                kind=CouponKind.PERCENT,
                value=Decimal(10),
                description="10 % pour les tests",
            )
        )
        for position, (name, fee, estimate) in enumerate(SHIPPING_ZONES, start=1):
            promotions.create_zone(
                ZoneFields(
                    name=name,
                    fee=Decimal(fee),
                    cities=(name,) if position < len(SHIPPING_ZONES) else (),
                    delivery_estimate=estimate,
                    is_default=position == len(SHIPPING_ZONES),
                    position=position,
                )
            )
        self.report.add("coupons")
        self.report.add("shipping zones", len(SHIPPING_ZONES))

    def _ready(self, user: User, account: E2eAccount) -> User:
        user.set_password(self._password)
        user.save(update_fields=["password"])
        EmailAddress.objects.update_or_create(
            user=user, email=user.email, defaults={"verified": True, "primary": True}
        )
        self.report.accounts.append((account.role.value, account.email, self._password))
        return user
