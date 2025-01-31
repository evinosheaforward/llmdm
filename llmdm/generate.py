import json
import logging
import os
import re
from dataclasses import asdict, dataclass

from openai import OpenAI

from llmdm.character import Character
from llmdm.data_types import Entity, Relation
from llmdm.location import Location
from llmdm.npc import NPC
from llmdm.utils import prompt_user_input, render_text, suppress_stdout

with suppress_stdout():
    from transformers import AutoTokenizer, pipeline


logger = logging.getLogger(__name__)


class LLM:
    def __init__(self):
        self.USE_OAI = os.getenv("USE_OPENAI")
        if self.USE_OAI:
            self.client = OpenAI()
        else:
            # model_name = "meta-llama/Llama-3.1-8B-Instruct"
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
        render_text(".")
        logger.debug(f"LLM.generate - system:\n{system_instructions}")
        logger.debug(f"LLM.generate - user:\n{prompt}")
        messages = [
            {
                "role": "system",
                "content": system_instructions.strip(),
            },
            {"role": "user", "content": prompt.strip()},
        ]
        if self.USE_OAI:
            response_format = {"type": "json_object"} if json_out else None
            generated_text = (
                self.client.chat.completions.create(
                    messages=messages,
                    model="gpt-4o",
                    response_format=response_format,
                )
                .choices[0]
                .message.content
            )
        else:
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
        nicknames=False,
        extra_prompt=None,
        name=None,
        prompt_user: bool = False,
    ):
        """
        cls should be a data class with default values of descriptions of the fields for the llm
        """
        object_type = cls.__name__
        default_object = cls()
        fields = [k for k in asdict(default_object) if k not in fill_data]

        logger.debug(f"Generating new {object_type}...")
        llm_prompt = f"""
Create a detailed {object_type} for our text-based RPG game.
Include the following data: {', '.join(fields)}
"""
        if prompt_user:
            info = prompt_user_input(f"Give your idea for the {object_type}:\n")
            llm_prompt += f"""\n**Player's Description**
{info}
            """
            render_text("\nGenerating..")
        if extra_prompt:
            llm_prompt += f"\n\n{extra_prompt}"

        if not name and cls == NPC:
            name_instruct = "Create an NPC with a name that is unique to this setting and avoid commonly used fantasy names like Elara, Mira, Thorne, and Bran. Create names that are unfamiliar yet fit within a medieval fantasy world."
        else:
            name_instruct = ""

        object_text = self.generate(
            prompt=llm_prompt,
            system_instructions=f"""
You are a part of an expert AI Dungeon Master. You are the AI designed to create a {object_type} for the game.
You ONLY output the description of the ONE {object_type} you generate.
{name_instruct}
            """,
            max_new_tokens=1000,
        )

        # should be inserting name into generating prompt
        #         if name:
        #             fill_data["name"] = name
        #             object_text = self.generate(
        #                 prompt=f"""
        # Correct all references to the {object_type} in this passage with {name}:
        # {object_text}
        #                 """,
        #                 system_instructions="""
        # You are a gramatical AI that is an expert at replacing names in text.
        # You ONLY output the corrected text.
        #                 """,
        #                 max_new_tokens=1200,
        #             )

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
                    max_new_tokens=1500,
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

    def generate_nicknames(self, obj: dataclass) -> list:
        nicknames = (
            self.generate(
                f"""
Generate a list of names for the entity below. Include both title-based names that reference the {type(obj).__name__}’s role or description and familiar, name-based nicknames.

{obj.describe()}

Provide a list of 3-5 comma separated names, with a mix of role/description-based titles and name-based nicknames.
ONLY output the list of nicknames and no other information.
                """,
                system_instructions=f"""
You are creating alternate names for a {type(obj).__name__} in a text-based RPG. Generate a mix of two types of names:
1. **Occupation/Location-Based Titles**: Names that reflect the {type(obj).__name__}’s traits
2. **Name-Based Nicknames**: Shortened versions, affectionate names, or playful adaptations based on the character’s actual name.

- Ensure that all names connect to the {type(obj).__name__}’s traits, role, or background.
- Avoid random names; keep each suggestion grounded in the {type(obj).__name__}’s identity.

Provide a list of 3-5 comma separated names, with a mix of both title-based and name-based options.
                """,
                max_new_tokens=50,
            )
            .strip()
            .split(", ")
        )
        logger.debug(f"generate_nicknames: {nicknames}")
        if type(obj) is NPC:
            nicknames.append(obj.name.split(" ")[0])

        return list(set(n.strip() for n in nicknames))

    def generate_for_npc(
        self, prompt: str, npc: NPC, motivation: str, player_name: str
    ):
        def _sanitize(generated):
            generated = generated.split("player: ")[0]
            generated = "".join(generated.split(f"{npc.name}: ")).strip()
            return generated

        generated_response = _sanitize(
            self.generate(
                prompt=f"""
You are an NPC named {npc.name}, {npc.description}.
You motivation is: {motivation}

{npc.name} currently has an affinity status of {npc.relationship_status} toward the player.
Based on this affinity status, adjust the tone and choice of words to reflect this relationship.

Respond to the player with a short dialogue sample showing how the NPC would speak to them at this affinity level."
Remember that the player is {player_name}. Always refer to "{player_name}" as "you".

Respond as {npc.name} to the player's latest reply:
{prompt}
                """,
                system_instructions="""
You are a AI Dungeon Master roleplaying an NPC in a text-based RPG. This means you are the Narrator AND the NPC.
You will role-play various NPC characters who interact with the player. When responding as an NPC:

1. **Refer to the Player as "You"**: Always address the player as "you", keeping the conversation focused on their experience.
2. **Speak in the First Person**: Only speak in the first person, as though the NPC is talking directly to the player.
3. **Narrate in the Third Person**: Describe actions, reactions, or emotions of the NPC in the 3rd person as seen from the player’s perspective. Avoid describing anything the player cannot directly observe about the NPC.
4. **Stay in Character**: Respond in a manner consistent with the NPC’s personality, background, and relationship with the player.
5. **Do not repeat**: Do not repeat what has already been said or happened during the conversation.

Always respond as though you are continuing an in-character conversation, creating immersive dialogue that feels natural and engaging for the player.
Remember to speak directly to the player as "you", but use the third person to describe the NPC's actions, and stay in character when writing dialogue.
Keep your responses short (1-4 sentences) in order to keep the narrative engaging for the player.
                """,
                max_new_tokens=256,
            )
        )
        edited_response = self.remove_unfinished(generated_response, max_new_tokens=256)
        render_text(edited_response)
        return f"{npc.name}: {edited_response}"

    def remove_unfinished(self, text, max_new_tokens=256):
        return self.generate(
            prompt=f"""
Remove any unfinished sentences or thoughts from the end of this text:
{text}
            """,
            system_instructions="""
You are an expert AI designed to remove any unfinished thoughts from text. You output ONLY output the text you have edited.
            """,
            max_new_tokens=max_new_tokens,
        )

    def does_end_conversation(self, conversation):
        split_convo = conversation.split("player:")
        if len(split_convo) < 1:
            return False
        trunc_conversation = "player:".join(split_convo[-3:])
        return (
            "yes"
            == self.generate(
                prompt=f"""
Based on the following recent conversation, determine if the NPC intends to end the conversation. Answer only with "Yes" if the NPC is concluding or signaling the end of the conversation, or "No" if the NPC is open to further interaction.

{trunc_conversation}

Is the NPC ending the conversation?
            """,
                system_instructions="""
You are determining if an NPC in a text-based RPG is ending the conversation with the player. Review the recent exchange between the NPC and the player to decide if the NPC’s latest response indicates an end to the conversation.

- Respond with "Yes" if the NPC’s latest response signals that they are concluding the conversation or implying there’s nothing further to discuss.
- Respond with "No" if the NPC is open to further interaction or invites the player to continue the conversation.

Answer only with "Yes" or "No" based on the NPC’s intent to end or continue the dialogue.
                """,
                max_new_tokens=1,
            )
            .strip()
            .lower()
        )

    def get_npc_name(self, player_input: str, current_location: Location) -> str:
        if not current_location.npcs:
            return None
        npcs = "- " + "\n- ".join(
            [f"{npc.name}: {npc.description}" for npc in current_location.npcs]
        )
        exists = self.generate(
            f"""
The player wants to start a conversation with: {player_input}

The current location has the following people:
{npcs}

Is there a person matching that description or with that name?
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

    def is_quest(self, motivation: str) -> bool:
        decision = (
            self.generate(
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
            .strip()
            .lower()
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

Remember, only output a JSON list an no other text
                    """,
                    system_instructions="""
You are an AI designed to parse a list of NPC *names* out of descriptions. You are careful to escape quotation marks when needed in order to output valid JSON.
                    """,
                    max_new_tokens=512,
                    json_out=True,
                )
                obj_list = list(set(json.loads(generated_data)))
                break
            except Exception as e:
                logger.info(f"Could not parse json response attempt {i}: {e}")

        if not obj_list:
            raise ValueError(f"Could not create a {object_type}...")

        logger.debug(f"parse_out: {object_type}: {obj_list}")
        return obj_list

    def match_npcs_to_locations(
        self, description: str, locations: list[Location], npcs: list[NPC]
    ):
        people = "\n".join(f"{npc.name}: {npc.description}" for npc in npcs)
        places = "\n".join(f"{loc.name}: {loc.description}" for loc in locations)
        template = json.dumps(
            {npc.name: "<location>" for npc in npcs},
            indent=2,
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

locations:
{places}

Fill in the <location> placeholders with the location names above in the following json.
{template}

Remember to output a JSON map from person name to location name.
                    """,
                    system_instructions="""
You are an AI designed to identify which locations in town people will be in for a DnD game.
Given serveral people and places, match each person with a location by filling in the <location> placeholders.
Be careful to escape quotation marks when needed and ONLY output VALID JSON.
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

        logger.info(f"npc to location matches:\n{json.dumps(matches, indent=2)}")

        npc_map = {npc.name: npc for npc in npcs}
        location_map = {loc.name: loc for loc in locations}
        for npc_name, location_name in matches.items():
            npc = npc_map.get(npc_name)
            location = location_map.get(location_name)
            if location and npc:
                location.npcs.append(npc)
            else:
                logger.info(f"one of {npc_name=}, {location_name=} not found")

    def going_nearby(self, player_input: str, nearby_locations: list[str]):
        nearby_locations_str = "- " + "\n- ".join(nearby_locations)
        nearby = (
            self.generate(
                f"""
The player wants to go to:
{player_input}

nearby locations include:
{nearby_locations_str}

Is the player going to one of the nearby locations?
            """,
                system_instructions="""
You are an AI RPG subsytem designed to identify where the player wants to go. You only respond with "yes" or "no"
            """,
                max_new_tokens=1,
            )
            .strip()
            .lower()
        )
        if nearby == "no":
            return "no"
        return (
            self.generate(
                f"""
The player wants to go to:
{player_input}

which of the following locations does the player want to go to?
{nearby_locations_str}

respond with only one location name
                """,
                system_instructions="""
You are an AI designed to determine which location the player wants to go given their request and the list of available locations.You ONLY respond with the ONE location the player wants to go to.
                """,
                max_new_tokens=8,
            )
            .strip()
            .lower()
            .replace("- ", "")
        )

    def generate_affinity_data(
        self, npc: NPC, player_character: Character
    ) -> (int, str):
        logger.info("generating affinity data")
        affinity_data = json.loads(
            self.generate(
                prompt=f"""
Player Character Information:
{player_character.describe()}

NPC Information:
{npc.describe()}

Use the information given about the player and the NPC to determine the NPC's initial disposition toward the player.
Remember to output your answer ONLY in JSON format.
                """,
                system_instructions="""
You are an AI language model tasked with generating JSON output containing an NPC's (Non-Player Character's) initial affinity information for a text-based RPG. The affinity the NPC has for the player is represented by two attributes:

1. **affinity_score**: An integer that determines the NPC's relationship status toward the player, based on the following scale:

- If `affinity_score <= -50`:
    - Status: **"Enemy"**
- If `-49 <= affinity_score <= -10`:
    - Status: **"Rival"**
- If `-9 <= affinity_score <= 9`:
    - Status: **"Neutral"**
- If `10 <= affinity_score <= 49`:
    - Status: **"Friendly"**
- If `50 <= affinity_score <= 89`:
    - Status: **"Ally"**
- If `90 <= affinity_score`:
    - Status: **"Loved One"**

2. **affinity_type**: A string indicating how the NPC's affinity for the player can change over time. The types are:

    - **"fixed"**: These NPCs have no capacity to shift their opinions or affinities through regular actions. They hold a consistent perspective, either due to an intrinsic personality trait (e.g., strong-willed, resolute) or because of past events that make them immovable.
    - **"dynamic"**: These NPCs are naturally adaptable and responsive, able to change their perspective more frequently. However, each change is slightly less intense, representing a slower but constant potential for influence. Dynamic NPCs’ affinity scores might fluctuate with smaller events and interactions, allowing for more dynamic, story-driven responses.
    - **"deciding"**: These NPCs are initially open to influence but become gradually more resistant as their affinity changes. Each significant shift (e.g., from neutral to friendly, or friendly to ally) makes them less responsive to further changes.

**Output Format:**

Please generate the output in the following JSON format:
{
  "affinity_score": <integer>,
  "affinity_type": "<fixed|dynamic|deciding>"
}

**Instructions:**

- Ensure that the `affinity_score` is an integer within the appropriate range corresponding to one of the statuses.
- The `affinity_type` should be one of the specified types: "fixed", "dynamic", or "deciding".
- Do not include any additional text outside of the JSON structure.
                """,
                max_new_tokens=250,
                json_out=True,
            )
        )
        return affinity_data["affinity_score"], affinity_data["affinity_type"]

    def affinity_score_change(self, npc: NPC, conversation: str) -> int:
        affinity_change = json.loads(
            self.generate(
                prompt=f"""
The following is a description of the NPC:
{npc.describe()}

A player has just had the following conversation with the NPC {npc.name}:
{conversation}

The NPC ({npc.name}) currently has an affinity score of {npc.affinity_score} with the player, which places them in the {npc.relationship_status} range. Consider the NPC’s personality traits, relationship type, and recent interactions with the player.

Does this interaction:

    Increase the affinity that the NPC has for the player slightly, moderately, or significantly?
    Decrease the affinity that the NPC has for the player slightly, moderately, or significantly?
    Have no effect because it’s repetitive or unimportant?

Remember the Output Requirements:
- Format: The output must be in JSON format. Do not output any other explaination other than the JSON.
- Fields:
    - `change`: The numerical change in affinity score (positive for increase, negative for decrease).
    - `reason`: A brief description explaining why this action caused the score change.
""",
                system_instructions="""
You are assisting with a text-based RPG where players interact with NPCs (non-player characters). Each NPC has an affinity score toward the player, represented on a scale from -100 to 100. This affinity score reflects the NPC’s relationship toward the player, which is influenced by the player’s actions and the NPC’s personality.

Affinity Ranges:
- Enemy: -100 to -50
- Rival: -49 to -10
- Neutral: -9 to 9
- Friendly: 10 to 49
- Ally: 50 to 89
- Loved One: 90 to 100

Scoring Change Guide:
- Determine how much an action affects the affinity score, using these guidelines:
  - Slight Change: ±1–3 points for minor actions or actions with little emotional impact.
  - Moderate Change: ±4–7 points for actions of moderate significance.
  - Significant Change: ±8–10 points for highly impactful actions or pivotal events in the relationship.
- Use negative values for actions that decrease affinity and positive values for actions that increase affinity.

Output Requirements:
- Format: The output must be in JSON format. Do not output any other explaination other than the JSON.
- Fields:
    - `change`: The numerical change in affinity score (positive for increase, negative for decrease).
    - `reason`: A brief description explaining why this action caused the score change.
""",
                max_new_tokens=400,
                json_out=True,
            )
        )
        logger.info(f"{json.dumps(affinity_change, indent=2)}")
        return affinity_change["change"]

    def summarize_conversation(
        self, npc: str, conversation: str, npc_motivation: str, **kwargs
    ):
        return self.generate(
            f"""
Summarize the conversation between the player and the NPC. Focus on the key facts, including topics discussed, the NPC’s responses, and any notable outcomes. The summary should be short, factual, and consistent for future reference.

**NPC Name**: {npc}
**NPC Motivation**: {npc_motivation}
**Conversation Details**:
{conversation}

Provide a short, factual summary of this conversation. Keep your summary to 200 tokens.
            """,
            system_instructions="""
You are summarizing conversations between a player and an NPC in a text-based RPG. Focus on capturing the key points, topics discussed, the NPC’s motivations, and any notable outcomes or player decisions. Keep the summary concise and factual to ensure consistency in future interactions with the NPC.

Ensure the summary includes:
1. The main topics or questions covered.
2. The NPC’s responses and any key details shared.
3. Any notable player decisions or actions taken.
            """,
            max_new_tokens=220,
        )

    def summarize_npc_history(self, npc: NPC, history: list[dict]):
        events_text = "\n".join(json.dumps(item) for item in history)
        return self.generate(
            f"""
Summarize the history of interactions between the player and the NPC based on the following event data. Highlight the main themes, important events, and any relationship changes.

**NPC**
{npc.describe()}

**Event History**:
{events_text}

Provide a concise summary of the history of the relationship between the player and the NPC based on the event history.
            """,
            system_instructions="""
You are summarizing the history of interactions between a player character and an NPC based on event data. Focus on consolidating the key interactions, notable events, and relationship developments. Your goal is to create a summary that highlights the progression of the relationship and any significant changes or outcomes over time.

When summarizing:
1. Identify recurring themes or important topics in the interactions.
2. Highlight any major decisions or pivotal moments between the NPC and the player.
3. Ensure the summary remains factual and concise for future reference in the game.
            """,
            max_new_tokens=1000,
        )


def strip_markdown(text):
    for token in ["```json", "```"]:
        text = "".join(text.split(token))

    return text
