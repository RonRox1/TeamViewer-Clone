#FunctionsModule.py
from PIL import ImageGrab
from io import BytesIO
from pynput import mouse, keyboard


# Maximum chunk size for socket receiving to avoid too large reads at once
MAX_CHUNK_SIZE = 4096

# Mapping string mouse button IDs to pynput mouse.Button enums
MOUSE_BUTTON_MAP = {
    "1": mouse.Button.left,
    "2": mouse.Button.middle,
    "3": mouse.Button.right
}

# Mapping string key names to pynput keyboard.Key special keys or characters
KEYBOARD_SPECIAL_KEYS_MAP = {
    'Shift_L': keyboard.Key.shift,
    'Shift_R': keyboard.Key.shift_r,
    'Control_L': keyboard.Key.ctrl,
    'Control_R': keyboard.Key.ctrl_r,
    'Alt_L': keyboard.Key.alt,
    'Alt_R': keyboard.Key.alt_r,
    'BackSpace': keyboard.Key.backspace,
    'Tab': keyboard.Key.tab,
    'Return': keyboard.Key.enter,
    'Escape': keyboard.Key.esc,
    'space': keyboard.Key.space,
    'Left': keyboard.Key.left,
    'Right': keyboard.Key.right,
    'Up': keyboard.Key.up,
    'Down': keyboard.Key.down,
    'Delete': keyboard.Key.delete,
    'Caps_Lock': keyboard.Key.caps_lock,
    'Insert': keyboard.Key.insert,
    'Home': keyboard.Key.home,
    'End': keyboard.Key.end,
    'Page_Up': keyboard.Key.page_up,
    'Page_Down': keyboard.Key.page_down,
    'Num_Lock': keyboard.Key.num_lock,
    'Scroll_Lock': keyboard.Key.scroll_lock,
    'Pause': keyboard.Key.pause,
    'Print': keyboard.Key.print_screen,
    'Menu': keyboard.Key.menu,
    'F1': keyboard.Key.f1,
    'F2': keyboard.Key.f2,
    'F3': keyboard.Key.f3,
    'F4': keyboard.Key.f4,
    'F5': keyboard.Key.f5,
    'F6': keyboard.Key.f6,
    'F7': keyboard.Key.f7,
    'F8': keyboard.Key.f8,
    'F9': keyboard.Key.f9,
    'F10': keyboard.Key.f10,
    'F11': keyboard.Key.f11,
    'F12': keyboard.Key.f12,
    'period': '.',
    'comma': ',',
    'slash': '/',
    'backslash': '\\',
    'bracketleft': '[',
    'bracketright': ']',
    'semicolon': ';',
    'apostrophe': "'",
    'grave': '`',
    'minus': '-',
    'equal': '=',
    'plus': '+',
    'underscore': '_',
    'colon': ':',
    'quotedbl': '"',
    'bar': '|',
    'asciitilde': '~',
    'less': '<',
    'greater': '>',
    'question': '?',
    'exclam': '!',
    'at': '@',
    'numbersign': '#',
    'dollar': '$',
    'percent': '%',
    'asciicircum': '^',
    'ampersand': '&',
    'asterisk': '*',
    'parenleft': '(',
    'parenright': ')',
}


class UserBlocker:
    """
    Class to block all user input (keyboard and mouse) by suppressing events.
    """

    def __init__(self):
        """
        Initialize UserBlocker with no active listeners.
        """
        self.keyboard_listener = None
        self.mouse_listener = None

    def start_blocking(self):
        """
        Start blocking user input by suppressing keyboard and mouse events.
        This creates and starts listeners that prevent any input from reaching other apps.
        """
        if not self.keyboard_listener or not self.mouse_listener:
            # Suppress=True means events are blocked/suppressed system-wide
            self.keyboard_listener = keyboard.Listener(suppress=True)
            self.mouse_listener = mouse.Listener(suppress=True)
            self.keyboard_listener.start()
            self.mouse_listener.start()

    def stop_blocking(self):
        """
        Stop blocking user input by stopping the keyboard and mouse listeners.
        """
        if self.keyboard_listener and self.keyboard_listener.running:
            self.keyboard_listener.stop()
        if self.mouse_listener and self.mouse_listener.running:
            self.mouse_listener.stop()
        self.keyboard_listener = None
        self.mouse_listener = None


