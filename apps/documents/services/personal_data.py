import io
import json
import zipfile
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from apps.documents.domain.personal_data import (
    FORMAT_NAME,
    FORMAT_VERSION,
    HTML_NAME,
    JSON_NAME,
    README_NAME,
    DataSubject,
    instant,
    ordered_sections,
)
from apps.documents.domain.tables import RenderedFile
from apps.documents.services.contracts import PersonalDataCollector
from apps.documents.services.generators import JobOutput, JobRequest
from apps.documents.services.personal_data_html import render_html
from core.domain.errors import Unauthenticated
from core.registry import Registry

# one collector per app, registered under its section key (see SECTION_ORDER)
collector_registry: Registry[PersonalDataCollector] = Registry("personal data collector")

README = """Celebobo — vos données personnelles
====================================

Ce fichier ZIP contient les données que Celebobo garde sur votre compte, à la date de l'export
({generated}) :

- {html} : vos données lisibles dans un navigateur (ouvrez-le par un double clic) ;
- {json} : les mêmes données dans un format lisible par une machine (JSON), pour les conserver
  ou les transmettre à un autre service.

Les montants sont en dollars américains ($). Les dates du fichier JSON suivent la norme ISO 8601.

Vous pouvez aussi demander à tout moment l'accès à vos données, leur correction ou leur effacement
(politique de confidentialité, article 11) en écrivant à {contact}. Nous accusons réception sous
72 heures et répondons dans les 30 jours.

Gardez ce fichier en lieu sûr : il contient vos informations personnelles.
"""


class PersonalDataExport:
    """Gathers what every app holds about the owner of the request into one ZIP."""

    def __init__(
        self,
        collectors: Registry[PersonalDataCollector],
        branding: Mapping[str, str],
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._collectors = collectors
        self._branding = branding
        self._clock = clock

    def run(self, request: JobRequest) -> JobOutput:
        if request.actor.user_id is None:
            raise Unauthenticated
        subject = DataSubject(user_id=request.actor.user_id, role=request.actor.role)
        generated_at = self._clock()
        sections: dict[str, Any] = {}
        for key in ordered_sections(list(self._collectors)):
            content = self._collectors.create(key).collect(subject)
            if content is not None:
                sections[key] = content
        document = {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "generated_at": instant(generated_at),
            "user_id": subject.user_id,
            "data": sections,
        }
        stamp = generated_at.strftime("%Y%m%d-%H%M")
        return JobOutput(
            RenderedFile(
                content=self._archive(document),
                filename=f"celebobo-mes-donnees-{stamp}.zip",
                content_type="application/zip",
            ),
            {"sections": {key: _size(content) for key, content in sections.items()}},
        )

    def _archive(self, document: Mapping[str, Any]) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(JSON_NAME, json.dumps(document, ensure_ascii=False, indent=2))
            archive.writestr(HTML_NAME, render_html(document, company=self._branding))
            archive.writestr(
                README_NAME,
                README.format(
                    generated=document["generated_at"],
                    html=HTML_NAME,
                    json=JSON_NAME,
                    contact=self._branding.get("company_contact", ""),
                ),
            )
        return buffer.getvalue()


def _size(content: Any) -> int:
    return len(content) if isinstance(content, list) else 1
