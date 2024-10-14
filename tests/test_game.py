import timeout_decorator
from mock import patch

from llmdm.game import Game


def run_game_with_timeout(timeout=5):

    @timeout_decorator.timeout(timeout)
    def _run_game_with_timeout():
        Game("test").run()

    return _run_game_with_timeout()


class TestGame:
    @patch("builtins.input", side_effect=["load", "exit"])
    def test_exit(self, mocked_input):
        run_game_with_timeout(5)
