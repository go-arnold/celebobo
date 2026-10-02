import pytest

pytestmark = pytest.mark.django_db

PAGES = "/api/v1/bo/pages/"
FAQ = "/api/v1/bo/faq/"
BANNERS = "/api/v1/bo/banners/"
SETTINGS = "/api/v1/bo/settings/"


def test_page_lifecycle_and_cache_invalidation(
    api, as_user, manager, django_capture_on_commit_callbacks
):
    staff = as_user(manager)
    created = staff.post(
        PAGES, {"slug": "guide", "title": "Guide", "body": "Étape 1"}, format="json"
    )
    page_id = created.json()["id"]
    api.force_authenticate(None)
    assert api.get("/api/v1/pages/guide/").json()["body"] == "Étape 1"

    with django_capture_on_commit_callbacks(execute=True):
        as_user(manager).patch(f"{PAGES}{page_id}/", {"body": "Étape 1 et 2"}, format="json")
    api.force_authenticate(None)
    refreshed = api.get("/api/v1/pages/guide/").json()["body"]
    duplicate = as_user(manager).post(
        PAGES, {"slug": "guide", "title": "Autre", "body": "x"}, format="json"
    )
    drafts = as_user(manager).get(PAGES).json()
    deleted = as_user(manager).delete(f"{PAGES}{page_id}/")

    assert created.status_code == 201
    assert refreshed == "Étape 1 et 2"
    assert duplicate.status_code == 409
    assert [page["slug"] for page in drafts] == ["guide"]
    assert deleted.status_code == 204
    assert (
        as_user(manager).patch(f"{PAGES}{page_id}/", {"title": "x"}, format="json").status_code
        == 404
    )


def test_faq_and_banners(as_user, manager):
    staff = as_user(manager)

    entry = staff.post(
        FAQ, {"question": "Délais ?", "answer": "24-48 h", "category": "Livraison"}, format="json"
    )
    banner = staff.post(
        BANNERS, {"title": "Soldes", "image": "https://img.test/a.jpg"}, format="json"
    )
    bad = staff.patch(
        f"{BANNERS}{banner.json()['id']}/",
        {"starts_at": "2026-05-02T00:00:00Z", "ends_at": "2026-05-01T00:00:00Z"},
        format="json",
    )

    assert entry.status_code == 201
    assert (
        staff.patch(f"{FAQ}{entry.json()['id']}/", {"position": 3}, format="json").json()[
            "position"
        ]
        == 3
    )
    assert len(staff.get(FAQ).json()) == 1
    assert banner.status_code == 201
    assert bad.status_code == 400
    assert "ends_at" in bad.json()["errors"]


def test_settings_are_admin_only_and_validated(api, as_user, admin, manager, site):
    staff = as_user(admin)

    updated = staff.patch(
        SETTINGS,
        {"usd_to_cdf": "2850.50", "payment_methods": ["cash", "cash", "airtel_money"]},
        format="json",
    )
    invalid = staff.patch(SETTINGS, {"payment_methods": ["bitcoin"]}, format="json")
    api.force_authenticate(None)
    public = api.get("/api/v1/settings/public/").json()

    assert updated.json()["usd_to_cdf"] == "2850.50"
    assert updated.json()["payment_methods"] == ["cash", "airtel_money"]
    assert updated.json()["newsletter_code"] == "BIENVENUE10"
    assert invalid.status_code == 400
    assert public["usd_to_cdf"] == "2850.50"
    assert as_user(manager).get(SETTINGS).status_code == 403


def test_resellers_cannot_edit_content(as_user, reseller):
    assert as_user(reseller).post(PAGES, {}, format="json").status_code == 403
