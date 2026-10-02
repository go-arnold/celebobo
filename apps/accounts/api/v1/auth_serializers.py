from typing import Any

from dj_rest_auth.serializers import PasswordResetSerializer
from rest_framework import serializers

from apps.accounts.adapters.allauth import password_reset_url
from apps.accounts.api.v1.serializers import ProfileOutput
from apps.accounts.models import User
from apps.accounts.selectors import ProfileSelector
from core.authz.catalog import permission_catalog


class FrontendPasswordResetSerializer(PasswordResetSerializer):
    def get_email_options(self) -> dict[str, Any]:
        return {"url_generator": password_reset_url}


class SessionUserSerializer(serializers.Serializer[User]):
    def to_representation(self, instance: User) -> dict[str, Any]:
        profile = ProfileSelector(permission_catalog).profile(instance.pk)
        return dict(ProfileOutput(profile).data)
