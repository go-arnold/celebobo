import csv
import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from apps.catalog.domain.management import ProductChanges, ProductDraft
from apps.documents.domain.errors import InvalidImportFile
from apps.documents.services.contracts import ProductCatalog
from apps.documents.services.generators import JobOutput, JobRequest
from core.domain.errors import DomainError

REQUIRED_COLUMNS = frozenset({"name", "category", "price"})
KNOWN_COLUMNS = REQUIRED_COLUMNS | {
    "slug",
    "description",
    "sale_price",
    "cost_price",
    "stock",
    "stock_threshold",
    "is_active",
}
TRUE_VALUES = frozenset({"1", "true", "oui", "yes", "vrai"})
FALSE_VALUES = frozenset({"0", "false", "non", "no", "faux"})
MAX_REPORTED_ERRORS = 200
NAME_MAX_LENGTH = 255


class RowError(Exception):
    def __init__(self, messages: dict[str, str]) -> None:
        super().__init__(messages)
        self.messages = messages


@dataclass(frozen=True, slots=True)
class ImportLine:
    slug: str
    values: dict[str, Any]
    stock: int | None


def parse_csv(content: bytes, *, max_rows: int, max_bytes: int) -> list[dict[str, str]]:
    if len(content) > max_bytes:
        raise InvalidImportFile(f"Le fichier dépasse {max_bytes // 1000} Ko.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InvalidImportFile("Le fichier doit être encodé en UTF-8.") from error
    header = text.split("\n", 1)[0]
    delimiter = ";" if header.count(";") > header.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = {(name or "").strip().lower() for name in reader.fieldnames or []}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise InvalidImportFile(f"Colonnes manquantes : {', '.join(sorted(missing))}.")
    rows = [
        {(key or "").strip().lower(): (value or "").strip() for key, value in row.items()}
        for row in reader
    ]
    if not rows:
        raise InvalidImportFile("Le fichier ne contient aucune ligne.")
    if len(rows) > max_rows:
        raise InvalidImportFile(f"{max_rows} lignes maximum par import.")
    return rows


class ProductImport:
    def __init__(self, catalog: ProductCatalog, *, max_rows: int, max_bytes: int) -> None:
        self._catalog = catalog
        self._max_rows = max_rows
        self._max_bytes = max_bytes

    def run(self, request: JobRequest) -> JobOutput:
        rows = parse_csv(request.upload or b"", max_rows=self._max_rows, max_bytes=self._max_bytes)
        dry_run = bool(request.params.get("dry_run"))
        categories = self._catalog.category_ids()
        counts = {"created": 0, "updated": 0}
        errors: list[dict[str, Any]] = []
        for number, raw in enumerate(rows, start=2):
            try:
                line = _validate(raw, categories)
                product_id = self._catalog.product_id(line.slug) if line.slug else None
                if not dry_run:
                    self._apply(request, line, product_id)
                counts["updated" if product_id else "created"] += 1
            except RowError as error:
                errors.append({"row": number, "errors": error.messages})
            except DomainError as error:
                errors.append({"row": number, "errors": {"row": str(error.detail)}})
        return JobOutput(
            None,
            {
                **counts,
                "dry_run": dry_run,
                "rows": len(rows),
                "error_count": len(errors),
                "errors": errors[:MAX_REPORTED_ERRORS],
            },
        )

    def _apply(self, request: JobRequest, line: ImportLine, product_id: int | None) -> None:
        with transaction.atomic():
            if product_id is None:
                product_id = self._catalog.create(
                    request.actor,
                    ProductDraft(
                        name=line.values["name"],
                        description=line.values.get("description", ""),
                        category_id=line.values["category_id"],
                        price=line.values["price"],
                        sale_price=line.values.get("sale_price"),
                        cost_price=line.values.get("cost_price"),
                        stock_threshold=line.values.get("stock_threshold", 5),
                        is_active=line.values.get("is_active", True),
                    ),
                )
            else:
                self._catalog.update(request.actor, product_id, ProductChanges(**line.values))
            if line.stock is not None:
                self._catalog.set_stock(request.actor, product_id, line.stock)


def _validate(raw: dict[str, str], categories: dict[str, int]) -> ImportLine:
    problems: dict[str, str] = {}
    values: dict[str, Any] = {}
    _identity(raw, categories, values, problems)
    _prices(raw, values, problems)
    _settings(raw, values, problems)
    stock = _integer(raw["stock"], problems, "stock") if raw.get("stock") else None
    if problems:
        raise RowError(problems)
    return ImportLine(slug=raw.get("slug", ""), values=values, stock=stock)


def _identity(
    raw: dict[str, str],
    categories: dict[str, int],
    values: dict[str, Any],
    problems: dict[str, str],
) -> None:
    name = raw.get("name", "")
    if not name or len(name) > NAME_MAX_LENGTH:
        problems["name"] = f"Nom obligatoire ({NAME_MAX_LENGTH} caractères maximum)."
    else:
        values["name"] = name
    category = raw.get("category", "").lower()
    if category in categories:
        values["category_id"] = categories[category]
    else:
        problems["category"] = f"Catégorie inconnue : {category or '—'}."
    if raw.get("description"):
        values["description"] = raw["description"]


def _prices(raw: dict[str, str], values: dict[str, Any], problems: dict[str, str]) -> None:
    price = _decimal(raw.get("price"), problems, "price", required=True)
    if price is not None:
        values["price"] = price
    for field in ("sale_price", "cost_price"):
        if raw.get(field):
            amount = _decimal(raw.get(field), problems, field)
            if amount is not None:
                values[field] = amount
    sale_price = values.get("sale_price")
    if price is not None and sale_price is not None and sale_price >= price:
        problems["sale_price"] = "Le prix promo doit être inférieur au prix."


def _settings(raw: dict[str, str], values: dict[str, Any], problems: dict[str, str]) -> None:
    if raw.get("stock_threshold"):
        threshold = _integer(raw["stock_threshold"], problems, "stock_threshold")
        if threshold is not None:
            values["stock_threshold"] = threshold
    if raw.get("is_active"):
        flag = raw["is_active"].lower()
        if flag in TRUE_VALUES | FALSE_VALUES:
            values["is_active"] = flag in TRUE_VALUES
        else:
            problems["is_active"] = "Valeur attendue : 1 ou 0."


def _decimal(
    value: str | None, problems: dict[str, str], field: str, *, required: bool = False
) -> Decimal | None:
    if not value:
        if required:
            problems[field] = "Montant obligatoire."
        return None
    try:
        amount = Decimal(value.replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        problems[field] = "Montant invalide."
        return None
    if amount < 0 or amount != amount.quantize(Decimal("0.01")):
        problems[field] = "Montant invalide."
        return None
    return amount


def _integer(value: str, problems: dict[str, str], field: str) -> int | None:
    if not value.isdigit():
        problems[field] = "Nombre entier positif attendu."
        return None
    return int(value)
