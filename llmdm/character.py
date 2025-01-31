import json
import logging
import os
from dataclasses import dataclass

from llmdm.utils import render_text

logger = logging.getLogger(__name__)


@dataclass
class Character:
    name: str = "<player character name>"
    description: str = "<player character description>"
    level: int = 1

    @classmethod
    def new(cls, llm, level=1):
        character = llm.generate_object(
            cls,
            fill_data={"level": level},
            prompt_user=True,
            extra_prompt="Please craft a character that is engaging and has depth, aligning closely with the player's input while adding creative elements to enhance their adventure. When naming the character, DO NOT include a nickname.",
        )
        render_text(f"You are {character.name}, {character.description}")
        return character

    @classmethod
    def from_save(cls, save_name):
        with open(os.path.join("saved", f"{save_name}.json")) as f:
            data = json.load(f)
        return cls(**data["PlayerCharacter"])

    def describe(self):
        return f"{self.name}: {self.description}"
