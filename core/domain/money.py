from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Self

CENT = Decimal("0.01")
DEFAULT_CURRENCY = "USD"
ISO_CODE_LENGTH = 3


class CurrencyMismatchError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        if len(self.currency) != ISO_CODE_LENGTH or not self.currency.isupper():
            raise ValueError(f"Invalid ISO 4217 currency code: {self.currency!r}")
        object.__setattr__(
            self, "amount", Decimal(str(self.amount)).quantize(CENT, rounding=ROUND_HALF_UP)
        )

    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> Self:
        return cls(Decimal(0), currency)

    @classmethod
    def total(cls, amounts: Iterable["Money"], currency: str = DEFAULT_CURRENCY) -> Self:
        result = cls.zero(currency)
        for amount in amounts:
            result = result + amount
        return result

    def __add__(self, other: "Money") -> Self:
        self._ensure_same_currency(other)
        return type(self)(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> Self:
        self._ensure_same_currency(other)
        return type(self)(self.amount - other.amount, self.currency)

    def __mul__(self, factor: int | Decimal) -> Self:
        return type(self)(self.amount * Decimal(factor), self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> Self:
        return type(self)(-self.amount, self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._ensure_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._ensure_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._ensure_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._ensure_same_currency(other)
        return self.amount >= other.amount

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def _ensure_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"{self.currency} != {other.currency}")
