from collections.abc import Iterable

from allauth.account.models import EmailAddress
from django.db.models import Count, Exists, OuterRef, Q, QuerySet

from apps.accounts.domain.commands import ResellerFilters, UserFilters
from apps.accounts.domain.consents import (
    ConsentKind,
    ConsentSource,
    PolicyVersions,
    missing_consents,
    needs_consents,
)
from apps.accounts.domain.enums import (
    ACCOUNT_ROLES,
    AddressLabel,
    Availability,
    NotificationChannel,
    NotificationTopic,
    ResellerOrdering,
)
from apps.accounts.domain.errors import AddressNotFound, ResellerNotFound, UserNotFound
from apps.accounts.domain.phone import parse_drc_phone, phone_missing, phone_search_fragment
from apps.accounts.domain.preferences import DEFAULT_PREFERENCES
from apps.accounts.domain.read_models import (
    AddressView,
    ConsentOverview,
    ConsentRecord,
    ConsentStatus,
    Contact,
    Invitee,
    InviterRef,
    InvitingReseller,
    ManagerRef,
    Profile,
    Referral,
    ReferralCheck,
    ResellerAccount,
    ResellerCounts,
    ResellerProfile,
    ResellerRef,
    SellerProfile,
    UserRow,
)
from apps.accounts.models import Address, Consent, NotificationPreference, User
from core.authz.catalog import PermissionCatalog
from core.domain.actor import Role


class ConsentSelector:
    def __init__(self, versions: PolicyVersions) -> None:
        self._versions = versions

    def missing(self, user_id: int, role: Role) -> tuple[ConsentKind, ...]:
        if not needs_consents(role):
            return ()
        return missing_consents(
            role, Consent.objects.open_versions(user_id), self._versions.current()
        )

    def overview(self, user_id: int, role: Role) -> ConsentOverview:
        records = list(Consent.objects.filter(user_id=user_id).order_by("-accepted_at", "-pk"))
        current = self._versions.current()
        latest: dict[ConsentKind, Consent] = {}
        for record in records:
            if record.withdrawn_at is None:
                latest.setdefault(ConsentKind(record.kind), record)
        accepted = {kind: record.version for kind, record in latest.items()}
        return ConsentOverview(
            consents=tuple(
                _consent_status(kind, latest.get(kind), current.get(kind, ""))
                for kind in ConsentKind
            ),
            missing=missing_consents(role, accepted, current),
            history=tuple(_consent_record(record) for record in records),
        )


def _consent_status(kind: ConsentKind, open_record: Consent | None, current: str) -> ConsentStatus:
    return ConsentStatus(
        kind=kind,
        label=kind.label,
        required=kind.required,
        given=open_record is not None,
        version=open_record.version if open_record else None,
        accepted_at=open_record.accepted_at if open_record else None,
        source=ConsentSource(open_record.source) if open_record else None,
        current_version=current,
        outdated=open_record is not None and current not in ("", open_record.version),
    )


def _consent_record(record: Consent) -> ConsentRecord:
    return ConsentRecord(
        kind=ConsentKind(record.kind),
        version=record.version,
        source=ConsentSource(record.source),
        accepted_at=record.accepted_at,
        withdrawn_at=record.withdrawn_at,
    )


class ProfileSelector:
    def __init__(self, catalog: PermissionCatalog, consents: ConsentSelector) -> None:
        self._catalog = catalog
        self._consents = consents

    def profile(self, user_id: int) -> Profile:
        user = (
            User.objects.select_related("invited_by")
            .annotate(invited_count=Count("invitees", distinct=True))
            .filter(pk=user_id, is_active=True)
            .first()
        )
        if user is None:
            raise UserNotFound
        role = user.account_role
        return Profile(
            id=user.pk,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone_number=user.phone_number,
            avatar=user.avatar,
            role=role,
            email_verified=EmailAddress.objects.filter(
                user_id=user.pk, email__iexact=user.email, verified=True
            ).exists(),
            date_joined=user.date_joined,
            invited_by_code=user.invited_by.referral_code if user.invited_by else None,
            permissions=tuple(sorted(self._catalog.permissions_for(role))),
            reseller=_reseller_profile(user) if role is Role.RESELLER else None,
            missing_consents=self._consents.missing(user.pk, role),
            phone_required=phone_missing(role, user.phone_number),
        )


