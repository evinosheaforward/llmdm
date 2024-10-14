import json
import logging
import os
from dataclasses import asdict, dataclass

from llmdm.character import Character
from llmdm.data_types import Entity
from llmdm.generate import LLM
from llmdm.graph_client import GraphClient
from llmdm.location import Location
from llmdm.nouns_lookup import ProperNounDB
from llmdm.npc import NPC
from llmdm.sql_client import SQLClient
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

    @classmethod
    def from_storyline(cls, storyline: str, llm: LLM):
        game_data = None
        for i in range(3):
            try:
                generated_data = llm.generate(
                    f"""
Parse the game state data from the following character description:
{storyline}
                        """,
                    system_instructions="""
You are an AI designed to parse game state data out of descriptions. You ONLY output VALID JSON in the format:
{"date": <current date of the storyline>, "location": <starting location of the player character>}
                    """,
                    max_new_tokens=256,
                    json_out=True,
                )
                game_data = json.loads(generated_data)
                break
            except Exception as e:
                logger.warn(f"Could not parse character data {e}")
        if not game_data:
            raise ValueError("Could not create a character...")
        print(storyline)
        return cls(mode="free", **game_data)


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

Create a short starting narrative of where the player is and what their current goal/objective/quest is.
""",
            system_instructions="You are part of an AI-driven RPG. Your responsibility is to generate the background of a new game.",
            max_new_tokens=256,
        )
        logger.debug(new_storyline)
        state = GameState.from_storyline(new_storyline, llm)
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
        game_data.save()
        starting_location = game_data.generate_location(
            player_input="Based on {game_data.game_state.location}"
        )
        game_data.game_state.location = starting_location.name
        logger.debug("game_state: {json.dumps(asdict(game_data.game_state), indent=2)}")
        print(
            f"You begin your story in: {starting_location.name}:\n{starting_location.description}"
        )
        game_data.travel_to(starting_location)
        return game_data

    def transition_mode_to(self, mode, npc=None):
        self.game_state.mode = mode
        if mode == "conversation":
            self.game_state.mode_data = {"conversation": "", "npc": npc.name}

    def generate_location(
        self,
        player_input: str = "",
        current_location: Location = None,
        destination: str = "",
    ):
        parent_location = None
        if destination == "leaving":
            extra_prompt = f"The player is leaving {current_location.name}, {current_location.description} and is going to:\n{player_input}"
        elif destination == "new sublocation":
            extra_prompt = f"The player is in {current_location.name}, {current_location.description} and is staying there, but going to:\n{player_input}"
            parent_location = current_location.name
        else:
            extra_prompt = player_input

        new_location, nicknames = self.llm.generate_object(
            Location,
            fill_data={
                "connections": [],
                "npcs": [],
                "parent_location": parent_location,
                "sublocations": [],
            },
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
        else:
            old_location = self.get_location(self.game_state.location)
            travel_text = self.llm.generate(
                f"""
The player is traveling
from: {old_location.name}: {old_location.description}
to {new_location.name}: {new_location.description}

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

    def generate_npc(self, player_input=None, fill_data={}):
        new_npc, nicknames = self.llm.generate_object(
            NPC,
            fill_data=fill_data,
            nicknames=True,
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
            self.game_state.mode_data["conversation"],
            self.get_npc(self.game_state.mode_data["npc"]),
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

    def get_location(self, name: str) -> Location:
        proper_name = self.noun_db.fuzzy_lookup(name)
        return self.sql_db.get_location(proper_name)

    def get_npc_to_talk_to(self, player_input):
        current_location = self.sql_db.get_location(self.game_state.location)
        npc_name = self.llm.get_npc_name(player_input, current_location)
        if npc_name == "new":
            npc = self.generate_npc(
                player_input, fill_data={"location_name": current_location.name}
            )
            current_location.npcs.append(npc)
            self.sql_db.save_location(current_location)
        else:
            npc = self.get_npc(npc_name)
        return npc

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