class InputController:
    """
    Handles injecting mouse and keyboard inputs programmatically.
    """

    def __init__(self, block_event, block_event_lock, user_blocker):
        """
        Initialize the input controller.

        :param block_event: threading.Event used to track if input blocking is active.
        :param block_event_lock: threading.Lock protecting access to block_event.
        :param user_blocker: Instance of UserBlocker to start/stop blocking when needed.
        """
        self.block_event = block_event
        self.block_event_lock = block_event_lock
        self.user_blocker = user_blocker
        self.mouse = mouse.Controller()
        self.keyboard = keyboard.Controller()

    def set_mouse_pos(self, x_pos, y_pos):
        """
        Set the mouse cursor position on screen.

        :param x_pos: X coordinate.
        :param y_pos: Y coordinate.
        """
        self.mouse.position = (x_pos, y_pos)

    def handle_command(self, command):
        """
        Handle an input command string and execute mouse or keyboard actions.

        :param command: Command string, e.g. "button:1:100:200", "key_down:Shift_L".
        """
        try:
            with self.block_event_lock:
                was_blocking = self.block_event.is_set()
                if was_blocking:
                    # Temporarily stop blocking so injected inputs are accepted by the system
                    self.user_blocker.stop_blocking()

                sliced_command = command.split(":")
                if sliced_command[0] == "button":
                    # Mouse button click command: button:<button_num>:<x>:<y>
                    button_num = sliced_command[1]
                    x = int(sliced_command[2])
                    y = int(sliced_command[3])
                    button = MOUSE_BUTTON_MAP.get(button_num)
                    if button:
                        self.set_mouse_pos(x, y)
                        self.mouse.click(button)
                    else:
                        print(f"[InputController] Unknown mouse button: {button_num}")

                elif sliced_command[0] == "key_down":
                    # Key press command
                    self._press_key(sliced_command[1])

                elif sliced_command[0] == "key_up":
                    # Key release command
                    self._release_key(sliced_command[1])

                if was_blocking:
                    # Restart blocking after input injection to continue suppressing real user input
                    self.user_blocker.start_blocking()

        except Exception as e:
            print(f"[InputController] Error handling command '{command}': {e}")

    def _press_key(self, key):
        """
        Press a keyboard key.

        :param key: String key name to press.
        """
        if key in KEYBOARD_SPECIAL_KEYS_MAP:
            pynput_key = KEYBOARD_SPECIAL_KEYS_MAP[key]
            self.keyboard.press(pynput_key)
        else:
            try:
                self.keyboard.press(key)
            except ValueError:
                print(f"[InputController] Invalid key press: {key}")

    def _release_key(self, key):
        """
        Release a keyboard key.

        :param key: String key name to release.
        """
        if key in KEYBOARD_SPECIAL_KEYS_MAP:
            pynput_key = KEYBOARD_SPECIAL_KEYS_MAP[key]
            self.keyboard.release(pynput_key)
        else:
            try:
                self.keyboard.release(key)
            except ValueError:
                print(f"[InputController] Invalid key release: {key}")


def take_screenshot(x_size=1920, y_size=1080, quality=75):
    """
    Capture a screenshot of the screen resized to given dimensions and compressed as JPEG.

    :param x_size: Width of the resized screenshot.
    :param y_size: Height of the resized screenshot.
    :param quality: JPEG quality (0-100).
    :return: JPEG image bytes.
    """
    # Capture the entire screen
    screenshot = ImageGrab.grab()

    # Resize screenshot to target resolution
    screenshot = screenshot.resize((x_size, y_size))

    # Save screenshot to in-memory byte stream in JPEG format with specified quality
    byte_io = BytesIO()
    screenshot.save(byte_io, format='JPEG', quality=quality)
    byte_io.seek(0)

    # Return the raw bytes of the JPEG image
    return byte_io.getvalue()


def recv_all(sock, num_bytes):
    """
    Receive an exact number of bytes from a socket, handling partial receives.

    :param sock: Socket object to receive from.
    :param num_bytes: Number of bytes to receive.
    :return: Received bytes.
    :raises ConnectionError: If the connection is lost before all bytes are received.
    """
    data = b''
    while len(data) < num_bytes:
        # Receive the remaining number of bytes or MAX_CHUNK_SIZE, whichever is smaller
        packet = sock.recv(min(MAX_CHUNK_SIZE, num_bytes - len(data)))
        if not packet:
            # Connection lost unexpectedly
            raise ConnectionError("Connection lost while receiving data")
        data += packet
    return data