class AddressSelector:
    def for_user(self, user_id: int) -> list[AddressView]:
        return [to_address_view(address) for address in Address.objects.filter(user_id=user_id)]

    def one(self, user_id: int, address_id: int) -> AddressView:
        address = Address.objects.filter(user_id=user_id, pk=address_id).first()
        if address is None:
            raise AddressNotFound
        return to_address_view(address)


class ReferralSelector:
    # the reseller who invited the client, while that reseller is still active
    def referral(self, client_id: int) -> Referral | None:
        row = (
            User.objects.filter(
                pk=client_id,
                invited_by__isnull=False,
                invited_at__isnull=False,
                invited_by__is_active=True,
                invited_by__role=Role.RESELLER.value,
            )
            .values("invited_by_id", "invited_at")
            .first()
        )
        if row is None or row["invited_at"] is None:
            return None
        return Referral(reseller_id=row["invited_by_id"], since=row["invited_at"])

    # the active reseller who invited each client, with no time limit, in one query
    def inviting_resellers(self, client_ids: Iterable[int]) -> dict[int, InvitingReseller]:
        clients = (
            User.objects.filter(
                pk__in=set(client_ids),
                invited_by__is_active=True,
                invited_by__role=Role.RESELLER.value,
            )
            .select_related("invited_by")
            .only(
                "id",
                "invited_at",
                "invited_by__id",
                "invited_by__first_name",
                "invited_by__last_name",
                "invited_by__email",
            )
        )
        return {
            client.pk: InvitingReseller(
                id=inviter.pk,
                name=inviter.get_full_name() or inviter.email,
                invited_at=client.invited_at,
            )
            for client in clients
            if (inviter := client.invited_by) is not None
        }

    def check(self, code: str) -> ReferralCheck:
        reseller = (
            User.objects.filter(referral_code=code, role=Role.RESELLER.value, is_active=True)
            .only("first_name")
            .first()
        )
        if reseller is None:
            return ReferralCheck(valid=False)
        return ReferralCheck(valid=True, reseller_first_name=reseller.first_name or None)


def to_address_view(address: Address) -> AddressView:
    return AddressView(
        id=address.pk,
        label=AddressLabel(address.label),
        recipient=address.recipient,
        phone=address.phone,
        line1=address.line1,
        quarter=address.quarter,
        city=address.city,
        country=address.country,
        is_default=address.is_default,
    )


def _reseller_profile(user: User) -> ResellerProfile:
    return ResellerProfile(
        referral_code=user.referral_code,
        availability=Availability(user.availability),
        invited_count=getattr(user, "invited_count", 0),
    )


class ResellerSelector:
    def active(self, reseller_id: int) -> ResellerRef | None:
        reseller = self._resellers().filter(pk=reseller_id).first()
        return _reseller_ref(reseller) if reseller else None

    def assignable(self, search: str | None = None, *, limit: int = 50) -> list[ResellerRef]:
        resellers = self._resellers()
        if search:
            resellers = resellers.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(referral_code=search)
            )
        return [_reseller_ref(reseller) for reseller in resellers.order_by("first_name")[:limit]]

    @staticmethod
    def _resellers() -> QuerySet[User]:
        return User.objects.filter(role=Role.RESELLER.value, is_active=True)


def _reseller_ref(user: User) -> ResellerRef:
    return ResellerRef(
        id=user.pk,
        name=user.get_full_name() or user.email,
        email=user.email,
        availability=Availability(user.availability),
    )


