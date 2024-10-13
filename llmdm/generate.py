import json
import logging

from transformers import AutoTokenizer, pipeline

from llmdm.data_types import Relation, data_type_from_str

logger = logging.getLogger(__name__)


class LLM:
    def __init__(self):
        model_name = "meta-llama/Llama-3.2-3B-Instruct"
        # model_name = "meta-llama/Llama-3.2-1B-Instruct"
        # model_name = "meta-llama/Llama-3.1-8B-Instruct"
        # model_name = "ISTA-DASLab/Meta-Llama-3.1-70B-Instruct-AQLM-PV-2Bit-1x16"
        # model_name = "models--Qwen--Qwen2.5-14B-Instruct"
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
        generated_text = self.pipeline(
            messages,
            max_new_tokens=max_new_tokens,
            pad_token_id=self.pipeline.tokenizer.eos_token_id,
        )[0]["generated_text"][-1]["content"]
        if json_out:
            return strip_markdown(generated_text)
        return generated_text

    def generate_story(self, *, prompt=None, db_wrapper):
        if prompt is None:
            prompt = "Generate a person, place and object. Describe each of them briefly and decribe how they are related."
        generated_text = self.generate(prompt, max_new_tokens=256)
        logger.debug(f"LLM.generate_story - story:\n{generated_text}")

        for i in range(3):
            save_data_instructions = """
You are an AI that parses the most essential data from stories.
You ONLY output VALID JSON, have your output be a list of data with types person, place, object of the format:
{"type": "<person/place/object>", "name": "<name>",  "description": "<description of noun>"}
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
                logger.error(f"failed to save data (attempt {i}):\n{data_generated}")

        for i in range(3):
            save_relations_instructions = """
You are an AI that parses the most essential relationstips between nouns in stories.
You ONLY output VALID JSON data, have your output be a list of relation objects of the format:
{"description": "<description of relation>", "_from": "<type>/<name>", "_to": "<type>/<name>"}
            """

            noun_ids = ", ".join([f'{d["type"]}/{d["name"]}' for d in nouns_data])
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
                logger.error(
                    f"failed to save data (attempt {i}):\n{relations_generated}"
                )

        for entity_or_relation in nouns_data + relations_data:
            try:
                if "type" in entity_or_relation:
                    data_type = data_type_from_str(entity_or_relation.pop("type"))
                else:
                    data_type = Relation

                datum = data_type(**entity_or_relation)
                if data_type.__name__ == "Relation":
                    db_wrapper.add_relation(datum)
                else:
                    db_wrapper.add_entity(datum)
            except Exception as e:
                logger.debug(f"Entity/Relation type invalid: {entity_or_relation}")
                logger.debug(f"with error: {str(e)}")
        return generated_text


def strip_markdown(text):
    for token in ["```json", "```"]:
        text = "".join(text.split(token))

    return text
