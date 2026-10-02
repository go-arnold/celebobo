from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class ResellerSettings:
    invite_path: str = "/inscription?code={code}"
    share_text: str = (
        "Rejoins-moi sur Celebobo et profite de mes conseils avec mon code {code} : {link}"
    )
    whatsapp_url: str = "https://wa.me/?text={text}"
    ranking_days: int = 30
    qr_scale: int = 8


def reseller_settings() -> ResellerSettings:
    return load_section("RESELLERS", ResellerSettings)
