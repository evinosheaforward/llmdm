import json
import logging
import os
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from json.decoder import JSONDecodeError

from llmdm.character import Character
from llmdm.generate import LLM
from llmdm.graph_client import GraphClient
from llmdm.location import Location
from llmdm.names import NAMES
from llmdm.nouns_lookup import ProperNounDB
from llmdm.npc import NPC
from llmdm.points_of_interest import (
    COMMON_LOCATIONS,
    ESSENTIAL_LOCATIONS,
    UNIQUE_LOCATIONS,
)
from llmdm.quest import Quest
from llmdm.sql_client import SQLClient
from llmdm.town_names import TOWN_NAMES
from llmdm.traits import TRAIT_TRIPLETS
from llmdm.utils import SAVE_DIR, render_text
from llmdm.vector_client import OpenSearchClient

logger = logging.getLogger(__name__)


@dataclass
class GameState:
    date: str = "<the in-game date>"
    location: str = "<current in-game location>"
    mode: str = "one of: free, combat, conversation"
    mode_data: dict = field(default_factory=lambda: {})
    active_quest: dict = field(default_factory=lambda: {})

    @classmethod
    def from_save(cls, save_name):
        with open(os.path.join("saved", f"{save_name}.json"), "r") as f:
            data = json.load(f)
        logger.debug(
            f"GameState.from_save - loaded json:\n{json.dumps(data, indent=2)}"
        )
        return cls(**data["GameState"])


