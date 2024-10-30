from dataclasses import dataclass, field


@dataclass
class Quest:
    id: str = "Unique identifier for the quest"
    title: str = "Title of the quest"
    description: str = "Detailed description of the quest"
    objective: str = "Objective of the quest"
    # rewards: Dict[str, Any] = field(
    #     default_factory=lambda: {
    #         "experience": "Experience points awarded upon completion",
    #         "items": ["List of item IDs awarded"],
    #         "reputation": {
    #             "faction": "Faction affected",
    #             "amount": "Reputation change amount",
    #         },
    #     }
    # )
    giver: str = "Name of NPC who gave the quest"
    npcs_involved: list[str] = field(
        default_factory=["List of NPC names involved in the quest"]
    )
    locations: list[str] = field(
        default_factory=["List of location names relevant to the quest"]
    )

    status: str = (
        "<Current status of the quest ('Available', 'In Progress', 'Completed', 'Failed')>"
    )
