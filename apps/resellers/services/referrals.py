from urllib.parse import quote

from apps.resellers.conf import ResellerSettings
from apps.resellers.domain.read_models import ReferralKit
from apps.resellers.services.contracts import QrRenderer


class ReferralKitBuilder:
    def __init__(self, qr: QrRenderer, settings: ResellerSettings, *, base_url: str) -> None:
        self._qr = qr
        self._settings = settings
        self._base_url = base_url.rstrip("/")

    def build(self, code: str) -> ReferralKit:
        link = f"{self._base_url}{self._settings.invite_path.format(code=code)}"
        text = self._settings.share_text.format(code=code, link=link)
        return ReferralKit(
            code=code,
            link=link,
            qr_svg=self._qr.svg_data_uri(link, scale=self._settings.qr_scale),
            share_text=text,
            whatsapp_url=self._settings.whatsapp_url.format(text=quote(text)),
        )
