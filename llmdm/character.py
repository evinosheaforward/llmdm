from dataclasses import dataclass, field
from typing import List


@dataclass
class Character:
    name: str
    race: str
    character_class: str
    level: int = 1
    health_points: int = 100
    strength: int = 10
    dexterity: int = 10
    intelligence: int = 10
    charisma: int = 10
    inventory: List[str] = field(default_factory=list)
    abilities: List[str] = field(default_factory=list)

    def damage(self, damage: int):
        """Reduce health points when taking damage."""
        self.health_points -= damage
        if self.health_points < 0:
            self.health_points = 0
        print(
            f"{self.name} took {damage} damage and now has {self.health_points} health points."
        )

    def heal(self, amount: int):
        """Heal the character by increasing health points."""
        self.health_points += amount
        print(
            f"{self.name} healed for {amount} points and now has {self.health_points} health points."
        )

    def use_mana(self, cost: int):
        """Reduce mana points when using a spell or ability."""
        if cost > self.mana_points:
            print(f"{self.name} does not have enough mana.")
        else:
            self.mana_points -= cost
            print(
                f"{self.name} used {cost} mana and now has {self.mana_points} mana points."
            )
