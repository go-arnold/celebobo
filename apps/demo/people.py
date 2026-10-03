import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DemoPerson:
    first_name: str
    last_name: str
    phone: str
    city: str = "Kinshasa"
    quarter: str = "Gombe"


MANAGERS = (
    DemoPerson("Joël", "Mpiana", "+243 81 100 0001"),
    DemoPerson("Sarah", "Kalala", "+243 81 100 0002", quarter="Limete"),
)

RESELLERS = (
    DemoPerson("Patrick", "Kabasele", "+243 82 200 0001", quarter="Bandalungwa"),
    DemoPerson("Grâce", "Ilunga", "+243 82 200 0002", city="Lubumbashi", quarter="Kampemba"),
    DemoPerson("Christian", "Mukendi", "+243 82 200 0003", quarter="Ngaliema"),
    DemoPerson("Ruth", "Tshibangu", "+243 82 200 0004", city="Goma", quarter="Himbi"),
)

CLIENTS = (
    DemoPerson("Aline", "Mbuyi", "+243 81 300 0001"),
    DemoPerson("Jonathan", "Kasongo", "+243 81 300 0002", quarter="Lingwala"),
    DemoPerson("Esther", "Mwamba", "+243 81 300 0003", quarter="Kintambo"),
    DemoPerson("Daniel", "Lukusa", "+243 81 300 0004", quarter="Kalamu"),
    DemoPerson("Merveille", "Ngoy", "+243 81 300 0005", city="Lubumbashi", quarter="Kenya"),
    DemoPerson("Fiston", "Kabila", "+243 81 300 0006", quarter="Matete"),
    DemoPerson("Sandra", "Nzuzi", "+243 81 300 0007", quarter="Barumbu"),
    DemoPerson("Hervé", "Mutombo", "+243 81 300 0008", city="Goma", quarter="Katindo"),
    DemoPerson("Prisca", "Kayembe", "+243 81 300 0009", quarter="Ngaba"),
    DemoPerson("Blaise", "Mbala", "+243 81 300 0010", quarter="Lemba"),
    DemoPerson("Nadège", "Kalonji", "+243 81 300 0011", city="Kisangani", quarter="Makiso"),
    DemoPerson("Cédric", "Banza", "+243 81 300 0012", quarter="Masina"),
    DemoPerson("Rebecca", "Lumbu", "+243 81 300 0013", quarter="Kasa-Vubu"),
    DemoPerson("Gloire", "Makiese", "+243 81 300 0014", city="Matadi", quarter="Nzanza"),
    DemoPerson("Divine", "Mpoyi", "+243 81 300 0015", quarter="Bumbu"),
)

APPLICANTS = (
    DemoPerson("Jérémie", "Kanku", "+243 82 400 0001", city="Kananga"),
    DemoPerson("Odile", "Masika", "+243 82 400 0002", city="Bukavu"),
    DemoPerson("Trésor", "Kibala", "+243 82 400 0003"),
)


def email_for(person: DemoPerson, domain: str) -> str:
    plain = unicodedata.normalize("NFKD", f"{person.first_name}.{person.last_name}".lower())
    return f"{''.join(c for c in plain if not unicodedata.combining(c))}@{domain}"
