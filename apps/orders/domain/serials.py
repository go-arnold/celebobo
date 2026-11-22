"""Serial numbers and IMEIs of the units sold (warranty policy: a return must bring "the same serial
number or IMEI as on the invoice"), and the warranty dates printed with them."""

import calendar
import re
from datetime import date

# warranty policy: a 7-day trial (art. 59 of the Code du numérique), then the CeLE BoBO warranty,
# one month, both counted from the delivery
TRIAL_DAYS = 7
WARRANTY_MONTHS = 1

IMEI_LENGTH = 15
# letters, digits and the separators makers print (S/N "R58N12ABC3D", "C02-XY1.2/3")
_SERIAL = re.compile(r"^[A-Z0-9][A-Z0-9./-]{3,39}$")
_DIGITS = re.compile(r"^[0-9]+$")


def normalize(raw: str) -> str:
    """Upper case, without spaces: "35 209900 176148 1" and "352099001761481" are the same IMEI."""
    return "".join(raw.split()).upper()


def luhn_valid(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 1:
            # every second digit from the right is doubled, its digits summed (12 -> 1 + 2)
            value = sum(divmod(value * 2, 10))
        total += value
    return total % 10 == 0


def problem(serial: str) -> str | None:
    """Why a normalised serial is refused, or None. 15 digits is an IMEI: its check digit must be
    right (a typo is caught before it is printed on the invoice)."""
    if _DIGITS.match(serial) and len(serial) == IMEI_LENGTH:
        return None if luhn_valid(serial) else "IMEI invalide : vérifiez les 15 chiffres."
    if not _SERIAL.match(serial):
        return "Numéro invalide : 4 à 40 lettres ou chiffres (tirets, points et barres permis)."
    return None


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def warranty_end(delivered_on: date) -> date:
    return add_months(delivered_on, WARRANTY_MONTHS)
