from datetime import date

import pytest

from apps.content.policies import policies

pytestmark = pytest.mark.django_db

SLUGS = [
    "politique-de-confidentialite",
    "politique-de-livraison",
    "garantie-et-retours",
    "programme-de-fidelite",
    "politique-revendeurs",
]


def test_the_five_policies_are_published_with_their_version(api):
    listing = {page["slug"]: page for page in api.get("/api/v1/pages/").json()}
    delivery = api.get("/api/v1/pages/politique-de-livraison/").json()
    privacy = api.get("/api/v1/pages/politique-de-confidentialite/").json()

    assert set(SLUGS) <= set(listing)
    assert (delivery["version"], delivery["effective_on"]) == ("0.9.2", "2026-12-12")
    assert "code de livraison à 6 chiffres" in delivery["body"]
    assert "Contabo GmbH" in privacy["body"]
    assert listing["garantie-et-retours"]["version"] == "0.9"


def test_every_source_file_reads(api):
    sources = policies()

    assert [policy.slug for policy in sources] == SLUGS
    assert all(policy.body and policy.title for policy in sources)
    assert all(isinstance(policy.effective_on, date) for policy in sources)
    # the title and version line are page fields, not repeated in the text
    assert not any("— Celebobo" in policy.body.splitlines()[0] for policy in sources)
    assert not any("Version de test" in policy.body for policy in sources)


def test_staff_update_a_policy_and_its_version(api, as_user, manager):
    staff = as_user(manager)
    page = next(p for p in staff.get("/api/v1/bo/pages/").json() if p["slug"] == SLUGS[1])

    updated = staff.patch(
        f"/api/v1/bo/pages/{page['id']}/",
        {"version": "1.0", "effective_on": "2027-01-01"},
        format="json",
    )

    assert updated.status_code == 200, updated.json()
    assert (updated.json()["version"], updated.json()["effective_on"]) == ("1.0", "2027-01-01")
