import pytest

from core.api.converters import IdConverter
from core.api.fields import MAX_INTEGER


def test_ids_within_range_are_converted():
    assert IdConverter().to_python("42") == 42
    assert IdConverter().to_url(42) == "42"


def test_ids_beyond_the_database_range_do_not_match():
    with pytest.raises(ValueError, match="2147483648"):
        IdConverter().to_python(str(MAX_INTEGER + 1))
