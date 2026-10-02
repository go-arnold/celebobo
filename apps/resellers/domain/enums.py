from enum import StrEnum


class ApplicationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

    @property
    def label(self) -> str:
        return {"pending": "En attente", "approved": "Acceptée", "rejected": "Refusée"}[self.value]
