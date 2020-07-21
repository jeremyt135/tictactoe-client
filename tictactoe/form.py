from ipaddress import ip_address
import PySimpleGUI as sg


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
    sg.theme('DarkAmber')

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