class DirectorySelector:
    def staff_ids(self) -> list[int]:
        return list(
            User.objects.filter(
                role__in=[Role.MANAGER.value, Role.ADMIN.value], is_active=True
            ).values_list("pk", flat=True)
        )

    def contacts(self, user_ids: Iterable[int]) -> dict[int, Contact]:
        users = User.objects.filter(pk__in=set(user_ids), is_active=True).only(
            "pk", "email", "first_name", "role"
        )
        return {
            user.pk: Contact(
                id=user.pk, email=user.email, first_name=user.first_name, role=user.account_role
            )
            for user in users
        }

    def subscribed(
        self,
        user_ids: Iterable[int],
        topic: NotificationTopic,
        channel: NotificationChannel,
    ) -> set[int]:
        wanted = set(user_ids)
        stored = dict(
            NotificationPreference.objects.filter(user_id__in=wanted).values_list(
                "user_id", "preferences"
            )
        )
        default = DEFAULT_PREFERENCES[topic][channel]
        subscribed = {
            user_id
            for user_id in wanted
            if bool(stored.get(user_id, {}).get(topic.value, {}).get(channel.value, default))
        }
        if topic is NotificationTopic.PROMOTIONS:
            # commercial offers only reach those who gave the marketing consent (policy §8)
            subscribed &= set(
                Consent.objects.filter(
                    user_id__in=subscribed,
                    kind=ConsentKind.MARKETING.value,
                    withdrawn_at__isnull=True,
                ).values_list("user_id", flat=True)
            )
        return subscribed


class SellerSelector:
    def profile(self, user_id: int) -> SellerProfile | None:
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            return None
        return SellerProfile(
            id=user.pk,
            name=user.get_full_name() or user.email,
            role=user.account_role,
        )

    def names(self, user_ids: Iterable[int]) -> dict[int, str]:
        users = User.objects.filter(pk__in=set(user_ids)).only(
            "pk", "first_name", "last_name", "email"
        )
        return {user.pk: user.get_full_name() or user.email for user in users}

    def resellers(self) -> list[SellerProfile]:
        return [
            SellerProfile(
                id=user.pk,
                name=user.get_full_name() or user.email,
                role=user.account_role,
            )
            for user in User.objects.filter(role=Role.RESELLER.value).order_by("first_name")
        ]


RESELLER_ORDERING = {
    ResellerOrdering.NAME: ("first_name", "last_name", "pk"),
    ResellerOrdering.NEWEST: ("-date_joined", "-pk"),
    ResellerOrdering.OLDEST: ("date_joined", "pk"),
    ResellerOrdering.MOST_INVITED: ("-invited_count", "first_name", "pk"),
}


class ResellerDirectorySelector:
    def page(
        self, filters: ResellerFilters, *, offset: int, limit: int
    ) -> tuple[list[ResellerAccount], int]:
        resellers = self._filtered(filters)
        page = resellers.order_by(*RESELLER_ORDERING[filters.ordering])[offset : offset + limit]
        return [to_reseller_account(user) for user in page], resellers.count()

    def one(self, reseller_id: int) -> ResellerAccount:
        user = self._resellers().filter(pk=reseller_id).first()
        if user is None:
            raise ResellerNotFound
        return to_reseller_account(user)

    def ids(self) -> list[int]:
        return list(User.objects.filter(role=Role.RESELLER.value).values_list("pk", flat=True))

    def is_reseller(self, email: str) -> bool:
        return self._resellers().filter(email__iexact=email.strip(), is_active=True).exists()

    def counts(self) -> ResellerCounts:
        totals = User.objects.filter(role=Role.RESELLER.value).aggregate(
            total=Count("pk"), active=Count("pk", filter=Q(is_active=True))
        )
        invited = User.objects.filter(invited_by__role=Role.RESELLER.value).count()
        return ResellerCounts(
            total=totals["total"], active=totals["active"], invited_clients=invited
        )

    def invitees(self, reseller_id: int, *, offset: int, limit: int) -> tuple[list[Invitee], int]:
        invitees = User.objects.filter(invited_by_id=reseller_id)
        page = invitees.order_by("-date_joined", "-pk")[offset : offset + limit]
        return [_invitee(user) for user in page], invitees.count()

    def invitee_ids(self, reseller_id: int) -> list[int]:
        return list(User.objects.filter(invited_by_id=reseller_id).values_list("pk", flat=True))

    def _filtered(self, filters: ResellerFilters) -> QuerySet[User]:
        resellers = self._resellers()
        if filters.active is not None:
            resellers = resellers.filter(is_active=filters.active)
        if filters.manager_id is not None:
            resellers = resellers.filter(manager_id=filters.manager_id)
        if filters.search:
            term = filters.search.strip()
            resellers = resellers.filter(
                Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(email__icontains=term)
                | _phone_matches(term)
                | Q(referral_code=term)
            )
        return resellers

    @staticmethod
    def _resellers() -> QuerySet[User]:
        return (
            User.objects.filter(role=Role.RESELLER.value)
            .select_related("manager")
            .annotate(invited_count=Count("invitees", distinct=True))
        )


