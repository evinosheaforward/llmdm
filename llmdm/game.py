import logging
import sys

from llmdm.actions import ActionNames, Actions
from llmdm.generate import LLM
from llmdm.graph_client import DatabaseWrapper

logger = logging.getLogger("Game")


class Game:
    def __init__(self, logs=False, db_name="my_graph_db"):
        if logs:
            logging.basicConfig(
                level=logging.DEBUG,
                stream=sys.stdout,
                format="%(asctime)s - %(levelname)s - %(message)s",
            )
        self.story = ""
        self.action = None
        self.action_type = None
        self.db_wrapper = DatabaseWrapper(db_name=db_name)
        logger.debug("Game - Loading Model")
        self.llm = LLM()
        logger.debug("Game - Loaded Model")

    def prompt(self):
        self.action_response = "".join(
            input(f"Select Action:\n{', '.join(ActionNames)}\n").strip().lower().split()
        )
        try:
            self.action_type = Actions[self.action_response]
        except KeyError:
            print("Invalid Action")
            self.action = None
            return
        self.action = self.action_type.value.get_input()

    def resolve(self):
        self.action.perform(db_wrapper=self.db_wrapper, llm=self.llm)

    def validate(self):
        pass

    def run(self):
        while True:
            self.prompt()
            logger.debug(f"{self.action=}, {self.action_type=}")
            if self.action is None:
                continue
            if self.action_type == Actions.exit:
                print("Game Ended")
                return
            self.validate()
            self.resolve()


def run():
    Game().run()


def run_debug():
    Game(logs=True).run()


if __name__ == "__main__":
    run(Game().run())
