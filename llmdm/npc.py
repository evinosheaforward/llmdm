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
    role: str = "<occupation/story role>"
    traits: str = "<character traits of the npc>"
    gender: str = "<gender>"

    def describe(self) -> str:
        return f"""
{self.name}: {self.description}
with these traits:
bonds: {self.bonds}
ideals: {self.ideals}
flaws: {self.flaws}
roles: {self.role}
traits: {self.traits}
gender: {self.gender}
"""
