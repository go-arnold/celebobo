from collections.abc import Sequence

from django.db import transaction

from apps.media.domain.errors import UploadNotAllowed
from apps.media.domain.policies import UploadPolicy, UploadPurpose, policy_for
from apps.media.domain.uploads import CompletedUpload, StoredMedia, UploadSignature
from apps.media.selectors import to_stored
from apps.media.services.cleanup import OrphanSweeper, OwnerFilesEraser, SweepResult
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

    def complete_many(self, actor: Actor, uploads: Sequence[CompletedUpload]) -> list[StoredMedia]:
        with transaction.atomic():
            return [self.complete(actor, upload) for upload in uploads]

    def _allowed_policy(self, actor: Actor, purpose: UploadPurpose) -> UploadPolicy:
        policy = policy_for(purpose)
        if not self._permissions.allows(actor, policy.permission):
            raise UploadNotAllowed
        return policy


@logged_facade
class MediaMaintenanceFacade:
    def __init__(self, *, sweeper: OrphanSweeper) -> None:
        self._sweeper = sweeper

    def sweep_orphans(self) -> SweepResult:
        return self._sweeper.sweep()


# retention of client accounts (privacy policy, section 6): the files of an anonymised client.
# Each file is destroyed at the storage before its row goes; a storage failure rolls back the
# account's whole erasure, retried on the next run (destroying a file twice is harmless).
@logged_facade
class MediaPrivacyFacade:
    def __init__(self, *, eraser: OwnerFilesEraser) -> None:
        self._eraser = eraser

    def forget_owner(self, user_id: int) -> int:
        with transaction.atomic():
            return self._eraser.erase(user_id)
