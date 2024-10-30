import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from llmdm.npc import NPC


@dataclass
class Location:
    name: str = "<name>"
    description: str = "<description>"
    npcs: List["NPC"] = field(default_factory=list)
    parent_location: Optional[str] = None  # Name of the parent location
    sublocations: List[str] = field(default_factory=list)  # Names of sublocations
    location_type: str = "<Town, Forest, Dungeon, Cave, etc.>"
    attributes: str = "<comma separated keyword attributes>"

    def describe(self) -> str:
        description = ""
        for key in ("parent_location", "location_type", "attributes"):
            description += f"{key.replace('_', ' ')}: {getattr(self, key)}\n"
        return (
            f"""
name: {self.description}
        """
            + description
        )

    def debug_describe(self) -> str:
        self_dict = asdict(self)
        self_dict["npcs"] = [asdict(npc) for npc in self.npcs]
        print(json.dumps(self_dict, indent=2))
