from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.media.api.v1.serializers import CompleteInput, MediaOutput, SignatureOutput, SignInput
from apps.media.domain.policies import UploadPurpose
from apps.media.domain.uploads import CompletedUpload
from apps.media.facades import MediaFacade
from apps.media.permissions import MEDIA_UPLOAD
from core.api.views import UseCaseViewSet
from core.container import Inject


class UploadViewSet(UseCaseViewSet):
    action_permissions = {"sign": (MEDIA_UPLOAD,), "complete": (MEDIA_UPLOAD,)}
    throttle_scope = "uploads"
    media = Inject(MediaFacade)

    @extend_schema(request=SignInput, responses=SignatureOutput)
    def sign(self, request: Request) -> Response:
        purpose = UploadPurpose(self.validated(SignInput)["purpose"])
        return self.respond(SignatureOutput, self.media.sign(self.actor, purpose))

    @extend_schema(request=CompleteInput, responses={201: MediaOutput})
    def complete(self, request: Request) -> Response:
        upload = self.parse(CompleteInput, into=CompletedUpload)
        return self.respond(MediaOutput, self.media.complete(self.actor, upload), status=201)
