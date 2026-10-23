"""Field types shared by the API schemas."""

from typing import Annotated

from pydantic import BeforeValidator, Field, StringConstraints


def blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None
    return value


# Required short text, e.g. a name. Surrounding whitespace is stripped.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

# Optional text. Blank strings are stored as NULL.
OptionalName = Annotated[Name | None, BeforeValidator(blank_to_none)]
OptionalText = Annotated[str | None, BeforeValidator(blank_to_none)]

# Whole NTD amounts. The cap keeps values inside a PostgreSQL integer column.
NTD = Annotated[int, Field(ge=0, le=2_000_000_000)]
PositiveNTD = Annotated[int, Field(gt=0, le=2_000_000_000)]
Percent = Annotated[int, Field(ge=0, le=100)]
