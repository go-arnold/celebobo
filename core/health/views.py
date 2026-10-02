from http import HTTPStatus

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.conf import core_settings
from core.health.checks import run_checks


class _OpenProbe(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = ()


@extend_schema(exclude=True)
class LivenessView(_OpenProbe):
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


@extend_schema(exclude=True)
class ReadinessView(_OpenProbe):
    def get(self, request: Request) -> Response:
        results = run_checks(core_settings().health_checks)
        healthy = all(result.healthy for result in results)
        return Response(
            {
                "status": "ok" if healthy else "unavailable",
                "checks": {
                    result.name: {
                        "healthy": result.healthy,
                        "duration_ms": result.duration_ms,
                        "error": result.error,
                    }
                    for result in results
                },
            },
            status=HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE,
        )
