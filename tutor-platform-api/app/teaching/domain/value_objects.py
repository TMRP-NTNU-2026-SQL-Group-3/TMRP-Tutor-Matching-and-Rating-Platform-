from dataclasses import dataclass


@dataclass(frozen=True)
class EditLog:
    field_name: str
    old_value: str | None
    new_value: str | None
