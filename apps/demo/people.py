import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DemoPerson:
    first_name: str
    last_name: str
    phone: str
    city: str = "Bukavu"
    quarter: str = "Ibanda"


MANAGERS = (
    DemoPerson("Joël", "Mpiana", "+243 81 100 0001"),
    DemoPerson("Sarah", "Kalala", "+243 81 100 0002", city="Goma", quarter="Himbi"),
)

RESELLERS = (
    DemoPerson("Patrick", "Kabasele", "+243 82 200 0001", quarter="Kadutu"),
    DemoPerson("Grâce", "Ilunga", "+243 82 200 0002", city="Goma", quarter="Les Volcans"),
    DemoPerson("Christian", "Mukendi", "+243 82 200 0003", city="Uvira", quarter="Kalundu"),
    DemoPerson("Ruth", "Tshibangu", "+243 82 200 0004", city="Goma", quarter="Katindo"),
)

CLIENTS = (
    DemoPerson("Aline", "Mbuyi", "+243 81 300 0001"),
    DemoPerson("Jonathan", "Kasongo", "+243 81 300 0002", city="Goma", quarter="Himbi"),
    DemoPerson("Esther", "Mwamba", "+243 81 300 0003", quarter="Nyalukemba"),
    DemoPerson("Daniel", "Lukusa", "+243 81 300 0004", city="Goma", quarter="Mabanga"),
    DemoPerson("Merveille", "Ngoy", "+243 81 300 0005", quarter="Kadutu"),
    DemoPerson("Fiston", "Kabila", "+243 81 300 0006", city="Sake", quarter="Centre"),
    DemoPerson("Sandra", "Nzuzi", "+243 81 300 0007", city="Goma", quarter="Katindo"),
    DemoPerson("Hervé", "Mutombo", "+243 81 300 0008", quarter="Bagira"),
    DemoPerson("Prisca", "Kayembe", "+243 81 300 0009", city="Goma", quarter="Les Volcans"),
    DemoPerson("Blaise", "Mbala", "+243 81 300 0010", city="Kavumu", quarter="Centre"),
    DemoPerson("Nadège", "Kalonji", "+243 81 300 0011", city="Kisangani", quarter="Makiso"),
    DemoPerson("Cédric", "Banza", "+243 81 300 0012", city="Goma", quarter="Mabanga"),
    DemoPerson("Rebecca", "Lumbu", "+243 81 300 0013", quarter="Muhumba"),
    DemoPerson("Gloire", "Makiese", "+243 81 300 0014", city="Lubumbashi", quarter="Kenya"),
    DemoPerson("Divine", "Mpoyi", "+243 81 300 0015", city="Goma", quarter="Himbi"),
)

APPLICANTS = (
    DemoPerson("Jérémie", "Kanku", "+243 82 400 0001", city="Kananga"),
    DemoPerson("Odile", "Masika", "+243 82 400 0002", city="Uvira"),
    DemoPerson("Trésor", "Kibala", "+243 82 400 0003", city="Goma"),
)


def email_for(person: DemoPerson, domain: str) -> str:
    plain = unicodedata.normalize("NFKD", f"{person.first_name}.{person.last_name}".lower())
    return f"{''.join(c for c in plain if not unicodedata.combining(c))}@{domain}"
