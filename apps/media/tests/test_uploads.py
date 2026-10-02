import hashlib

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ManagerFactory, UserFactory
from apps.media.adapters.cloudinary import sign
from apps.media.models import UploadedMedia

pytestmark = pytest.mark.django_db

SECRET = "test-cloudinary-secret"
SIGN = "/api/v1/uploads/sign/"
COMPLETE = "/api/v1/uploads/complete/"


def authenticated(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


def cloudinary_response(public_id: str, version: int = 1712345678, **overrides):
    signature = hashlib.sha1(
        f"public_id={public_id}&version={version}{SECRET}".encode(), usedforsecurity=False
    ).hexdigest()
    return {
        "purpose": "avatar",
        "public_id": public_id,
        "version": version,
        "signature": signature,
        "format": "jpg",
        "bytes": 120_000,
        "width": 400,
        "height": 400,
        **overrides,
    }


class TestSigning:
    def test_signature_matches_cloudinary_algorithm(self):
        body = authenticated(UserFactory.create()).post(SIGN, {"purpose": "avatar"}).json()

        expected = sign(
            {
                "allowed_formats": body["allowed_formats"],
                "folder": "celebobo-test/avatars",
                "timestamp": body["timestamp"],
                "transformation": "c_fill,g_face,w_400,h_400/q_auto",
            },
            SECRET,
        )
        assert body["signature"] == expected
        assert body["upload_url"] == "https://api.cloudinary.com/v1_1/demo/image/upload"
        assert body["api_key"] == "123456789"
        assert body["max_bytes"] == 2 * 1024 * 1024
        assert "api_secret" not in body

    def test_product_images_need_catalogue_rights(self):
        client = authenticated(UserFactory.create()).post(SIGN, {"purpose": "product_image"})
        manager = authenticated(ManagerFactory.create()).post(SIGN, {"purpose": "product_image"})

        assert client.status_code == 403
        assert client.json()["code"] == "upload_not_allowed"
        assert manager.json()["folder"] == "celebobo-test/products"
        assert manager.json()["transformation"] == "c_limit,w_1600,h_1600/q_auto:good"

    def test_anonymous_cannot_sign(self):
        assert APIClient().post(SIGN, {"purpose": "avatar"}).status_code == 401

    @override_settings(MEDIA={"CLOUD_NAME": "", "API_KEY": "", "API_SECRET": ""})
    def test_unconfigured_storage(self):
        response = authenticated(UserFactory.create()).post(SIGN, {"purpose": "avatar"})

        assert response.status_code == 503
        assert response.json()["code"] == "storage_not_configured"

    def test_sign_skips_empty_values(self):
        assert sign({"a": "1", "b": ""}, "s") == hashlib.sha1(
            b"a=1s", usedforsecurity=False
        ).hexdigest()


class TestCompletion:
    def test_verified_upload_is_stored_with_a_rebuilt_url(self):
        user = UserFactory.create()

        response = authenticated(user).post(
            COMPLETE, cloudinary_response("celebobo-test/avatars/abc123")
        )

        assert response.status_code == 201
        assert response.json()["url"] == (
            "https://res.cloudinary.com/demo/image/upload/v1712345678/celebobo-test/avatars/abc123.jpg"
        )
        assert UploadedMedia.objects.get().owner == user

    def test_completion_is_idempotent_for_the_owner(self):
        api = authenticated(UserFactory.create())
        payload = cloudinary_response("celebobo-test/avatars/abc123")

        first = api.post(COMPLETE, payload).json()
        second = api.post(COMPLETE, payload).json()

        assert first["id"] == second["id"]

    def test_someone_else_cannot_claim_the_same_asset(self):
        payload = cloudinary_response("celebobo-test/avatars/abc123")
        authenticated(UserFactory.create()).post(COMPLETE, payload)

        response = authenticated(UserFactory.create()).post(COMPLETE, payload)

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_upload"

    @pytest.mark.parametrize(
        ("payload", "code"),
        [
            ({**cloudinary_response("celebobo-test/avatars/a"), "signature": "0" * 40}, "invalid_upload"),
            (cloudinary_response("celebobo-test/products/a"), "invalid_upload"),
            (cloudinary_response("elsewhere/avatars/a"), "invalid_upload"),
            (cloudinary_response("celebobo-test/avatars/a", format="gif"), "unsupported_format"),
            (cloudinary_response("celebobo-test/avatars/a", bytes=3 * 1024 * 1024), "upload_too_large"),
        ],
    )
    def test_rejections(self, payload, code):
        response = authenticated(UserFactory.create()).post(COMPLETE, payload)

        assert response.status_code == 400
        assert response.json()["code"] == code
        assert not UploadedMedia.objects.exists()
