import json
import logging
import os
import re
from dataclasses import asdict, dataclass

from llmdm.data_types import Entity, Relation
from llmdm.location import Location
from llmdm.npc import NPC
from llmdm.utils import suppress_stdout

with suppress_stdout():
    from transformers import AutoTokenizer, pipeline


logger = logging.getLogger(__name__)


class LLM:
    def __init__(self):
        model_name = "meta-llama/Llama-3.1-8B-Instruct"
        model_name = "meta-llama/Llama-3.2-3B-Instruct"
        model_name = os.getenv("LLMDM_MODEL", model_name)
        with suppress_stdout():
            self.pipeline = pipeline(
                "text-generation",
                model=model_name,
                device_map="auto",
                torch_dtype="auto",
                tokenizer=AutoTokenizer.from_pretrained(model_name),
            )

    def generate(
        self,
        prompt,
        system_instructions="You are an AI story teller.",
        max_new_tokens=128,
        json_out=False,
    ):
        messages = [
            {
                "role": "system",
                "content": system_instructions.strip(),
            },
            {"role": "user", "content": prompt.strip()},
        ]
        logger.debug(f"LLM.generate: messages:\n{messages}")
        with suppress_stdout():
            generated_text = (
                self.pipeline(
                    messages,
                    max_new_tokens=max_new_tokens,
                    pad_token_id=self.pipeline.tokenizer.eos_token_id,
                )[0]["generated_text"][-1]["content"]
                .strip()
                .replace("*", "")
            )

        if json_out:
            generated_text = strip_markdown(generated_text)

        logger.debug(f"LLM.generate: generated:\n{generated_text}")
        return generated_text

    def generate_story(self, *, prompt=None, game_data):
        if prompt is None:
            prompt = "Generate a person, place and object. Describe each of them briefly and decribe how they are related."
        generated_text = self.generate(prompt, max_new_tokens=256)
        logger.debug(f"LLM.generate_story - story:\n{generated_text}")

        for i in range(3):
            save_data_instructions = """
You are an AI that parses the most essential data from stories.
You ONLY output VALID JSON, have your output be a list of data with types person, place, object of the format:
{"name": "<name>",  "description": "<description of noun>"}
            """
            data_generated = self.generate(
                generated_text,
                save_data_instructions,
                max_new_tokens=512,
                json_out=True,
            )
            logger.debug(f"LLM.generate_story - parsed nouns:\n{data_generated}")
            try:
                nouns_data = json.loads(data_generated)
                break
            except json.decoder.JSONDecodeError:
                logger.warn(f"failed to save data (attempt {i}):\n{data_generated}")

        for i in range(3):
            save_relations_instructions = """
You are an AI that parses the most essential relationstips between nouns in stories.
You ONLY output VALID JSON data, have your output be a list of relation objects of the format:
{"description": "<description of relation>", "from": "<name1>", "to": "<name2>"}
            """

            noun_ids = ", ".join([d["name"] for d in nouns_data])
            relations_generated = self.generate(
                f"""
Extract up to 12 relations between these objects:
{noun_ids}
from this story blurb:
{generated_text}
                """,
                save_relations_instructions,
                max_new_tokens=512,
                json_out=True,
            )
            logger.debug(
                f"LLm.generate_story - parsed relations:\n{relations_generated}"
            )
            try:
                relations_data = json.loads(relations_generated)
                break
            except json.decoder.JSONDecodeError:
                logger.warn(
                    f"failed to save data (attempt {i}):\n{relations_generated}"
                )

        for entity in nouns_data:
            try:
                datum = Entity(**entity)
                game_data.graph_db.add_entity(datum)
            except Exception as e:
                logger.debug(f"Entity invalid: {datum}")
                logger.debug(f"with error: {str(e)}")

        for relation in relations_data:
            relation.update(
                {
                    "_from": "entity/" + relation.pop("from"),
                    "_to": "entity/" + relation.pop("to"),
                }
            )
            try:
                datum = Relation(**relation)
                game_data.graph_db.add_relation(datum)
            except Exception as e:
                logger.debug(f"Relation invalid: {datum}")
                logger.debug(f"with error: {str(e)}")
        return generated_text

    def generate_object(
        self,
        cls: dataclass,
        fill_data: dict = {},
        prompt: bool = False,
        nicknames=False,
        extra_prompt=None,
        name=None,
    ):
        """
        cls should be a data class with default values of descriptions of the fields for the llm
        """
        object_type = cls.__name__
        default_object = cls()
        fields = [k for k in asdict(default_object) if k not in fill_data]

        logger.debug(f"Generating new {object_type}...")
        llm_prompt = (
            f"Create a {object_type} for the player including {', '.join(fields)}"
        )
        if prompt:
            info = input(f"Give your idea for the {object_type}:\n")
            llm_prompt += f""" based on the player input:
{info}
            """
        if extra_prompt:
            llm_prompt += f"\n{extra_prompt}"

        object_text = self.generate(
            prompt=llm_prompt,
            system_instructions=f"""
You are a part of an AI-driven RPG. You are the AI designed to create {object_type} for the game.
You ONLY output descriptions of the {object_type}s you generate.
            """,
            max_new_tokens=512,
        )

        # if name is None:
        #     name = self.generate(
        #         prompt=f"Determine the name of the following {object_type}:\n{object_text}",
        #         system_instructions=f"You are an expert naming AI. You are designed to create unique {object_type} names. You ONLY output a single name.",
        #         max_new_tokens=10,
        #     )
        if name:
            fill_data["name"] = name
            object_text = self.generate(
                prompt=f"""
Correct all references to the {object_type} in this passage with {name}:
{object_text}
                """,
                system_instructions="""
You are a gramatical AI that is an expert at replacing names in text.
You ONLY output the corrected text.
                """,
                max_new_tokens=524,
            )

        # Replace un-escaped double and single quotes with escaped ones
        escaped_text = re.sub(r'(?<!\\)"', r"\"", object_text)
        object_data = None
        for i in range(3):
            try:
                generated_data = self.generate(
                    f"""
Parse the {object_type} data from the following description:
{escaped_text}
                    """,
                    system_instructions=f"""
You are an AI designed to parse {object_type} data out of descriptions. You are careful to escape quotation marks when needed because you ONLY output VALID JSON in the format:
{json.dumps(asdict(default_object))}
                    """,
                    max_new_tokens=1024,
                    json_out=True,
                )
                object_data = {
                    k: v for k, v in json.loads(generated_data).items() if k in fields
                }

                break
            except Exception as e:
                logger.info(f"Could not parse {object_type} data, attempt {i}: {e}")

        if not object_data:
            raise ValueError(f"Could not create a {object_type}...")

        object_data.update(fill_data)
        obj = cls(**object_data)
        if nicknames:
            return obj, self.generate_nicknames(obj)
        return obj

    def generate_nicknames(self, obj):
        nicknames = (
            self.generate(
                f"""
Here is a description of {obj.name}:
{obj.describe()}

output a few possible alternate names for this {type(obj).__name__} that they may be refered to as.
                """,
                system_instructions=f"""
You are an AI system designed to identify possible alternate names for a given {type(obj).__name__}.
You ONLY output a comma separated list of names.
                """,
                max_new_tokens=50,
            )
            .strip()
            .split(", ")
        )
        logger.debug(f"generate_nicknames: {nicknames}")
        return nicknames

    def generate_for_npc(self, prompt: str, npc: NPC, motivation: str):
        def _sanitize(generated):
            generated = generated.split("player: ")[0]
            generated = "".join(generated.split(f"{npc.name}: ")).strip()
            return generated

        generated_response = _sanitize(
            self.generate(
                prompt=f"Continue the conversation as {npc.name}:\n{prompt}",
                system_instructions=f"""
You are roleplaying as {npc.name}: {npc.description}.
Narrate in the 3rd person. Refer to the player as "you".

{npc.name} wants: {motivation}
                """,
                max_new_tokens=256,
            )
        )
        edited_response = self.generate(
            prompt=f"""
Remove any unfinished sentences or thoughts from the end of this text:
{generated_response}
                    """,
            system_instructions="""
You are an expert AI designed to remove any unfinished thoughts from text. You output ONLY output the text you have edited.
                    """,
            max_new_tokens=256,
        )

        print(edited_response)
        return f"{npc.name}: {edited_response}"

    def does_end_conversation(self, conversation):
        return (
            "yes"
            == self.generate(
                prompt=f"""
The conversation is:
{conversation}
            """,
                system_instructions="""
You are an AI designed to tell if last person to talk is ending the conversation.
The user provides the conversation and you respond with only "yes" or "no"
                """,
                max_new_tokens=1,
            ).strip()
        )

    def get_npc_name(self, player_input: str, current_location: Location) -> str:
        if not current_location.npcs:
            return None
        npcs = ", ".join(
            [f"{npc.name}: {npc.description}" for npc in current_location.npcs]
        )
        exists = self.generate(
            f"""
The player wants to start a conversation:
{player_input}

The current location has the following people:
[{npcs}]

Is there a person matching that description?
            """,
            system_instructions="""
You are an AI RPG subsytem designed to identify whether the person the player wants to talk to is in the current location. You only respond with "yes" or "no"
            """,
            max_new_tokens=1,
        )
        if exists == "no":
            return None
        else:
            return self.generate(
                f"""
Which of the following NPCs does the player want to start the conversation with:
{npcs}

The player wants to start a conversation:
{player_input}
                """,
                system_instructions="""
You are an AI RPG subsytem designed to extract the name of the NPC the player wants to start a conversation with.
You respond only with the NPC's name
                """,
                max_new_tokens=5,
            )

    def get_destination_name(
        self, player_input: str, current_location: Location
    ) -> str:
        leaving = (
            self.generate(
                f"""
The player wants to move:
{player_input}

The current location is:
{current_location.name}: {current_location.description}

Is the player leaving this location?
            """,
                system_instructions="""
You are an AI RPG subsytem designed to identify whether the player is leaving a location. You only respond with "yes" or "no"
            """,
                max_new_tokens=1,
            )
            .strip()
            .lower()
        )
        if leaving != "no":
            return "leaving"
        sublocations = ", ".join(
            # todo get the sublocations and include descriptions
            current_location.sublocations
        )
        # TODO: ask if we need to change locations at all!
        existing_sublocation = self.generate(
            f"""
The player wants to move:
{player_input}

The current sublocations of the current location are:
{sublocations}

Is the player going to one of these sublocations?
            """,
            system_instructions="""
You are an AI RPG subsytem designed to identify whether the player is going to a sublocation of their current location. You only respond with "yes" or "no"
            """,
            max_new_tokens=1,
        )
        if existing_sublocation.strip() == "yes":
            return self.generate(
                f"""
Which of the following sublocations does the player want to go to:
{sublocations}

The player wants to move to:
{player_input}
                """,
                system_instructions="""
You are an AI RPG subsytem designed to extract the name of the sublocation the player wants to move to.
You respond only with the name of that sublocation.
                """,
                max_new_tokens=5,
            )
        return "new sublocation"

    def is_quest(self, motivation: str) -> bool:
        decision = self.generate(
            f"""
The NPC wants: {motivation}.
Is this something that will spawn a quest?
            """,
            system_instructions="""
You are an AI trained in deciphering NPC motivations and deciding if what they want is a quest.
You ONLY respond with yes or no.
            """,
            max_new_tokens=1,
        )
        return decision == "yes"

    def parse_out(self, object_text, object_type):
        obj_list = None
        for i in range(3):
            try:
                generated_data = self.generate(
                    f"""
Parse out the names of people mentioned in this description:
{object_text}
                    """,
                    system_instructions="""
You are an AI designed to parse a list of NPC *names* out of descriptions. You are careful to escape quotation marks when needed because you ONLY output a VALID JSON LIST of strings.
                    """,
                    max_new_tokens=512,
                    json_out=True,
                )
                obj_list = json.loads(generated_data)
                break
            except Exception as e:
                logger.info(f"Could not parse {object_type} data, attempt {i}: {e}")

        if not obj_list:
            raise ValueError(f"Could not create a {object_type}...")

        logger.debug("parse_out: {object_type}: {obj_list}")
        return obj_list

    def match_npcs_to_locations(
        self, description: str, locations: list[Location], npcs: list[NPC]
    ):
        people = "\n".join(f"{npc.name}: {npc.description}" for npc in npcs)
        places = "\n".join(f"{loc.name}: {loc.description}" for loc in locations)
        template = json.dumps(
            {loc.name: ["<Person1>", "<Person2>", "..."] for loc in locations}, indent=2
        )
        matches = None
        for i in range(3):
            try:
                generated_data = self.generate(
                    f"""
Use the following description:
{description}

For these lists of people and places, output a map of locations to list of names
people:
{people}

places:
{places}

Use the following template for your ouput:
{template}
                    """,
                    system_instructions="""
You are an AI designed to identify which locations in town people will be in for a DnD game. You are careful to escape quotation marks when needed because you ONLY output VALID JSON.
                    """,
                    max_new_tokens=512,
                    json_out=True,
                )
                matches = json.loads(generated_data)
                break
            except Exception as e:
                logger.info(f"Could not parse location/npc matches, attempt {i}: {e}")

        if not matches:
            raise ValueError("Could not create the location to npc map...")

        logger.debug("npc to location matches:\n{matches}")
        for location in locations:
            loc_matches = matches.get(location.name, [])
            if not loc_matches:
                logger.debug("match_npcs_to_locations: no NPCs for loc_matches")
            for npc in npcs:
                if npc.name in loc_matches:
                    location.npcs.append(npc)
                    break


def strip_markdown(text):
    for token in ["```json", "```"]:
        text = "".join(text.split(token))

    return text
