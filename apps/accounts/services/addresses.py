from typing import Any

from apps.accounts.domain.commands import AddressChanges, AddressFields
from apps.accounts.domain.errors import AddressBookFull, AddressNotFound
from apps.accounts.domain.normalization import clean_text
from apps.accounts.models import Address
from apps.accounts.services.contracts import AddressStore
from core.domain.values import provided

DEFAULT_ADDRESS_LIMIT = 20


class AddressBookService:
    def __init__(self, store: AddressStore, *, limit: int = DEFAULT_ADDRESS_LIMIT) -> None:
        self._store = store
        self._limit = limit

    def add(self, user_id: int, fields: AddressFields) -> Address:
        self._store.lock_owner(user_id)
        count = self._store.count_for(user_id)
        if count >= self._limit:
            raise AddressBookFull
        make_default = fields.is_default or count == 0
        if make_default:
            self._store.clear_default(user_id)
        values = _clean(
            {
                "label": fields.label,
                "recipient": fields.recipient,
                "phone": fields.phone,
                "line1": fields.line1,
                "quarter": fields.quarter,
                "city": fields.city,
                "country": fields.country,
            }
        )
        return self._store.create(user_id, **values, is_default=make_default)

    def update(self, user_id: int, address_id: int, changes: AddressChanges) -> Address:
        address = self._get(user_id, address_id)
        values = _clean(provided(changes))
        for name, value in values.items():
            setattr(address, name, value)
        if values:
            self._store.save(address, fields=values)
        return address

    def remove(self, user_id: int, address_id: int) -> None:
        self._store.lock_owner(user_id)
        address = self._get(user_id, address_id)
        was_default = address.is_default
        self._store.delete(address)
        if was_default and (successor := self._store.newest_for(user_id)):
            successor.is_default = True
            self._store.save(successor, fields=("is_default",))

    def set_default(self, user_id: int, address_id: int) -> Address:
        self._store.lock_owner(user_id)
        address = self._get(user_id, address_id)
        if not address.is_default:
            self._store.clear_default(user_id)
            address.is_default = True
            self._store.save(address, fields=("is_default",))
        return address

    def _get(self, user_id: int, address_id: int) -> Address:
        address = self._store.get_for(user_id, address_id, for_update=True)
        if address is None:
            raise AddressNotFound
        return address


def _clean(values: Any) -> dict[str, Any]:
    return {
        name: value.value if name == "label" else clean_text(value)
        for name, value in dict(values).items()
    }
