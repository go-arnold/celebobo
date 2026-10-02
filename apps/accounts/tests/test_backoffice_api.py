import pytest
from django.contrib.auth.models import Group

from apps.accounts.domain.events import AvailabilityChanged, RoleChanged
from apps.accounts.facades import RealtimeAccessFacade
from apps.accounts.models import User
from core.container import container

pytestmark = pytest.mark.django_db


def role_url(user: User) -> str:
    return f"/api/v1/bo/users/{user.pk}/role/"


class TestRoleChange:
    def test_promoting_to_reseller_issues_a_code(
        self, as_user, admin_user, client_user, published_events
    ):
        response = as_user(admin_user).post(role_url(client_user), {"role": "reseller"})

        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "reseller"
        assert len(body["reseller"]["referral_code"]) == 4
        assert body["reseller"]["availability"] == "offline"
        client_user.refresh_from_db()
        assert client_user.is_staff is False
        assert list(client_user.groups.values_list("name", flat=True)) == ["reseller"]
        event = published_events.single(RoleChanged)
        assert (event.previous_role, event.role) == ("client", "reseller")

    def test_managers_get_admin_site_access(self, as_user, admin_user, reseller):
        as_user(admin_user).post(role_url(reseller), {"role": "manager"})

        reseller.refresh_from_db()
        assert reseller.is_staff is True
        assert list(reseller.groups.values_list("name", flat=True)) == ["manager"]

    def test_demotion_clears_role_groups(self, as_user, admin_user, manager):
        Group.objects.get_or_create(name="manager")[0].user_set.add(manager)

        as_user(admin_user).post(role_url(manager), {"role": "client"})

        manager.refresh_from_db()
        assert manager.groups.count() == 0
        assert manager.is_staff is False

    def test_same_role_is_a_no_op(self, as_user, admin_user, client_user, published_events):
        as_user(admin_user).post(role_url(client_user), {"role": "client"})

        assert published_events.of_type(RoleChanged) == []

    def test_admins_cannot_change_their_own_role(self, as_user, admin_user):
        response = as_user(admin_user).post(role_url(admin_user), {"role": "client"})

        assert response.status_code == 403
        assert response.json()["code"] == "own_role_change"

    @pytest.mark.parametrize("actor", ["client_user", "reseller", "manager"])
    def test_only_admins_manage_roles(self, request, as_user, actor):
        target = User.objects.create_user("target@celebobo.test", "Kinshasa-2026!")

        response = as_user(request.getfixturevalue(actor)).post(role_url(target), {"role": "admin"})

        assert response.status_code == 403

    def test_unknown_user(self, as_user, admin_user):
        response = as_user(admin_user).post("/api/v1/bo/users/999/role/", {"role": "client"})

        assert response.json()["code"] == "user_not_found"


class TestAvailability:
    url = "/api/v1/bo/me/availability/"

    def test_reseller_goes_online(self, as_user, reseller, published_events):
        response = as_user(reseller).patch(self.url, {"availability": "online"})

        assert response.json()["reseller"]["availability"] == "online"
        assert published_events.single(AvailabilityChanged).availability == "online"

    def test_clients_have_no_availability(self, as_user, client_user):
        assert as_user(client_user).patch(self.url, {"availability": "online"}).status_code == 403

    def test_managers_have_no_availability(self, as_user, manager):
        response = as_user(manager).patch(self.url, {"availability": "away"})

        assert response.json()["code"] == "not_a_reseller"


class TestWsTicket:
    def test_ticket_is_issued_once(self, as_user, client_user):
        response = as_user(client_user).post("/api/v1/auth/ws-ticket/")

        assert response.status_code == 201
        ticket = response.json()["ticket"]
        facade = container.resolve(RealtimeAccessFacade)
        assert facade.redeem_ticket(ticket) == client_user.pk
        assert facade.redeem_ticket(ticket) is None

    def test_requires_authentication(self, api):
        assert api.post("/api/v1/auth/ws-ticket/").status_code == 401
