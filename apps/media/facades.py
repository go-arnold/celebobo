from django.db import transaction

from apps.media.domain.errors import UploadNotAllowed
from apps.media.domain.policies import UploadPolicy, UploadPurpose, policy_for
from apps.media.domain.uploads import CompletedUpload, StoredMedia, UploadSignature
from apps.media.selectors import to_stored
from apps.media.services.uploads import UploadService
from core.authz.catalog import PermissionCatalog
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.observability.decorators import logged_facade


@logged_facade
class MediaFacade:
    def __init__(self, *, uploads: UploadService, permissions: PermissionCatalog) -> None:
        self._uploads = uploads
        self._permissions = permissions

    def sign(self, actor: Actor, purpose: UploadPurpose) -> UploadSignature:
        return self._uploads.sign(self._allowed_policy(actor, purpose))

    def complete(self, actor: Actor, upload: CompletedUpload) -> StoredMedia:
        if actor.user_id is None:
            raise Unauthenticated
        policy = self._allowed_policy(actor, upload.purpose)
        with transaction.atomic():
            return to_stored(self._uploads.complete(actor.user_id, policy, upload))

    def _allowed_policy(self, actor: Actor, purpose: UploadPurpose) -> UploadPolicy:
        policy = policy_for(purpose)
        if not self._permissions.allows(actor, policy.permission):
            raise UploadNotAllowed
        return policy
