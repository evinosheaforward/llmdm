import logging
import os
import sys
from logging.handlers import RotatingFileHandler

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
from llmdm.utils import (
    SAVE_DIR,
    prompt_user_input,
    render_text,
    start_display_thread,
    stop_display_thread,
)
from llmdm.vector_client import OpenSearchClient

logger = logging.getLogger("llmdm.game")


class Game:
    def __init__(self, logs=False, save_name="SavedGame"):
        self.save_name = save_name
        setup_logger(logs=logs)
        self.story = ""
        self.action = None
        self.action_type = None

        saved_games = [
            os.path.splitext(f)[0] for f in os.listdir(SAVE_DIR) if f.endswith(".json")
        ]

        while (
            load_or_new := prompt_user_input("[Load] game or start a [new] one?\n")
            .strip()
            .lower()
        ) not in ("load", "new"):
            continue
        if load_or_new == "load":
            game_name = prompt_user_input(
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
            while True:
                save_name = prompt_user_input(
                    "What do you want to name your new game?\n"
                ).lower()
                if save_name in saved_games:
                    print(
                        f"Sorry, {save_name} is in your previously saved games, please choose a name not in the following list:\n"
                        + "- "
                        "\n - ".join(saved_games)
                    )
                else:
                    break

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
            prompt_user_input(f"Select Action:\n{', '.join(available_actions)}\n")
            .strip()
            .lower()
            .split()
        )
        try:
            self.action_type = actions_enum[self.action_response]
        except KeyError:
            render_text("Invalid Action")
            self.action = None
            return
        self.action = self.action_type.value.get_input()

    def resolve(self):
        self.action.perform(game_data=self.game_data)

    def run(self):
        start_display_thread()
        while True:
            try:
                self.prompt()
                logger.debug(f"{self.action=}, {self.action_type=}")
                if self.action is None:
                    continue
                if self.action_type.value == Actions.exit.value:
                    render_text("Game Ended")
                    break
                self.resolve()
                self.game_data.save()
            except Exception as e:
                stop_display_thread()
                raise e
        stop_display_thread()


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


def setup_logger(logs=False):
    log_file = "/tmp/llmdm.log"

    logger = logging.getLogger("llmdm")
    logger.setLevel(logging.DEBUG)  # Set to debug level
    handler = RotatingFileHandler(
        log_file,
        mode="a",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding=None,
        delay=0,
    )
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if logs:
        # Console (stdout) handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    logger.info("**************** NEW SESSION STARTED ****************")

    return logger


if __name__ == "__main__":
    run(Game().run())
