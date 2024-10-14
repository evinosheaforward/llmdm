import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Character:
    name: str = "<character name>"
    rpg_class: str = "<one of: fighter, wizard, rouge, priest>"
    description: str = "<character description>"
    level: int = 1

    @classmethod
    def new(cls, llm, level=1):
        character = llm.generate_object(cls, fill_data={"level": level}, prompt=True)
        # print(f"You are {character.name}: {character.description}")
        return character

    @classmethod
    def from_save(cls, save_name):
        with open(os.path.join("saved", f"{save_name}.json")) as f:
            data = json.load(f)
        return cls(**data["PlayerCharacter"])
