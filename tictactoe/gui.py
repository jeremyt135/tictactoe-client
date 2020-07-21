import PySimpleGUI as sg
import asyncio
import copy
import re


class _GameState:
    def __init__(self):
        self.token = ""
        self.is_turn = False
        self.game_is_over = False
        self.status_text = ""
        self.taken_cells: [(str, int)] = []


def _process_game_action(action: str, data: tuple, state: _GameState) -> _GameState:
    next_state = copy.deepcopy(state)
    if action == 'PLAYER':
        # received player token
        next_state.token = data[1]
        next_state.status_text = 'Game started'
    elif action == 'INVALID':
        # previous move was invalid
        next_state.status_text = 'Your move was invalid'
    elif action == 'TURN':
        # opponent took a turn
        _, op_token, row, col = data
        next_state.status_text = f'{op_token} moved in {row},{col}'
        next_state.taken_cells.append((op_token, int(row)*3 + int(col)))
    elif action == 'MOVE':
        # it's our turn
        next_state.is_turn = True
        next_state.status_text = "It's your turn"
    elif action == 'WINNER':
        # game is over
        next_state.game_is_over = True
        _, winner_token = data
        next_state.status_text = f"{'You' if winner_token == next_state.token else winner_token} won"

    return next_state


async def show_game_board(gui_queue: asyncio.Queue(), client_queue: asyncio.Queue) -> None:
    """
    Creates a window with the game GUI that runs until closed or the game finishes.
    """
    sg.theme('DarkAmber')

    EMPTY_CELL = '_'
    STATUS_KEY = 'STATUS'
    PLAYER_KEY = 'PLAYER'

    game_state = _GameState()
    game_state.status_text = 'Waiting for game to start...'

    player_label_text = 'You are player: '

    # create checkerboard layout, text showing player's token, and game status text
    layout = [
        [sg.Frame('', [[sg.Button(EMPTY_CELL, key=f'BUTTON_{r}_{c}')
                        for r in range(3)] for c in range(3)],
                  element_justification='center')],
        [sg.Text(player_label_text + '?', key=PLAYER_KEY)],
        [sg.Text('Waiting for game to start...',
                 key=STATUS_KEY)]
    ]
    window = sg.Window('Tic Tac Toe', layout, element_justification='center')

    # continue until window is closed or connection lost
    while True:
        event, _ = window.read(timeout=100)
        if event in (sg.WIN_CLOSED, 'Cancel'):
            await gui_queue.put('closed')
            break
        else:
            # check if button click, which means we're submitting a turn
            match = re.match(r'^BUTTON_(\d)_(\d)$', event)
            if match and game_state.token and game_state.is_turn and not game_state.game_is_over:
                game_state.is_turn = False
                # send move to network client
                row, col = (int(g) for g in match.groups())
                game_state.taken_cells.append((game_state.token, row*3 + col))
                await gui_queue.put(f'TURN {game_state.token} {row} {col}\n')
                # get the Button element, set it to show our token, and disable it
                # window[event].Update(text=token, disabled=True)
                # clear the "your turn" message
                game_state.status_text = "Opponent's turn"

        await asyncio.sleep(0.001)

        # check for data from network client
        if not client_queue.empty():
            message = await client_queue.get()
            if message['status'] == 'error':
                # got an error
                if not game_state.game_is_over:
                    # don't show error if game is over
                    sg.popup_ok('Error ' + message['data'], title='Error',
                                button_color=sg.DEFAULT_ERROR_BUTTON_COLOR)
                    break
            else:
                # got some kind of game status udpate
                data = message['data'].split(' ')
                action = data[0]

                game_state = _process_game_action(action, data, game_state)

        if game_state.token:
            window[PLAYER_KEY].update(player_label_text + game_state.token)

        window[STATUS_KEY].update(game_state.status_text)
        for cell in game_state.taken_cells:
            token, ind = cell
            row = int(ind / 3)
            col = ind % 3
            btn: sg.Button = window[f'BUTTON_{row}_{col}']
            if not btn.Disabled:
                btn.update(text=token, disabled=True)
        game_state.taken_cells = []

    window.close()
