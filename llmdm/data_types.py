import json
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Optional


@dataclass
class Entity:
    _id: Optional[str] = None
    _key: Optional[str] = None
    _rev: Optional[str] = None
    name: str = ""
    description: str = ""


@dataclass
class Person(Entity):
    pass


@dataclass
class Place(Entity):
    pass


@dataclass
class Object(Entity):
    pass


@dataclass
class Relation:
    _id: Optional[str] = None
    _key: Optional[str] = None
    _rev: Optional[str] = None
    _from: str = ""
    _to: str = ""
    description: str = ""


def prompt_dataclass(cls):
    """
    Prompt the user for input for each field of the dataclass `cls` and return an instance of `cls`.
    Assumes all fields are strings and required.

    Parameters:
    - cls: The dataclass type to instantiate.

    Returns:
    - An instance of `cls` with fields populated from user input.
    """
    if not is_dataclass(cls):
        raise ValueError("The provided class must be a dataclass.")

    field_values = {}
    for field in fields(cls):
        if ignore_field(field.name):
            continue
        # Since all fields are strings and required, we can simply prompt for each one
        while True:
            user_input = input(f"Enter value for {field.name}: ").strip()
            if user_input:
                field_values[field.name] = user_input
                break
    return cls(**field_values)


def data_type_from_str(entity_name: str) -> type:
    return {
        "person": Person,
        "place": Place,
        "object": Object,
        "relation": Relation,
    }[entity_name.split("/")[0].lower().strip()]


def str_dataclass(entity):
    return json.dumps(
        {k: v for k, v in asdict(entity).items() if not ignore_field(k)}, indent=2
    )


def ignore_field(f):
    return f.startswith("_") and f not in ["_from", "_to"]