def to_reseller_account(user: User) -> ResellerAccount:
    manager = user.manager
    return ResellerAccount(
        id=user.pk,
        first_name=user.first_name,
        last_name=user.last_name,
        name=user.get_full_name() or user.email,
        email=user.email,
        phone_number=user.phone_number,
        avatar=user.avatar,
        referral_code=user.referral_code,
        availability=Availability(user.availability),
        is_active=user.is_active,
        manager=ManagerRef(id=manager.pk, name=manager.get_full_name() or manager.email)
        if manager
        else None,
        date_joined=user.date_joined,
        last_seen_at=user.last_seen_at,
        invited_count=getattr(user, "invited_count", 0),
    )


def _invitee(user: User) -> Invitee:
    return Invitee(
        id=user.pk,
        name=user.get_full_name() or user.email,
        email=user.email,
        joined_at=user.date_joined,
    )


# phones are stored as +243…: "0812345678" finds "+243812345678", and a partial number typed in
# the national form ("081234") is looked up without its trunk 0 or country code
def _phone_matches(term: str) -> Q:
    phone = parse_drc_phone(term)
    if phone:
        return Q(phone_number=phone)
    return Q(phone_number__icontains=phone_search_fragment(term) or term)


class UserDirectorySelector:
    def page(
        self, filters: UserFilters, *, offset: int, limit: int
    ) -> tuple[list[UserRow], int, dict[str, int]]:
        users = self._filtered(filters)
        page = users.order_by("-date_joined", "-pk")[offset : offset + limit]
        return [to_user_row(user) for user in page], users.count(), self.counts()

    def one(self, user_id: int) -> UserRow:
        user = self._users().filter(pk=user_id).first()
        if user is None:
            raise UserNotFound
        return to_user_row(user)

    def counts(self) -> dict[str, int]:
        totals = User.objects.filter(deleted_at__isnull=True).aggregate(
            **{role.value: Count("pk", filter=Q(role=role.value)) for role in ACCOUNT_ROLES}
        )
        return {name: int(value) for name, value in totals.items()}

    def _filtered(self, filters: UserFilters) -> QuerySet[User]:
        users = self._users()
        if filters.role is not None:
            users = users.filter(role=filters.role.value)
        if filters.active is not None:
            users = users.filter(is_active=filters.active)
        if filters.search:
            term = filters.search.strip()
            users = users.filter(
                Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(email__icontains=term)
                | _phone_matches(term)
                | Q(referral_code=term)
            )
        return users

    @staticmethod
    def _users() -> QuerySet[User]:
        verified = EmailAddress.objects.filter(user=OuterRef("pk"), verified=True)
        return (
            User.objects.filter(deleted_at__isnull=True)
            .select_related("invited_by")
            .annotate(email_verified=Exists(verified))
        )


def to_user_row(user: User) -> UserRow:
    inviter = user.invited_by
    return UserRow(
        id=user.pk,
        first_name=user.first_name,
        last_name=user.last_name,
        name=user.get_full_name() or user.email,
        email=user.email,
        phone_number=user.phone_number,
        avatar=user.avatar,
        role=user.account_role,
        referral_code=user.referral_code,
        invited_by=InviterRef(
            id=inviter.pk,
            name=inviter.get_full_name() or inviter.email,
            referral_code=inviter.referral_code,
        )
        if inviter
        else None,
        is_active=user.is_active,
        email_verified=bool(getattr(user, "email_verified", False)),
        date_joined=user.date_joined,
        last_login=user.last_login,
    )
