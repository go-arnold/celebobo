from core.api.fields import MAX_INTEGER


class IdConverter:
    regex = "[0-9]{1,10}"

    def to_python(self, value: str) -> int:
        number = int(value)
        if number > MAX_INTEGER:
            raise ValueError(value)
        return number

    def to_url(self, value: int) -> str:
        return str(value)
