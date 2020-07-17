from ipaddress import ip_address
from functools import partial
from typing import Optional
import asyncio
import PySimpleGUI as sg
import re
import sys


def is_ip_address(address: str) -> bool:
    """
    Returns true if the string contains a valid tcpv4 address
    """
    try:
        ip_address(address)
    except ValueError:
        return False
    return True


def is_port(port: str) -> bool:
    """
    Returns true if the string contains a valid port number
    """
    try:
        port_value = int(port)
        return port_value > 0 and port_value <= 65535
    except ValueError:
        return False


def get_socket_address() -> (str, int):
    """
    Shows a connection form for a user to input an address. The form will not close
    until a valid input is received or the user clicks the close button.
    Returns a valid (hostname, port) tuple if the user did not close the form, otherwise 
    it returns (None, None).
    """
    while True:
        was_cancelled, hostname, port = show_address_form()
        if was_cancelled:
            return (None, None)
        elif is_ip_address(hostname) and is_port(port):
            return hostname, int(port)
        else:
            sg.popup_ok('Invalid hostname or port', title='Error',
                        button_color=sg.DEFAULT_ERROR_BUTTON_COLOR)


def show_address_form() -> (bool, str, str):
    """
    Displays a form to input a socket address. Returns a tuple (was_cancelled,
    hostname, port) where was_cancelled will be True if the user closed the form
    rather than submitting valid input.
    """
    label_size = (14, 1)
    event, values = sg.Window(
        'Enter connection info',
        [
            [sg.Text('Hostname:', size=label_size),
             sg.InputText(key='HOST')],
            [sg.Text('Port:', size=label_size),
                sg.InputText(key='PORT')],
            [sg.Button('Connect')]
        ]).read(close=True)
    hostname = values['HOST']
    port = values['PORT']
    was_cancelled = event in (sg.WIN_CLOSED, 'Cancel')
    return (was_cancelled, hostname, port)


async def show_game_board(gui_queue: asyncio.Queue(), client_queue: asyncio.Queue) -> None:
    """
    Creates a window with the game GUI that runs until closed or the game finishes.
    """
    EMPTY_CELL = '_'
    STATUS_KEY = 'STATUS'
    PLAYER_KEY = 'PLAYER'

    # create checkerboard layout, text showing player's token, and game status text
    layout = [
        [sg.Frame('', [[sg.Button(EMPTY_CELL, key=f'BUTTON_{r}_{c}')
                        for r in range(3)] for c in range(3)],
                  element_justification='center')],
        [sg.Text('You are player: ?', key=PLAYER_KEY)],
        [sg.Text('Waiting for game to start...',
                 key=STATUS_KEY)]
    ]
    window = sg.Window('Tic Tac Toe', layout, element_justification='center')

    token = ''  # player's token
    is_turn = False
    game_is_over = False

    # continue until window is closed or connection lost
    while True:
        event, _ = window.read(timeout=100)
        if event in (sg.WIN_CLOSED, 'Cancel'):
            await gui_queue.put('closed')
            break
        else:
            # check if button click, which means we're submitting a turn
            match = re.match(r'^BUTTON_(\d)_(\d)$', event)
            if match and token and is_turn and not game_is_over:
                is_turn = False
                # send move to network client
                row, col = (int(g) for g in match.groups())
                await gui_queue.put(f'TURN {token} {row} {col}\n')
                # get the Button element, set it to show our token, and disable it
                window[event].Update(text=token, disabled=True)

        await asyncio.sleep(0.001)

        # check for data from network client
        if not client_queue.empty():
            message = await client_queue.get()
            if message['status'] == 'error':
                # got an error
                if not game_is_over:
                    # don't show error if game is over
                    sg.popup_ok('Error ' + message['data'], title='Error',
                                button_color=sg.DEFAULT_ERROR_BUTTON_COLOR)
                    break
            else:
                # got some kind of game status udpate
                data = message['data'].split(' ')
                action = data[0]
                if action == 'PLAYER':
                    # received player token
                    token = data[1]
                    # update player label
                    label = window['PLAYER']
                    label.update(label.Get().replace('?', token))
                elif action == 'INVALID':
                    # write that previous move was invalid
                    window[STATUS_KEY].update('Your move was invalid')
                elif action == 'TURN':
                    # opponent took a turn
                    _, op_token, row, col = data
                    window[STATUS_KEY].update(
                        f'{op_token} moved in {row},{col}')
                    window[f'BUTTON_{row}_{col}'].Update(
                        text=op_token, disabled=True)
                elif action == 'MOVE':
                    # it's our turn
                    is_turn = True
                    window[STATUS_KEY].update("It's your turn")
                elif action == 'WINNER':
                    # game is over
                    game_is_over = True
                    _, winner_token = data
                    window[STATUS_KEY].update(
                        f"{'You' if winner_token == token else winner_token} won")

    window.close()


