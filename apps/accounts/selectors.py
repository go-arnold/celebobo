from collections.abc import Iterable

from allauth.account.models import EmailAddress
from django.db.models import Count, Q, QuerySet

from apps.accounts.domain.enums import (
    AddressLabel,
    Availability,
    NotificationChannel,
    NotificationTopic,
)
from apps.accounts.domain.errors import AddressNotFound, UserNotFound
from apps.accounts.domain.preferences import DEFAULT_PREFERENCES
from apps.accounts.domain.read_models import (
    AddressView,
    Contact,
    Profile,
    ReferralCheck,
    ResellerProfile,
    ResellerRef,
    SellerProfile,
)
from apps.accounts.models import Address, NotificationPreference, User
from core.authz.catalog import PermissionCatalog
from core.domain.actor import Role


class ProfileSelector:
    def __init__(self, catalog: PermissionCatalog) -> None:
        self._catalog = catalog

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
        commission_rate=user.commission_rate,
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
        return {
            user_id
            for user_id in wanted
            if bool(stored.get(user_id, {}).get(topic.value, {}).get(channel.value, default))
        }


class SellerSelector:
    def profile(self, user_id: int) -> SellerProfile | None:
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            return None
        return SellerProfile(
            id=user.pk,
            name=user.get_full_name() or user.email,
            role=user.account_role,
            commission_rate=user.commission_rate,
        )

    def resellers(self) -> list[SellerProfile]:
        return [
            SellerProfile(
                id=user.pk,
                name=user.get_full_name() or user.email,
                role=user.account_role,
                commission_rate=user.commission_rate,
            )
            for user in User.objects.filter(role=Role.RESELLER.value).order_by("first_name")
        ]