@dataclass
class GameData:
    llm: LLM
    sql_db: SQLClient
    graph_db: GraphClient
    vector_db: OpenSearchClient
    game_state: GameState
    noun_db: ProperNounDB
    player_character: Character
    save_name: str

    def save(self):
        with open(os.path.join(SAVE_DIR, f"{self.save_name}.json"), "w") as f:
            save_data = {
                "GameState": asdict(self.game_state),
                "PlayerCharacter": asdict(self.player_character),
            }
            json.dump(save_data, f, indent=2)
        logger.debug(f"Saving data to file:\n{json.dumps(save_data, indent=2)}")

    @classmethod
    def new_game(cls, save_name: str):
        llm = LLM()
        character = Character.new(llm)
        new_storyline = llm.generate(
            """
Based on the following player character description, generate a short narrative for the small, rural village where the player starts their journey. The narrative should be rich in detail, include compelling plot hooks, and remain open-ended to encourage exploration. Include 1 or two plot hooks that could lead to quests for the player.
""",
            # f"""
            # Concept: {character.description}
            #
            # Please craft this narrative to align closely with the character's background, incorporating unique elements that will intrigue the player and set the stage for their adventure.
            #             """,
            system_instructions="""
You are a creative storyteller and world-builder for a text-based RPG game. Your task is to craft unique, engaging, and open-ended narratives that serve as starting points for players. These narratives should be inspired by the player's character description and set in a small town where the player's adventure begins. Include intriguing plot hooks and backstory elements without resolving the storyline, allowing for open-ended gameplay. Avoid clichés and ensure that each story is fresh and imaginative.
            """,
            max_new_tokens=256,
        )
        logger.debug(new_storyline)
        state = GameState(
            mode="free",
            location="",
            date="day 0, hour 0",
        )
        game_data = cls(
            llm=llm,
            sql_db=SQLClient(save_name),
            graph_db=GraphClient(save_name),
            vector_db=OpenSearchClient(save_name),
            game_state=state,
            noun_db=ProperNounDB(save_name),
            player_character=character,
            save_name=save_name,
        )
        render_text("\nGenerating..")
        starting_location = game_data.generate_town(
            town_input=f"Based on:\n{new_storyline}"
        )
        game_data.game_state.location = starting_location.name
        game_data.save()

        logger.debug(
            f"game_state: {json.dumps(asdict(game_data.game_state), indent=2)}"
        )
        render_text(
            f"You begin your story in {starting_location.name}:\n{starting_location.description}"
        )
        game_data.travel_to(starting_location)
        return game_data

    def transition_mode_to(self, mode: str, npc: NPC = None):
        # set time elapsed
        previous_mode = self.game_state.mode
        if previous_mode == "conversation":
            self.update_affinity_score()
            self.save_conversation()

        if mode == "conversation":
            self.game_state.mode_data = {"conversation": "", "npc": npc.name}
            self.start_conversation(npc)
        elif mode == "free":
            self.game_state.mode_data = {}

        self.game_state.mode = mode

    def generate_location(
        self,
        player_input: str = "",
        current_location: Location = None,
        destination: str = "",
        fill_data: dict = {},
    ):
        parent_location = None
        if destination == "leaving":
            extra_prompt = f"The player is leaving {current_location.name}, {current_location.description} and is going to:\n{player_input}"
        elif destination == "new sublocation":
            extra_prompt = f"The player is in {current_location.name}, {current_location.description} and is staying there, but going to:\n{player_input}"
            parent_location = current_location.name
        else:
            extra_prompt = player_input

        _fill_data = {
            "npcs": [],
            "parent_location": parent_location,
            "sublocations": [],
        }
        _fill_data.update(fill_data)
        new_location, nicknames = self.llm.generate_object(
            Location,
            fill_data=_fill_data,
            nicknames=True,
            extra_prompt=extra_prompt,
        )
        self.save_location(new_location, nicknames)
        return new_location

    def travel_to(self, new_location: Location, move_type: str = None):
        new_location = self.expand_location(new_location)
        if not self.game_state.location:
            travel_text = self.llm.generate(
                f"""
The player is beginning their game session in a new location. Describe the setting with immersive detail to introduce the player to the space.

- **Location Name**: {new_location.name}
- **location.location_type**: {new_location.location_type}
- **Location Description**: {new_location.description}

Create a description that emphasizes the atmosphere of the {new_location.location_type} and uses sensory details from the description to make the player feel present in {new_location.name}. Keep the description between two to four sentences.
                """,
                system_instructions="""
You are an assistant creating descriptive, immersive settings for a text-based RPG. Your task is to introduce the player to a location, using sensory-rich details that evoke the location’s mood and atmosphere.
Keep the description between two to four sentences, making it detailed yet concise to enhance player immersion.
                """,
                max_new_tokens=512,
            )

        else:
            current_location = self.sql_db.get_location(self.game_state.location)
            type_prompt = {
                "local": f"Focus on a small, immediate transition within {current_location.name}, emphasizing details like proximity and visible features in  the {current_location.location_type}",
                "child": f"Describe moving deeper within {current_location.name} to a more specific point, referencing key elements in both {current_location.name} and {new_location.name}.",
                "parent": f"Describe the player’s movement from {current_location.name} outward to the broader {new_location.name}, creating a sense of leaving the smaller space of {current_location.name}.",
                "nearby": f"Describe the journey between two nearby locations, incorporating the atmosphere of both {current_location.name} and {new_location.name}.",
            }.get(move_type)

            if move_type == "local":
                prompt = f"""
The player is moving within a location in a text-based RPG.

- **Current Location**:
  - Name: {current_location.name}
  - Type: {current_location.location_type}
  - Description: {current_location.description}

{type_prompt}
            """
            else:
                prompt = f"""
The player is moving from one location to another in a text-based RPG.

- **Origin Location**:
  - Name: {current_location.name}
  - Type: {current_location.location_type}
  - Description: {current_location.description}

- **Destination Location**:
  - Name: {new_location.name}
  - Type: {new_location.location_type}
  - Description: {new_location.description}

{type_prompt}

Describe the player’s movement from {current_location.name} to {new_location}. Use the characteristics of the {current_location.location_type} and the {new_location.location_type} to guide your description. Mention key details from each location to create a short, but immersive transition. Respond in one to three sentences.
                """
            travel_text = self.llm.generate(
                prompt=prompt,
                system_instructions="""
You are creating travel descriptions for a text-based RPG. When a player moves from one location to another, describe the transition in a way that captures the feel of both locations. Use the location names, types, and descriptions to set the scene, and incorporate motion verbs (like “stride,” “stroll,” “hurry”) that match the tone and setting. The descriptions should be short, vivid, and help the player imagine the journey.
                """,
                max_new_tokens=256,
            )
        travel_text = self.llm.remove_unfinished(travel_text, max_new_tokens=256)
        render_text(travel_text)
        render_text("----------")
        self.game_state.location = new_location.name
        self.describe_scene()

    def generate_npc(
        self,
        extra_prompt: str = "",
        player_input: str = None,
        fill_data: dict = {},
        prefill=True,
    ):
        if prefill:
            if "gender" not in fill_data:
                fill_data["gender"] = random.choices(
                    list(NAMES.keys()), weights=[0.47, 0.47, 0.06], k=1
                )[0]
            gender = fill_data["gender"]

            for _ in range(10):
                if "name" not in fill_data:
                    fill_data["name"] = random.choice(NAMES[gender])
                    name = fill_data["name"]
                if not self.sql_db.npc_name_used(name):
                    break

            if "traits" not in fill_data:
                fill_data["traits"] = random.choice(TRAIT_TRIPLETS)
            traits = fill_data["traits"]

            extra_prompt += f"""
The NPC is named {name}, they are {gender} presenting, and they have these traits:
{traits}
            """
        else:
            name = None

        # placeholders updated after initial generation
        fill_data["affinity_score"] = 0
        fill_data["affinity_type"] = "not set"

        if player_input:
            extra_prompt += f"The player gave this description of the NPC they are approaching: {player_input}"

        new_npc, nicknames = self.llm.generate_object(
            NPC,
            fill_data=fill_data,
            nicknames=True,
            extra_prompt=extra_prompt,
            name=name,
        )
        new_npc.affinity_score, new_npc.affinity_type = self.llm.generate_affinity_data(
            new_npc, self.player_character
        )
        self.save_npc(new_npc, nicknames)
        return new_npc

    def respond_as_npc_to_leaving(self, player_input: str):
        self.respond_as_npc(
            f'The player leaves the conversation saying: "{player_input}"'
        )

    def respond_as_npc_to_talking(self, player_input: str) -> bool:
        self.respond_as_npc(f'player: "{player_input}"')
        return self.llm.does_end_conversation(self.game_state.mode_data["conversation"])

    def respond_as_npc(self, prompt: str):
        self.game_state.mode_data["conversation"] += f"\n{prompt}"
        response = self.llm.generate_for_npc(
            prompt=self.game_state.mode_data["conversation"],
            npc=self.get_npc(self.game_state.mode_data["npc"]),
            motivation=self.game_state.mode_data["npc_motivation"],
            player_name=self.player_character.name,
        )
        self.game_state.mode_data["conversation"] += f"\n{response}"

    def get_all_locations(self):
        return self.sql_db.get_all_locations()

    def get_all_npcs(self):
        return self.sql_db.get_all_npcs()

    def get_location(self, name: str) -> Location:
        proper_name = self.noun_db.fuzzy_lookup(name)
        return self.sql_db.get_location(proper_name)

    def get_npc_to_talk_to(self, player_input):
        current_location = self.sql_db.get_location(self.game_state.location)
        npc_name = self.llm.get_npc_name(player_input, current_location)
        logger.debug(f"get_npc_to_talk_to: name from location info: {npc_name}")
        if npc_name:
            try:
                return self.get_npc(npc_name)
            except IndexError as e:
                raise e
                logger.debug("Generating new NPC to talk to...")
                npc = self.generate_npc(
                    extra_prompt=f"""
The npc is: {npc_name}, and they are currently in {current_location.name}, {current_location.description}
""",
                    player_input=player_input,
                    fill_data={"location_name": current_location.name},
                )
                current_location.npcs.append(npc)
                self.sql_db.save_location(current_location)
                return npc
        logger.debug("get_npc_to_talk_to: NPC not found")
        return None

    def get_npc(self, name: str) -> NPC:
        proper_name = self.noun_db.fuzzy_lookup(name)
        logger.debug(f"GameData.get_npc - {proper_name=}")
        return self.sql_db.get_npc(proper_name)

    def print_state(self):
        print(
            "\n".join(
                (
                    f"Character:{json.dumps(asdict(self.player_character), indent=2)}",
                    f"GameState:{json.dumps(asdict(self.game_state), indent=2)}",
                )
            )
        )

    def generate_quest(self, giver: NPC, motivation: str = "") -> Quest:
        current_location = self.get_location(self.game_state.location)

        # TODO add more prompt
        extra_prompt = f"""
You are a quest designer for a text-based RPG. Your task is to create a unique and interesting quest based on the following NPC's backstory:

NPC Name: {giver.name}
Backstory: {giver.description}
Motivation: {motivation}
Relevant Traits: {giver.bonds}
Current Location: {current_location.name} - {current_location.description}

**Quest Details**
    Description: Provide a short, engaging summary of the quest that hooks the player.
    Objective: Clearly define what the player must achieve to complete the quest.
    Relevant NPCs: Name and describe any other NPCs involved in the quest, along with their roles (e.g., allies, adversaries, neutral parties).
    Challenges: Describe key obstacles or conflicts the player will face during the quest.
    Reward: Describe the reward for completing the quest, which can include material items, knowledge, or relationship improvements with the NPC.

Keep the quest consistent with the NPC’s backstory and ensure it ties into the larger narrative of the game world. Make the quest immersive and meaningful to the player's journey."
"""
        new_quest = self.llm.generate_object(
            Quest,
            fill_data={"giver": giver.name},
            extra_prompt=extra_prompt,
        )
        self.save_quest(new_quest)

    def start_conversation(self, npc: NPC):
        # figure out way to check completion.
        # - maybe have to talk to originator
        # - check opensearch for events related, see if completed
        # - when start a conversation, check if quest was complete
        history_text = ""
        if history := self.get_npc_history(npc):
            history_text = f"\n**Relationship History**:\n{history}"
        self.game_state.mode_data["npc_motivation"] = self.llm.generate(
            f"""
**Player Destails**:
Name: {self.player_character.name}
Description: {self.player_character.description}

**NPC Details**
Name: {npc.name}
Description: {npc.describe()}
Disposition toward the player: {npc.relationship_status}.
{history_text}

What is {npc.name}'s motivation going into this conversation?
            """,
            system_instructions="""
You are a RPG AI skilled in determining and generating character motivations.
You are given NPC descriptions and you response ONLY with a short description of what the NPC wants from the conversation they are having the the player.
            """,
            max_new_tokens=200,
        )
        logger.info(
            f"{npc.name}'s motivation:\n{self.game_state.mode_data['npc_motivation']}"
        )

        if self.llm.is_quest(self.game_state.mode_data["npc_motivation"]):
            self.generate_quest(
                npc, motivation=self.game_state.mode_data["npc_motivation"]
            )

    def generate_town(self, town_input=""):
        name = random.choice(TOWN_NAMES)
        # select town locations
        town_size = random.randint(4, 10)
        num_essential = max(town_size // 3, 3)
        has_a_unique = random.randint(0, town_size - num_essential) > 3
        num_common = town_size - num_essential - has_a_unique

        town_pois = list(
            set(
                random.choices(COMMON_LOCATIONS, k=num_common)
                + random.choices(ESSENTIAL_LOCATIONS, k=num_essential)
            )
        )
        if has_a_unique:
            town_pois.append(random.choice(UNIQUE_LOCATIONS))

        logger.info(f"generate_town - points of interest: {town_pois}")

        pois_str = "- " + "\n- ".join(town_pois)
        town_description = self.llm.generate(
            prompt=f"""
Using the following storyline:
{town_input}

Create an interesting town named {name} with these locations:
{pois_str}

Output ideas about the overall plot of the town, mentioning key locations and NPCs.
           """,
            system_instructions="""
You are a creative AI designed to create town ideas for a DND game. You are good at creating unique ideas and fleshing them out in concise descriptions.
You are a creative AI designed to develop unique town ideas for a DND game. Your goal is to create concise, open-ended storylines and descriptions that allow players to explore and influence events as they unfold.

When developing storylines:
1. Focus on creating **story potential** and **mysteries** that can unfold through player actions.
2. Describe the **current situation** in the town, hinting at challenges, rumors, or mysteries, rather than narrating events that have already happened.
3. For each key location, give a brief description that sets the atmosphere and mentions any unique details.
4. Introduce key NPCs with hints of their personalities, motives, or secrets, suggesting ways players might interact with them.

Do not provide a closed narrative or fixed events; instead, create an intriguing setup that invites players to explore and discover the storyline.
            """,
            max_new_tokens=2048,
        )
        the_town = self.generate_location(
            player_input=f"Use the following information when designing the town:\n{town_description}",
            fill_data={"name": name},
        )
        locations_in_town = [
            self.generate_location(
                player_input=f"Create a {point_of_interest}.\nThe {point_of_interest} is in the town of {the_town.name}:\n{town_description}.",
                fill_data={"parent_location": the_town.name},
            )
            for point_of_interest in town_pois
        ]
        npcs = self.generate_from_lore(town_description, types=[NPC]).get("NPC")
        self.llm.match_npcs_to_locations(town_description, locations_in_town, npcs)
        for location in locations_in_town:
            self.expand_location(location)
            self.noun_db.add(location.name, [])
            self.sql_db.save_location(location)

        the_town.sublocations = [loc.name for loc in locations_in_town]
        self.sql_db.save_location(the_town)
        return the_town

    def respond_npc_not_found(self, player_input):
        current_location = self.get_location(self.game_state.location)
        render_text(
            self.llm.generate(
                f"""
The player asked to talk to someone saying:
{player_input}

The player is currently located at {current_location.name}: {current_location.description}.

Respond the the player that the person they wish to talk to is not here.
            """,
                system_instructions="""
You are an AI designed to respond the players of your text-based RPG for which you are the DM.
You output brief resonses the the player's actions.
            """,
                max_new_tokens=256,
            )
        )

    def generate_from_lore(self, text, types="all"):
        if types == "all":
            types = [NPC, Location]
        generated = defaultdict(list)
        for object_type in types:
            for npc_parsed in self.llm.parse_out(text, object_type):
                generated[f"{object_type.__name__}"].append(
                    self.generate_npc(
                        extra_prompt=f"""
Create an NPC with **name**: {npc_parsed}
Use details about {npc_parsed} from following description:
{text}
""",
                        prefill=False,
                    )
                )
        # can use current state to influence generated results
        return generated

    def get_location_to_move_to(
        self,
        player_input: str,
    ) -> (str, Location):
        current_location = self.sql_db.get_location(self.game_state.location)
        dest_options = ["local"]
        if current_location.parent_location:
            parent_location = self.sql_db.get_location(current_location.parent_location)
            dest_options.append("parent")
            nearby_locations = [
                self.sql_db.get_location(nl)
                for nl in parent_location.sublocations
                if nl != current_location.name
            ]
            parent_dependant = f"""
- Parent Location:
name: {parent_location.name}, type: {parent_location.location_type}
"""
            if nearby_locations:
                dest_options.append("nearby")
                parent_dependant += "- Nearby Locations:\n" + "\n".join(
                    f"name: {nearby_location.name}, type: {nearby_location.location_type}"
                    for nearby_location in nearby_locations
                )
        else:
            parent_dependant = ""
            nearby_locations = None
        child_locations = list(
            map(self.sql_db.get_location, current_location.sublocations)
        )
        if child_locations:
            dest_options.append("child")
            child_locations_str = "- Child Locations:\n" + "\n".join(
                f"name: {child_location.name}, type: {child_location.location_type}"
                for child_location in child_locations
            )
        else:
            child_locations_str = ""

        type_descriptions = {
            "local": """
- Indicate **'local'** if the movement is within the current location and does not include movement to a child or other defined area.
""",
            "child": """
- Indicate **'child'** if the movement is to a specific sub-location within the current location (e.g., moving to a shop within a marketplace).""",
            "nearby": """
- Indicate **'nearby'** if the movement is to an adjacent location outside the current location but within the same general area (e.g., moving from a marketplace to a nearby guard house).""",
            "parent": """
- Indicate **'parent'** if the movement is from the current location up to the parent location (e.g., leaving a marketplace to re-enter the larger area or town containing it).""",
        }
        type_desc_prompt = "".join(type_descriptions[dest] for dest in dest_options)

        json_instruct = json.dumps(
            {
                "movement_type": ", ".join(dest_options),
                "destination": "name of destination",
            },
            indent=2,
        )
        # TODO: this is where pathing between locations would be helpful, to use as prompt for possible places to go
        movement_data = json.loads(
            self.llm.generate(
                f"""
Contextual Game Details:
- Current Location:
name: {current_location.name}, type: {current_location.location_type}
{parent_dependant}
{child_locations_str}

Player Command:
{player_input}

Remember to select only one of the options for Movement Type.
                """,
                system_instructions=f"""
You are an assistant for a text-based RPG, helping to interpret player movement commands. Based on the player’s command, analyze the intended movement to determine:

1. **Movement Type**:{type_desc_prompt}

2. **Destination**: Provide the name of the target location based on the list in Contextual Game Details. If movement type is 'local,' provide a brief description of the movement within the location.


Please respond only in JSON format as shown below:
{json_instruct}

If the command is unclear, choose the most likely destination based on context.

Below are contextual details about the game environment to help with interpreting the player’s command. Use this information to make the most accurate choice possible.
                """,
                max_new_tokens=512,
                json_out=True,
            )
        )
        movement_data["destination"] = self.noun_db.fuzzy_lookup(
            movement_data["destination"]
        )
        render_text("Movement Data:")
        render_text(json.dumps(movement_data, indent=2))

        if current_location.name == movement_data["destination"]:
            return "local", current_location
        if (
            current_location.parent_location
            and parent_location.name == movement_data["destination"]
        ):
            return "local", current_location

        if nearby_locations:
            for nearby_location in nearby_locations:
                if movement_data["destination"] == nearby_location.name:
                    return "nearby", nearby_location
        if child_locations:
            for child_location in child_locations:
                if movement_data["destination"] == child_location.name:
                    return "child", child_location

        render_text("Error with movement data")
        raise ValueError("Bad LLM Generation")

    def describe_scene(self, location: Location = None):
        if location is None:
            location = self.sql_db.get_location(self.game_state.location)
        npcs = location.npcs
        if npcs:
            npc_instruct = """
When describing a scene that includes NPCs, mention the NPCs as part of the environment. Use their appearance, actions, or traits to enhance the scene’s atmosphere. Focus on how the NPCs interact with the environment or each other, but keep the main focus on the player’s perspective.
"""
            npc_descriptions = """
**NPCs Present**:
""" + "\n".join(
                f"{npc.name}: {npc.appearance}, who is {npc.traits} and is {npc.gender} presenting."
                for npc in npcs
            )
        else:
            npc_instruct = ""
            npc_descriptions = ""

        response = self.llm.generate(
            f"""
Describe the scene for the location below, focusing on its atmosphere, sensory details, notable features, and any NPCs present. Make the description immersive and keep it between two to four sentences.

{location.describe()}

{npc_descriptions}
            """,
            system_instructions=f"""
You are describing scenes in a text-based RPG. For each location, focus on creating an immersive description that highlights the atmosphere, sensory details (sights, sounds, smells, textures), and notable features.

- **Atmosphere**: Convey the overall feeling or mood of the location (e.g., bustling, eerie, tranquil).
- **Sensory Details**: Include specific sensory details that bring the scene to life, such as sounds, scents, lighting, and textures.
- **Notable Features**: Emphasize unique or defining characteristics that make the location distinctive.
{npc_instruct}
Write the description in two to four sentences, and keep it grounded in the player’s perspective.

""",
            max_new_tokens=256,
        )
        render_text(response)

    def expand_location(self, location: Location) -> Location:
        if len(location.npcs) < 3:
            n_npcs = random.randint(3, 6) - len(location.npcs)
            new_npcs = self.generate_more_npcs(location, n=n_npcs)
            for npc in new_npcs:
                self.save_npc(npc)
            location.npcs.extend(new_npcs)
            self.sql_db.save_location(location)
        if not location.sublocations:
            # does location type not need sublocations (rooms, etc)
            # generate full layout
            pass
        return location

    def update_affinity_score(self):
        npc = self.sql_db.get_npc(self.game_state.mode_data["npc"])
        previous_relationship = npc.relationship_status
        if self.game_state.mode == "conversation":
            affinity_delta = self.llm.affinity_score_change(
                npc,
                self.game_state.mode_data["conversation"],
            )
            npc.affinity_score += affinity_delta
            if npc.relationship_status != previous_relationship:
                render_text(
                    f"Relationship with {npc.name} changed from {previous_relationship} to {npc.relationship_status}"
                )
            self.sql_db.save_npc(npc)

    def generate_more_npcs(self, location: Location, n: int) -> list[NPC]:
        logger.debug(f"generating more npcs for {location.name}")
        if location.npcs:
            npc_descriptions = "\n**Existing NPCs**:\n" + "\n".join(
                f"{npc.name}: {npc.description}" for npc in location.npcs
            )
        else:
            npc_descriptions = ""

        for _ in range(3):
            npcs_gen = self.llm.generate(
                f"""
    Expand on the location below by adding detailed descriptions of new NPCs that bring variety to the scene. Use the list of existing NPCs to avoid repetition, ensuring each new NPC has unique characteristics or roles that complement those already present.

    {location.describe()}
    {npc_descriptions}

    Introduce 3-4 new NPCs who are distinct from the ones listed above.
    Remember to output a JSON list of {n} NPC descriptions. Do not include any other information in your response.
    """,
                system_instructions="""
    You are creating new NPCs for a location in a text-based RPG. For each NPC, generate a one-line description that includes their name, role, personality, appearance, and actions. Each NPC should feel unique and add variety to the location.

    When expanding locations in a text-based RPG, consider the existing NPCs to ensure variety and avoid redundancy. Each new NPC should have unique characteristics or roles that complement those already present.

    - **Review Existing NPCs**: Note their roles, personalities, and actions to ensure the new NPCs bring fresh dynamics to the location.
    - **Create Distinctive New NPCs**: Generate NPCs with unique roles, traits, or behaviors that add to the atmosphere and diversity of the scene.
    - **Blend NPCs Naturally**: Ensure each NPC feels integrated within the setting, whether interacting with others, performing actions, or blending into the background.
    - **Boring NPCs**: You are allowed to make NPCs who are simple and plain.

    Each description should follow this format: "{Name}, a {role}, {personality traits}, {appearance details}, {what the NPC is doing}."
                """
                + f"""
    Respond with a JSON list of {n} NPC descriptions and no other text.
    """,
                max_new_tokens=2000,
                json_out=True,
            ).strip()
            try:
                npcs_ideas = json.loads(npcs_gen)
                break
            except JSONDecodeError:
                npcs_ideas = None
                continue
        if npcs_ideas is None:
            return []
        npcs = []
        for npc_idea in npcs_ideas:
            if not isinstance(npc_idea, str):
                npc_idea = json.dumps(npc_idea)
            if not npc_idea.strip():
                continue
            logger.debug(f"generating npc for {location.name}")
            npcs.append(
                self.generate_npc(
                    extra_prompt=f"Create the NPC based on the following idea:\n{npc_idea.strip()}",
                    fill_data={"location_name": location.name},
                    prefill=False,
                )
            )
        return npcs

    def save_conversation(self):
        conversation_summary = self.llm.summarize_conversation(
            **self.game_state.mode_data
        )
        self.vector_db.index_document(
            {
                "date": self.game_state.date,
                "type": "conversation",
                "summary": conversation_summary,
                "npc": self.game_state.mode_data["npc"],
            }
        )

    def get_npc_history(self, npc: NPC) -> str:
        documents = self.vector_db.search_documents(
            query={"query": {"match": {"npc": npc.name}}}
        )
        if not documents:
            return ""
        return self.llm.summarize_npc_history(npc, documents)

    def save_npc(self, npc, nicknames=None):
        if nicknames is None:
            nicknames = self.llm.generate_nicknames(npc)
        self.noun_db.add(npc.name, nicknames)
        self.sql_db.save_npc(npc)
        self.graph_db.add_entity(npc)

    def save_location(self, location, nicknames=None):
        if nicknames is None:
            nicknames = self.llm.generate_nicknames(location)
        self.noun_db.add(location.name, nicknames)
        self.sql_db.save_location(location)
        self.graph_db.add_entity(location)

    def save_quest(self, quest: Quest):
        self.sql_db.save_quest(quest)
        quest_data = asdict(quest)
        npcs = quest_data.pop("npcs_involved")
        # todo: maybe attach locations to quests?
        quest_data.pop("locations")
        quest_data.update({"type": "quest/aquired", "npc": quest.giver})

        self.vector_db.index_document(quest_data)
        self.graph_db.add_entity(quest)
        for npc in npcs:
            npc_name = self.noun_db.fuzzy_lookup(npc)
            self.graph_db.add_relation(
                {"_from": f"npc/{npc_name}", "_to": f"quest/{quest.name}"}
            )

    def get_quest(self, name) -> Quest:
        return self.sql_db.get_quest(name)