def main() -> None:
    """
    Entry point for client scripts to run the game gui and network client
    """
    sg.theme('DarkAmber')

    # get the server to connect to by displaying a form
    hostname, port = get_socket_address()
    if not hostname or not port:
        # exit if the form was cancelled
        sys.exit(1)

    # start the game app
    asyncio.run(app_main((hostname, port)))


async def app_main(socket_address: (str, int)) -> None:
    """
    Internal entry point for running the application.
    """
    gui_queue = asyncio.Queue(maxsize=1)
    client_queue = asyncio.Queue()
    # run a coroutine for the guii and network client and wait for both
    await asyncio.wait([show_game_board(gui_queue, client_queue), game_client(socket_address, gui_queue, client_queue)])


def on_read(read_chunks: asyncio.Queue, fut: asyncio.Future):
    if fut.cancelled():
        return
    elif fut.exception():
        read_chunks.put_nowait('EOF')
    else:
        line = fut.result()
        if not line or not line.endswith(b'\n'):
            # EOF received - line is empty or incomplete
            read_chunks.put_nowait('EOF')
        line = line.decode('utf-8').rstrip('\n')
        read_chunks.put_nowait(line)


async def game_client(socket_address: (str, int), gui_queue: asyncio.Queue, client_queue: asyncio.Queue) -> None:
    """
    Runs a network client for interacting with the game server.
    """
    reader: asyncio.StreamReader = None
    writer: asyncio.StreamWriter = None
    try:
        reader, writer = await asyncio.open_connection(*socket_address)
    except ConnectionRefusedError:
        client_queue.put_nowait(
            {'status': 'error', 'data': 'connection refused'})
        return

    connected = True
    read_chunks = asyncio.Queue()
    pending_writes = asyncio.Queue(maxsize=1)
    read_done, read_task = True, None
    write_done, write_task = True, None

    # interact with the server forever until it closes its end of the connection
    while connected:
        if read_done:
            # schedule a new read
            read_task = asyncio.create_task(reader.readline())
            read_task.add_done_callback(
                partial(on_read, read_chunks)
            )
            read_done = False
        elif read_task:
            read_done = read_task.done()
        await asyncio.sleep(0.001)

        # let the network client check for unrecoverable errors
        while not read_chunks.empty():
            chunk = read_chunks.get_nowait()
            print(f"client: received '{chunk}''")

            if chunk in ('EOF'):
                client_queue.put_nowait(
                    {'status': 'error', 'data': 'connection closed'})
                connected = False
                break
            elif chunk == 'TICTACTOE':
                # schedule a write
                pending_writes.put_nowait('TICTACTOE\n')
            else:
                # send anything else to gui
                client_queue.put_nowait(
                    {'status': 'ok', 'data': chunk})
        await asyncio.sleep(0.001)

        # check if the gui was closed
        if not gui_queue.empty():
            gui_message = gui_queue.get_nowait()
            # check if a closed event happened
            if gui_message == 'closed':
                break
            # not a close, so send whatever the action is
            pending_writes.put_nowait(gui_message)

        if write_done and not pending_writes.empty():
            # schedule a new write
            data = bytes(pending_writes.get_nowait(), 'utf-8')
            writer.write(data)
            write_task = asyncio.create_task(writer.drain())
            write_done = False
        elif write_task:
            write_done = write_task.done()

    # cancel pending tasks
    pending_tasks = []
    if read_task:
        read_task.cancel()
        pending_tasks.append(read_task)
    if write_task:
        write_task.cancel()
        pending_tasks.append(write_task)
    # wait until cancelled
    await asyncio.wait(pending_tasks)

    writer.close()
    await writer.wait_closed()
