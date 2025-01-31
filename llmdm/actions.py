# import json
import logging
from dataclasses import dataclass, fields
from enum import Enum

# from llmdm.data_types import Entity, Relation, prompt_dataclass, str_dataclass
from llmdm.game_data import GameData
from llmdm.utils import prompt_user_input, render_text

logger = logging.getLogger(__name__)


# actions that can be taken in conversation
class ConversationAction:
    pass


# actions that can be taken in conversation
class FreeModeAction:
    pass


class Action:
    def __init__(self, prompt_response):
        self.prompt_response = prompt_response

    @classmethod
    def get_input(cls):
        if (prompt_response := cls.prompt()) is not None:
            return cls(cls.prompt_type(**prompt_response))

    @classmethod
    def prompt(cls):
        prompt_response = {}
        for field in fields(cls.prompt_type):
            render_text('Enter "cancel" to cancel the action')
            while True:
                user_input = prompt_user_input(
                    f"Input {field.name} - {field.default}:\n"
                ).strip()
                if user_input:
                    if user_input.lower().strip() == "cancel":
                        return None
                    prompt_response[field.name] = user_input
                    break
        logger.debug(f"Action.prompt - {prompt_response=}")
        return prompt_response

    def perform(self, game: GameData):
        pass


@dataclass
class EmptyPrompt:
    pass


# ## @dataclass
# ## class AddInformationPrompt:
# ##     info_type: str = "entity or relation"
# ##     datum: Entity = Entity()
# ##
# ##
# ## class AddInformation(Action, FreeModeAction):
# ##     prompt_type = AddInformationPrompt
# ##
# ##     def __init__(self, *args, **kwargs):
# ##         super().__init__(*args, **kwargs)
# ##
# ##     @classmethod
# ##     def prompt(cls):
# ##         info_field = cls.prompt_type.__dataclass_fields__["info_type"]
# ##         prompt_response = {info_field.name: input(f"Input {info_field.default}:\n")}
# ##         try:
# ##             prompt_response["datum"] = prompt_dataclass(
# ##                 Relation(prompt_response["info_type"])
# ##                 if sanitize(prompt_response["info_type"]) == "relation"
# ##                 else Entity(prompt_response["info_type"])
# ##             )
# ##         except KeyError:
# ##             render_text(f"Sorry, {prompt_response['info_type']} is not a valid data type")
# ##             prompt_response["datum"] = None
# ##         logger.debug(f"Action.prompt - {prompt_response=}")
# ##         return prompt_response
# ##
# ##     def perform(self, game: GameData, **kwargs):
# ##         logger.debug(f"AddInformation.perform - {self.prompt_response}")
# ##         if self.prompt_response.datum is None:
# ##             return
# ##         try:
# ##             if isinstance(self.prompt_response.datum, Relation):
# ##                 game.add_relation(self.prompt_response.datum)
# ##             else:
# ##                 game.add_entity(self.prompt_response.datum)
# ##         except Exception as e:
# ##             logger.exception(f"AddInformation.perform: {e}")
# ##             if "document not found" in str(e):
# ##                 datum = self.prompt_response.datum
# ##                 render_text(f"Sorry, one of {datum._from}, {datum._to} doesn't exist.")
# ##             else:
# ##                 info_type = type(self.prompt_response.datum).__name__
# ##                 render_text(
# ##                     f"Sorry, {info_type}/{self.prompt_response.datum.name} already exists."
# ##                 )
# ##
# ##
# ## @dataclass
# ## class GetInformationPrompt:
# ##     info: str = "Name of person/place/thing"
# ##
# ##
# ## class GetInformation(Action, FreeModeAction):
# ##     prompt_type = GetInformationPrompt
# ##
# ##     def __init__(self, *args, **kwargs):
# ##         super().__init__(*args, **kwargs)
# ##
# ##     def perform(self, game: GameData, **kwargs):
# ##         logger.debug(f"GetInformation.perform - {self.prompt_response}")
# ##         try:
# ##             entity = game.get(self.prompt_response.info)
# ##             render_text(f"{self.prompt_response.info}:")
# ##             render_text(str_dataclass(entity))
# ##
# ##             relations = game.get_relations_for_entity(entity)
# ##             if relations:
# ##                 render_text(f"{self.prompt_response.info} has these relations:")
# ##             for relation in relations:
# ##                 logger.debug(f"GetInformation.perform - {relation}")
# ##                 render_text(str_dataclass(relation))
# ##
# ##         except Exception as e:
# ##             logger.exception(f"GetInformation.perform: {e}")
# ##             render_text(f"Sorry, {self.prompt_response.info} wasn't found.")
# ##
# ##
# ## @dataclass
# ## class AskQuestionPrompt:
# ##     question: str = "your question"
# ##
# ##
# ## class AskQuestion(Action, FreeModeAction):
# ##     prompt_type = AskQuestionPrompt
# ##
# ##     def __init__(self, *args, **kwargs):
# ##         super().__init__(*args, **kwargs)
# ##
# ##     # Todo update
# ##     def perform(self, game: GameData):
# ##         logger.debug(f"AskQuestion.perform - {self.prompt_response}")
# ##         entities_extracted = game.llm.generate(
# ##             prompt=f"""
# ## Parse the people, places, and objects from the following question into the json format:
# ## {self.prompt_response.question}
# ##             """,
# ##             system_instructions="""
# ## You are an AI trained to parse json data from questions. You ONLY output json. You output in the format:
# ## [
# ##     "person/<person-name>",
# ##     "place/<place-name>",
# ##     "object/<object-name>
# ## ]
# ##             """,
# ##             json_out=True,
# ##         )
# ##         logger.debug(
# ##             f"AskQuestion.perform - entities identified by llm: {entities_extracted}"
# ##         )
# ##         entities_list = json.loads(entities_extracted.strip())
# ##         entities_data = []
# ##         for entity_id in entities_list:
# ##             try:
# ##                 entity = game.get_entity_by_id(entity_id)
# ##                 entities_data.append(entity)
# ##                 entities_data.extend(
# ##                     game.get_relations_for_entity(entity),
# ##                 )
# ##             except Exception:
# ##                 logger.debug(f"{entity_id} not found")
# ##         context = "\n".join(set(map(str_dataclass, entities_data)))
# ##         logger.debug(f"AskQuestion: Gathered info for llm:\n{context}")
# ##         response = game.llm.generate(
# ##             prompt="\n".join(
# ##                 [
# ##                     "The user has a question about the story. Here is some helpful information:",
# ##                     context,
# ##                     "The user's question is:",
# ##                     self.prompt_response.question,
# ##                 ]
# ##             ),
# ##             system_instructions="You are an AI story teller backed by data storage. You answer in a way that preserves the immersion of the story, while answering the question directly.",
# ##         )
# ##         render_text(response)
# ##
# ##
# ## @dataclass
# ## class GenerateStoryPrompt:
# ##     prompt: str = "your prompt which will generate a story element"
# ##
# ##
# ## class GenerateStory(Action, FreeModeAction):
# ##     prompt_type = GenerateStoryPrompt
# ##
# ##     def __init__(self, *args, **kwargs):
# ##         super().__init__(*args, **kwargs)
# ##
# ##     def perform(self, game_data: GameData, **kwargs):
# ##         logger.debug(f"GenerateStory.perform - {self.prompt_response}")
# ##         render_text(
# ##             game_data.llm.generate_story(
# ##                 prompt=self.prompt_response.prompt, game_data=game_data
# ##             )
# ##         )


