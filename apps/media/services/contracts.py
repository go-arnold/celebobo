from typing import Protocol

from apps.media.domain.policies import UploadPolicy
from apps.media.domain.uploads import CompletedUpload, UploadSignature


class MediaStorage(Protocol):
    def sign_upload(self, policy: UploadPolicy, *, timestamp: int) -> UploadSignature: ...

    def verify(self, upload: CompletedUpload) -> bool: ...

    def folder_for(self, policy: UploadPolicy) -> str: ...

    def delivery_url(self, upload: CompletedUpload) -> str: ...
