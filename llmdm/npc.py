from dataclasses import dataclass


@dataclass
class NPC:
    name: str = "<npc's name>"
    description: str = "<description>"
    location_name: str = "Location they are found"
    behavior_type: str = "<general demeantor toward the player>"
    bonds: str = "<character bonds>"
    ideals: str = "<character ideals>"
    flaws: str = "<character flaws>"
    # faction: str = "<>"