@dataclass
class DescribeScene(Action, FreeModeAction, ConversationAction):
    prompt_type = EmptyPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, game_data: GameData, **kwargs):
        game_data.describe_scene()


@dataclass
class GetGameState(Action, FreeModeAction, ConversationAction):
    prompt_type = EmptyPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, game_data: GameData, **kwargs):
        game_data.print_state()


@dataclass
class GetCurrentLocation(Action, FreeModeAction, ConversationAction):
    prompt_type = EmptyPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, game_data: GameData, **kwargs):
        render_text("The Current Location:")
        game_data.get_location(game_data.game_state.location).debug_describe()


@dataclass
class GetAllLocations(Action, FreeModeAction, ConversationAction):
    prompt_type = EmptyPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, game_data: GameData, **kwargs):
        for location in game_data.get_all_locations():
            location.debug_describe()


@dataclass
class GetAllNPCs(Action, FreeModeAction, ConversationAction):
    prompt_type = EmptyPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, game_data: GameData, **kwargs):
        for npc in game_data.get_all_npcs():
            npc.debug_describe()


@dataclass
class MovePrompt:
    prompt: str = "Where do you want to go?"


class Move(Action, FreeModeAction):
    prompt_type = MovePrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, game_data: GameData):
        logger.debug(f"Move.perform - {self.prompt_response}")
        move_type, location = game_data.get_location_to_move_to(
            self.prompt_response.prompt
        )
        game_data.travel_to(location, move_type=move_type)


@dataclass
class StartConversationPrompt:
    prompt: str = "Who do you want to talk to?"


class StartConversation(Action, FreeModeAction):
    prompt_type = StartConversationPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, game_data: GameData):
        logger.debug(f"Talk.perform - {self.prompt_response}")
        npc = game_data.get_npc_to_talk_to(self.prompt_response.prompt)
        if npc:
            game_data.transition_mode_to("conversation", npc=npc)
            return
        game_data.respond_npc_not_found(self.prompt_response.prompt)


@dataclass
class SayPrompt:
    prompt: str = "What do you say?"


class Talk(Action, ConversationAction):
    prompt_type = SayPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, game_data: GameData):
        logger.debug(f"Talk.perform - {self.prompt_response}")
        npc_ends_conversation = game_data.respond_as_npc_to_talking(
            self.prompt_response.prompt
        )
        if npc_ends_conversation:
            game_data.transition_mode_to("free")


@dataclass
class LeaveConversationPrompt:
    prompt: str = "What do you say as you leave?"


class LeaveConversation(Action, ConversationAction):
    prompt_type = LeaveConversationPrompt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def perform(self, game_data: GameData):
        logger.debug(f"LeaveConversation.perform - {self.prompt_response}")
        # does create combat?
        game_data.respond_as_npc_to_leaving(self.prompt_response.prompt)
        game_data.transition_mode_to("free")


@dataclass
class Exit(Action, FreeModeAction, ConversationAction):
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


def freemode_actions_enum():
    return Enum(
        "FreeModeActions",
        {
            subclass.__name__.lower(): subclass
            for subclass in FreeModeAction.__subclasses__()
        },
    )


FreeModeActions = freemode_actions_enum()
FreeModeActionNames = [member.value.__name__ for member in FreeModeActions]


def conversation_actions_enum():
    return Enum(
        "ConversationActions",
        {
            subclass.__name__.lower(): subclass
            for subclass in ConversationAction.__subclasses__()
        },
    )


ConversationActions = conversation_actions_enum()
ConversationActionNames = [member.value.__name__ for member in ConversationActions]
