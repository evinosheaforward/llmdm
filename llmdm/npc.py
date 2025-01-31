import json
from dataclasses import asdict, dataclass


@dataclass
class NPC:
    name: str = "<npc's name>"
    description: str = "<description>"
    location_name: str = "Location they are found"
    behavior_type: str = "<general demeantor toward the player>"
    appearance: str = "<description of character appearance>"
    bonds: str = "<description of character bonds>"
    ideals: str = "<description of character ideals>"
    flaws: str = "<description of character flaws>"
    role: str = "<occupation/story role>"
    traits: str = "<sentence of character traits of the npc>"
    gender: str = "<gender>"
    affinity_score: int = 0
    affinity_type: str = "<fixed | flexible | deciding>"

    def debug_describe(self):
        print(json.dumps(asdict(self), indent=2))

    def describe(self) -> str:
        return f"""
{self.name}: {self.description}
with these traits:
bonds: {self.bonds}
ideals: {self.ideals}
flaws: {self.flaws}
role: {self.role}
traits: {self.traits}
gender: {self.gender}
"""

    @property
    def relationship_status(self):
        if self.affinity_score <= -50:
            return "Enemy"
        elif -49 <= self.affinity_score <= -10:
            return "Rival"
        elif -9 <= self.affinity_score <= 9:
            return "Neutral"
        elif 10 <= self.affinity_score <= 49:
            return "Friendly"
        elif 50 <= self.affinity_score <= 89:
            return "Ally"
        elif 90 <= self.affinity_score:
            return "Loved One"
