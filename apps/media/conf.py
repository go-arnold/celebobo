from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class MediaSettings:
    storage: str = "cloudinary"
    cloud_name: str = ""
    api_key: str = ""
    api_secret: str = ""
    root_folder: str = "celebobo"


def media_settings() -> MediaSettings:
    return load_section("MEDIA", MediaSettings)
