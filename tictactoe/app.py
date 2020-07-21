import asyncio
import sys

from .form import get_socket_address
from .client import game_client
from .gui import show_game_board


async def _app_main(socket_address: (str, int)) -> None:
    """
    Internal entry point for running the application.
    """
    gui_queue = asyncio.Queue(maxsize=1)
    client_queue = asyncio.Queue()
    # run a coroutine for the guii and network client and wait for both
    await asyncio.wait([show_game_board(gui_queue, client_queue), game_client(socket_address, gui_queue, client_queue)])


def main() -> None:
    """
    Entry point for client scripts to run the game gui and network client
    """

    # get the server to connect to by displaying a form
    hostname, port = get_socket_address()
    if not hostname or not port:
        # exit if the form was cancelled
        sys.exit(1)

    # start the game app
    asyncio.run(_app_main((hostname, port)))
