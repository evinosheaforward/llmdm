import json
import logging
import os
from dataclasses import asdict, dataclass

from transformers import AutoTokenizer, pipeline

from llmdm.data_types import Entity, Relation
from llmdm.location import Location
from llmdm.npc import NPC
from llmdm.utils import suppress_stdout

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
            generated_text = self.pipeline(
                messages,
                max_new_tokens=max_new_tokens,
                pad_token_id=self.pipeline.tokenizer.eos_token_id,
            )[0]["generated_text"][-1]["content"].strip()

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
            system_instructions=f"You are a part of an AI-driven RPG. You are the AI designed to create {object_type} for players. You ONLY output descriptions of the {object_type}s you generate.",
            max_new_tokens=256,
        )

        object_name = self.generate(
            prompt=f"Generate the name of the following {object_type}:\n{object_text}",
            system_instructions=f"You are an expert naming AI. You are designed to create unique {object_type} names. You ONLY output a single name.",
            max_new_tokens=3,
        )

        object_text = self.generate(
            prompt=f"""
Correct all references to the {object_type} in this passage with {object_name}:
{object_text}
            """,
            system_instructions="""
You are a gramatical AI that is an expert at replacing names in text.
You ONLY output the corrected text.
            """,
            max_new_tokens=300,
        )

        fill_data["name"] = object_name

        object_data = None
        for i in range(3):
            try:
                generated_data = self.generate(
                    f"""
Parse the {object_type} data from the following character description:
{object_text}
                    """,
                    system_instructions=f"""
You are an AI designed to parse {object_type} data out of descriptions. You are careful to escape quotation marks when needed because you ONLY output VALID JSON in the format:
{json.dumps(asdict(default_object))}
                    """,
                    max_new_tokens=1024,
                    json_out=True,
                )
                object_data = json.loads(generated_data)
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
        # TODO - generate list of nicknames
        return []

    def generate_for_npc(self, prompt: str, npc: NPC):
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
            return "new"
        npcs = ", ".join(
            [f"{npc.name}: {npc.description}" for npc in current_location.npcs]
        )
        need_to_generate = self.generate(
            f"""
The player wants to start a conversation:
{player_input}

The current location has the following people:
[{npcs}]

Do you need to generate another NPC?
            """,
            system_instructions="""
You are an AI RPG subsytem designed to identify whether the person the player wants to talk to is in the current location. You only respond with "yes" or "no"
            """,
            max_new_tokens=1,
        )
        if need_to_generate == "yes":
            return "new"
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
        leaving = self.generate(
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
        if leaving:
            return "leaving"
        sublocations = ", ".join(
            # todo get the sublocations and include descriptions
            current_location.sublocations
        )
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
        if existing_sublocation == "yes":
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


def strip_markdown(text):
    for token in ["```json", "```"]:
        text = "".join(text.split(token))

    return text
