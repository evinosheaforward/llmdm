import logging
import os
import sys

from llmdm.actions import (
    Actions,
    ConversationActionNames,
    ConversationActions,
    FreeModeActionNames,
    FreeModeActions,
)
from llmdm.character import Character
from llmdm.game_data import GameData, GameState
from llmdm.generate import LLM
from llmdm.graph_client import GraphClient
from llmdm.nouns_lookup import ProperNounDB
from llmdm.sql_client import SQLClient
from llmdm.utils import SAVE_DIR
from llmdm.vector_client import OpenSearchClient

logger = logging.getLogger("Game")


class Game:
    def __init__(self, logs=False, save_name="SavedGame"):
        self.save_name = save_name
        if logs:
            logging.basicConfig(
                level=logging.DEBUG,
                stream=sys.stdout,
                format="%(asctime)s - %(levelname)s - %(message)s",
            )
        self.story = ""
        self.action = None
        self.action_type = None

        logger.debug("Game - Loading Lanugage Model")
        logger.debug("Game - Loaded Lanugage Model")

        while (
            load_or_new := input("[Load] game or start a [new] one?\n").strip().lower()
        ) not in ("load", "new"):
            continue
        saved_games = [
            os.path.splitext(f)[0] for f in os.listdir(SAVE_DIR) if f.endswith(".json")
        ]
        if load_or_new == "load":
            game_name = input(
                "Which game to play?:\n- " + "\n- ".join(saved_games) + "\n"
            )
            game_state = GameState.from_save(game_name.strip().lower())
            self.game_data = GameData(
                llm=LLM(),
                sql_db=SQLClient(game_name),
                graph_db=GraphClient(game_name),
                vector_db=OpenSearchClient(game_name),
                player_character=Character.from_save(game_name),
                noun_db=ProperNounDB(game_name),
                game_state=game_state,
                save_name=game_name,
            )
        else:
            save_name = input("What do you want to name your new game?\n")
            self.game_data = GameData.new_game(save_name)

        self.game_data.print_state()

    def prompt(self):
        if self.game_data.game_state.mode == "free":
            actions_enum = FreeModeActions
            available_actions = FreeModeActionNames
        elif self.game_data.game_state.mode == "conversation":
            actions_enum = ConversationActions
            available_actions = ConversationActionNames

        self.action_response = "".join(
            input(f"Select Action:\n{', '.join(available_actions)}\n")
            .strip()
            .lower()
            .split()
        )
        try:
            self.action_type = actions_enum[self.action_response]
        except KeyError:
            print("Invalid Action")
            self.action = None
            return
        self.action = self.action_type.value.get_input()

    def resolve(self):
        self.action.perform(game_data=self.game_data)

    def run(self):
        while True:
            self.prompt()
            logger.debug(f"{self.action=}, {self.action_type=}")
            if self.action is None:
                continue
            if self.action_type.value == Actions.exit.value:
                print("Game Ended")
                return
            self.resolve()
            self.game_data.save()


def run():
    if len(sys.argv) > 1:
        Game(save_name=sys.argv[1]).run()
    else:
        Game().run()


def run_debug():
    if len(sys.argv) > 1:
        Game(logs=True, save_name=sys.argv[1]).run()
    else:
        Game(logs=True).run()


if __name__ == "__main__":
    run(Game().run())
