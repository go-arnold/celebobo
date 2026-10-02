from enum import StrEnum

ACTION_CODES = {"create": 0, "update": 1, "delete": 2, "access": 3}


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ACCESS = "access"

    @property
    def code(self) -> int:
        return ACTION_CODES[self.value]

    @classmethod
    def from_code(cls, code: int) -> "AuditAction":
        return next(action for action in cls if action.code == code)
