"""Base model and lenient field types shared by every generated model."""

from __future__ import annotations

import datetime as dt
from typing import Any, Iterator, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, model_validator
from typing_extensions import Annotated

__all__ = ["AgencyZoomModel", "OptBool", "OptFloat", "OptInt"]

_SECRET_NAMES = frozenset(
    {
        "password",
        "oldpassword",
        "newpassword",
        "jwt",
        "token",
        "accesstoken",
        "refreshtoken",
        "apitoken",
    }
)


class AgencyZoomModel(BaseModel):
    """Base class for all request and response models.

    * Attributes are snake_case; the camelCase API names are aliases, and both
      spellings are accepted on input.
    * Unknown fields are kept (``extra="allow"``) so new API fields are never lost
      and undocumented request fields can still be sent.
    * ``date``/``datetime`` values are sent as ISO-8601 strings, and numbers are
      accepted for string fields (e.g. a ZIP code or phone number given as an int).
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        protected_namespaces=(),
        use_enum_values=True,
        coerce_numbers_to_str=True,
        hide_input_in_errors=True,
        # Validators are built on first use, keeping `import agencyzoom` fast even
        # though the API has 230+ schemas.
        defer_build=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _dates_to_iso(cls, data: Any) -> Any:
        if isinstance(data, dict) and any(isinstance(v, (dt.date, list)) for v in data.values()):
            return {key: _iso(value) for key, value in data.items()}
        return data

    def to_api(self) -> dict[str, Any]:
        """Serialise to the JSON payload AgencyZoom expects (camelCase, unset fields omitted)."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)

    def __repr_args__(self) -> Iterator[tuple[str | None, Any]]:
        # Upstream may return a supported token alias as an extra field rather
        # than the spec's declared `jwt`. Field(repr=False) cannot hide extras.
        for name, value in super().__repr_args__():
            if isinstance(name, str) and name.replace("_", "").lower() in _SECRET_NAMES:
                continue
            yield name, value

    def __getitem__(self, key: str) -> Any:
        """Dict-style access by API (camelCase) or Python (snake_case) name."""
        name = _alias_to_field(type(self)).get(key, key)
        if name in type(self).model_fields:
            return getattr(self, name)
        extra = self.model_extra or {}
        if key in extra:
            return extra[key]
        raise KeyError(key)


def _iso(value: Any) -> Any:
    if isinstance(value, dt.datetime):  # check first: datetime is a date subclass
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, list):
        return [_iso(v) for v in value]
    return value


def _alias_to_field(model: type) -> dict[str, str]:
    cache: dict[str, str] | None = model.__dict__.get("__az_alias_map__")
    if cache is None:
        cache = {f.alias: name for name, f in model.model_fields.items() if f.alias}  # type: ignore[attr-defined]
        model.__az_alias_map__ = cache  # type: ignore[attr-defined]
    return cache


def _blank_to_none(value: Any) -> Any:
    # AgencyZoom frequently returns "" for empty numeric/boolean fields.
    if isinstance(value, str) and not value.strip():
        return None
    return value


_BLANK_AS_NONE = BeforeValidator(_blank_to_none)

OptInt = Annotated[Optional[int], _BLANK_AS_NONE]
OptFloat = Annotated[Optional[float], _BLANK_AS_NONE]
OptBool = Annotated[Optional[bool], _BLANK_AS_NONE]
