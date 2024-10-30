import json
import logging
import os
import random
from collections import defaultdict
from dataclasses import asdict, dataclass

from llmdm.character import Character
from llmdm.data_types import Entity
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
from llmdm.utils import SAVE_DIR
from llmdm.vector_client import OpenSearchClient

logger = logging.getLogger(__name__)


@dataclass
class GameState:
    date: str = "<the in-game date>"
    location: str = "<current in-game location>"
    mode: str = "one of: free, combat, conversation"
    mode_data: dict = None

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
    active_quest: dict = None

    def get(self, name) -> Entity:
        proper_name = self.noun_db.fuzzy_lookup(name)
        # TODO - maybe add type to lookup table?
        return self.sql_db.get(proper_name)

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
            f"""
Create the narrative for a new game. The main character is:
{character.name}: {character.description}

Create a short description of the town the player is in and why they are here.
Start with: "You find yourself in a small village in the woods..."
            """,
            system_instructions="""
You are an expert AI RPG Dungeon Master. Your responsibility is to write the intro to a new game.
            """,
            max_new_tokens=256,
        )
        logger.debug(new_storyline)
        state = GameState(
            mode="free",
            location="",
            date="day 0",
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
        starting_location = game_data.generate_town(
            town_input=f"Based on:\n{new_storyline}"
        )
        game_data.game_state.location = starting_location.name
        game_data.save()

        logger.debug("game_state: {json.dumps(asdict(game_data.game_state), indent=2)}")
        print(
            f"You begin your story in {starting_location.name}:\n{starting_location.description}"
        )
        game_data.travel_to(starting_location)
        return game_data

    def transition_mode_to(self, mode: str, npc: NPC = None):
        self.game_state.mode = mode
        if mode == "conversation":
            self.game_state.mode_data = {"conversation": "", "npc": npc.name}
            self.start_conversation(npc)

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
        self.noun_db.add(new_location.name, nicknames)
        self.sql_db.save_location(new_location)
        return new_location

    def travel_to(self, new_location: Location):
        if (
            new_location.name == self.game_state.location
            or not self.game_state.location
        ):
            travel_text = self.llm.generate(
                f"""
The player is in {new_location.name}: {new_location.description}

Create a narrative description of their surroundings.
                """,
                system_instructions="""
You are a expert narrative AI. You specialize in describing the location the player is in.
ONLY output a narration of the events and do NOT add events to the story.
ALWAYS refer to the player as "you".
                """,
                max_new_tokens=256,
            )

        old_location = self.get_location(self.game_state.location)
        if new_location.name in old_location.sublocations:
            travel_text = self.llm.generate(
                f"""
The player currently in {old_location.name}: {old_location.description}
and they are traveling to: {new_location.name}: {new_location.description}
{new_location.name} is in {old_location.name}.

Create a narrative description of what follows as the player arrives at {new_location.name}.
                """,
                system_instructions="""
You are a expert narrative AI. You specialize in describing the transition as the player travels from one location to another.
ONLY output a narration of the events and do NOT add events to the story.
ALWAYS refer to the player as "you".
                """,
                max_new_tokens=256,
            )
        else:
            travel_text = self.llm.generate(
                f"""
The player is traveling FROM {old_location.name}: {old_location.description}
and they are traveling TO: {new_location.name}: {new_location.description}

Create a narrative description of what follows as the player travels.
                """,
                system_instructions="""
You are a expert narrative AI. You specialize in describing the transition as the player travels from one location to another.
ONLY output a narration of the events and do NOT add events to the story.
ALWAYS refer to the player as "you".
                """,
                max_new_tokens=256,
            )
        print(travel_text)
        self.game_state.location = new_location.name

    def generate_npc(
        self, extra_prompt: str = "", player_input: str = None, fill_data: dict = {}
    ):
        if "gender" not in fill_data:
            fill_data["gender"] = random.choices(
                list(NAMES.keys()), weights=[0.47, 0.47, 0.06], k=1
            )[0]
        gender = fill_data["gender"]

        if "name" not in fill_data:
            fill_data["name"] = random.choice(NAMES[gender])
        name = fill_data["name"]

        if "traits" not in fill_data:
            fill_data["traits"] = random.choice(TRAIT_TRIPLETS)
        traits = fill_data["traits"]

        if player_input:
            extra_prompt += f"The player gave this description of the NPC they are approaching: {player_input}"

        extra_prompt += f"""
The NPC is named {name}, they are {gender} presenting, and they have these traits:
{traits}
        """
        new_npc, nicknames = self.llm.generate_object(
            NPC,
            fill_data=fill_data,
            nicknames=True,
            extra_prompt=extra_prompt,
            name=name,
        )
        self.noun_db.add(new_npc.name, nicknames)
        self.sql_db.save_npc(new_npc)
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
        )
        self.game_state.mode_data["conversation"] += f"\n{response}"

    def get_location_to_move_to(self, player_input):
        current_location = self.sql_db.get_location(self.game_state.location)
        destination = self.llm.get_destination_name(player_input, current_location)
        if destination == "leaving":
            location = self.generate_location(
                player_input,
                current_location,
                destination=destination,
            )
            # connection = self.llm.generate_connection(current_location, location, player_input)
        elif destination == "new sublocation":
            location = self.generate_location(
                player_input,
                current_location,
                destination=destination,
            )
            current_location.sublocations.append(location)
            # connection = self.llm.generate_connection(current_location, location, player_input)
        else:
            location = self.get_location(destination)
        return location

    def get_all_locations(self):
        return self.sql_db.get_all_locations()

    def get_location(self, name: str) -> Location:
        proper_name = self.noun_db.fuzzy_lookup(name)
        return self.sql_db.get_location(proper_name)

    def get_npc_to_talk_to(self, player_input):
        current_location = self.sql_db.get_location(self.game_state.location)
        npc_name = self.llm.get_npc_name(player_input, current_location)
        if npc_name:
            return self.get_npc(npc_name)
        logger.debug("get_npc_to_talk_to: NPC not found")
        return None

    def get_npc(self, name: str) -> NPC:
        proper_name = self.noun_db.fuzzy_lookup(name)
        logger.debug(f"GameData.get_npc - {proper_name=}")
        return self.sql_db.get_npc(proper_name)

    def print_state(self):
        print(
            f"Character:{json.dumps(asdict(self.player_character), indent=2)}",
            f"GameState:{json.dumps(asdict(self.game_state), indent=2)}",
            sep="\n",
        )

    def generate_quest(self, giver: str, motivation: str = "") -> Quest:
        current_location = self.get_location(self.game_state.location)
        npc = self.get_npc(giver)

        extra_prompt = f"""
The quest is given by {npc.name}: {npc.description}.
Who is currently in {current_location.name}: {current_location.description}
"""
        if motivation:
            extra_prompt += motivation

        self.game_state.active_quest = self.llm.generate_object(
            type(Quest),
            fill_data={"giver": npc.name},
            extra_prompt=extra_prompt,
        )

    def start_conversation(self, npc: NPC):
        self.game_state.mode_data["npc_motivation"] = self.llm.generate(
            f"""
Here is a short description of the NPC:
{npc.describe()}

The player is {self.player_character.name}: {self.player_character.description}

what does {npc.name} want to get out of this conversation?
            """,
            system_instructions="""
You are a RPG AI skilled in determining and generating character motivations.
You are given NPC descriptions and you response ONLY with a short description of what the NPC wants from the conversation they are having the the player.
            """,
            max_new_tokens=128,
        )
        print(
            f"{npc.name}'s motivation:\n{self.game_state.mode_data['npc_motivation']}"
        )

        if self.llm.is_quest(self.game_state.mode_data["npc_motivation"]):
            self.generate_quest(
                npc, motivation=self.game_state.mode_data["npc_motivation"]
            )

    def generate_town(self, town_input=""):
        name = random.choice(TOWN_NAMES)
        # select town locations
        town_size = random.randint(3, 10)
        num_essential = max(town_size // 3, 3)
        has_a_unique = random.randint(0, town_size - num_essential) > 3
        num_common = town_size - num_essential - has_a_unique

        town_pois = random.choices(COMMON_LOCATIONS, k=num_common) + random.choices(
            ESSENTIAL_LOCATIONS, k=num_essential
        )
        if has_a_unique:
            town_pois.append(random.choice(UNIQUE_LOCATIONS))

        pois_str = "- " + "\n- ".join(town_pois)
        town_description = self.llm.generate(
            prompt=f"""
Using the following storyline:
{town_input}

Create an interesting town named {name} with these locations:
{pois_str}

Come up with a key storyline for the town and any key NPCs.
            """,
            system_instructions="""
You are a creative AI designed to create town ideas for a DND game. You are good at creating unique ideas and fleshing them out in concise descriptions.
You output ideas about the overall plot of the town, mentioning key, locations and NPCs.
            """,
            max_new_tokens=2048,
        )
        print("TOWN DESC:\n{town_description}")
        the_town = self.generate_location(
            player_input="Use the following information when designing the town:\n{town_description}",
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
            # TODO
            # up the number of npcs in a location
            # self.llm.fill_location_npcs(location)
            self.noun_db.add(location.name, [])
            self.sql_db.save_location(location)

        the_town.sublocations = locations_in_town
        self.sql_db.save_location(the_town)
        return the_town

    def respond_npc_not_found(self, player_input):
        current_location = self.get_location(self.game_state.location)
        print(
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
Create {npc_parsed}, who is mentioned in the following town_description:
{text}
                """,
                        fill_data={"name": npc_parsed},
                    )
                )
        # can use current state to influence generated results
        return generated
