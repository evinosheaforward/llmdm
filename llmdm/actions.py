import json
import logging
from dataclasses import dataclass, fields
from enum import Enum

from llmdm.data_types import (
    Entity,
    Relation,
    data_type_from_str,
    prompt_dataclass,
    str_dataclass,
)
from llmdm.generate import LLM
from llmdm.graph_client import DatabaseWrapper

logger = logging.getLogger(__name__)


class Action:
    def __init__(self, prompt_response):
        self.prompt_response = prompt_response

    @classmethod
    def get_input(cls):
        return cls(prompt_response=cls.prompt_type(**cls.prompt()))

    @classmethod
    def prompt(cls):
        prompt_response = {}
        for field in fields(cls.prompt_type):
            while True:
                user_input = input(f"Input {field.name} - {field.default}:\n").strip()
                if user_input:
                    prompt_response[field.name] = user_input
                    break
        logger.debug(f"Action.prompt - {prompt_response=}")
        return prompt_response

    def perform(self, db_wrapper: DatabaseWrapper):
        pass


@dataclass
class AddInformationPrompt:
    info_type: str = "a person, place, object, relation"
    datum: Entity = Entity()


class AddInformation(Action):
    prompt_type = AddInformationPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def prompt(cls):
        info_field = cls.prompt_type.__dataclass_fields__["info_type"]
        prompt_response = {info_field.name: input(f"Input {info_field.default}:\n")}
        # TODO add error handling
        try:
            prompt_response["datum"] = prompt_dataclass(
                data_type_from_str(prompt_response["info_type"])
            )
        except KeyError:
            print(f"Sorry, {prompt_response['info_type']} is not a valid data type")
            prompt_response["datum"] = None
        logger.debug(f"Action.prompt - {prompt_response=}")
        return prompt_response

    def perform(self, db_wrapper: DatabaseWrapper, **kwargs):
        logger.debug(f"AddInformation.perform - {self.prompt_response}")
        if self.prompt_response.datum is None:
            return
        try:
            if isinstance(self.prompt_response.datum, Relation):
                db_wrapper.add_relation(self.prompt_response.datum)
            else:
                db_wrapper.add_entity(self.prompt_response.datum)
        except Exception as e:
            logger.exception(f"AddInformation.perform: {e}")
            if "document not found" in str(e):
                datum = self.prompt_response.datum
                print(f"Sorry, one of {datum._from}, {datum._to} doesn't exist.")
            else:
                info_type = type(self.prompt_response.datum).__name__
                print(
                    f"Sorry, {info_type}/{self.prompt_response.datum.name} already exists."
                )


@dataclass
class GetInformationPrompt:
    info: str = "person/<name>, place/<name>, object/<name>"


class GetInformation(Action):
    prompt_type = GetInformationPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, db_wrapper: DatabaseWrapper, **kwargs):
        logger.debug(f"GetInformation.perform - {self.prompt_response}")
        try:
            info_type = data_type_from_str(self.prompt_response.info)
        except KeyError:
            print(
                f"Sorry, {self.prompt_response.info.split('/')[0]} is not a valid data type"
            )
        try:
            entity = db_wrapper.get_entity_by_id(self.prompt_response.info)
            print(f"{self.prompt_response.info}:")
            print(str_dataclass(entity))

            relations = db_wrapper.get_relations_for_entity(entity)
            print(f"{self.prompt_response.info} has these relations:")
            for relation in relations:
                logger.debug(f"GetInformation.perform - {relation}")
                print(str_dataclass(relation))

        except Exception as e:
            logger.exception(f"GetInformation.perform: {e}")
            print(f"Sorry, that {info_type.__name__} wasn't found.")


@dataclass
class AskQuestionPrompt:
    question: str = "your question"


class AskQuestion(Action):
    prompt_type = AskQuestionPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, db_wrapper: DatabaseWrapper, llm: LLM, **kwargs):
        logger.debug(f"AskQuestion.perform - {self.prompt_response}")
        entities_extracted = llm.generate(
            prompt=f"""
Parse the people, places, and objects from the following question into the json format:
{self.prompt_response.question}
            """,
            system_instructions="""
You are an AI trained to parse json data from questions. You ONLY output json. You output in the format:
[
    "person/<person-name>",
    "place/<place-name>",
    "object/<object-name>
]
            """,
        )
        logger.debug(
            f"AskQuestion.perform - entities identified by llm: {entities_extracted}"
        )
        entities_list = json.loads(entities_extracted.strip())
        entities_data = []
        for entity_id in entities_list:
            try:
                entity = db_wrapper.get_entity_by_id(entity_id)
                entities_data.append(entity)
                entities_data.extend(
                    db_wrapper.get_relations_for_entity(entity),
                )
            except Exception:
                logger.debug(f"{entity_id} not found")
        context = "\n".join(set(map(str_dataclass, entities_data)))
        logger.debug(f"AskQuestion: Gathered info for llm:\n{context}")
        response = llm.generate(
            prompt="\n".join(
                [
                    "The user has a question about the story. Use the following information to answer the question:",
                    context,
                    "The user's question is:",
                    self.prompt_response.question,
                ]
            )
        )
        print(response)


@dataclass
class EmptyPrompt:
    pass


@dataclass
class Exit(Action):
    prompt_type = EmptyPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


def actions_enum():
    return Enum(
        "Actions",
        {subclass.__name__.lower(): subclass for subclass in Action.__subclasses__()},
    )


Actions = actions_enum()
ActionNames = [member.value.__name__ for member in Actions]
