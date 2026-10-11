from collections.abc import Sequence

import httpx

from apps.content.domain.errors import RevalidationFailed

SECRET_HEADER = "X-Revalidate-Secret"  # noqa: S105


class HttpRevalidator:
    def __init__(self, url: str, secret: str, *, timeout: float) -> None:
        self._url = url
        self._secret = secret
        self._timeout = timeout

    def revalidate(self, tags: Sequence[str]) -> None:
        try:
            response = httpx.post(
                self._url,
                json={"tags": list(tags)},
                headers={SECRET_HEADER: self._secret},
                timeout=self._timeout,
            )
        except httpx.HTTPError as error:
            raise RevalidationFailed(str(error)) from error
        if response.is_error:
            raise RevalidationFailed(f"{response.status_code} from the frontend")
