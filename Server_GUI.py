#Server_GUI.py
import tkinter as tk
from PIL import ImageTk, Image
from io import BytesIO
import math
import os
import queue
import threading
import time
import socket


# Directory where this script is located, used for loading assets reliably
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Names of buttons shown in fullscreen mode
FULLSCREEN_BUTTON_NAMES = ["control start", "block", "kick"]

# Aspect ratio for screen previews (width / height)
RATIO = 16 / 9

# Size of control buttons in fullscreen mode (width and height)
BUTTON_SIZE = 54

# Height reserved for taskbar or UI elements at bottom
TASKBAR_HEIGHT = 72

# Tooltip texts associated with each button name
TOOLTIPS = {
    "control start": "Take control of the screen",
    "control stop": "Stop control of the screen",
    "block": "Block the student screen",
    "unblock": "Unblock the student screen",
    "kick": "Kick the student",
    "exit": "Exit fullscreen mode"
}

# File paths for button icons
ICON_FILES = {
    "info": os.path.join(SCRIPT_DIR, "assets", "info_icon.png"),
    "control start": os.path.join(SCRIPT_DIR, "assets", "control_start_icon.png"),
    "control stop": os.path.join(SCRIPT_DIR, "assets", "control_stop_icon.png"),
    "block": os.path.join(SCRIPT_DIR, "assets", "block_icon.png"),
    "unblock": os.path.join(SCRIPT_DIR, "assets", "unblock_icon.png"),
    "kick": os.path.join(SCRIPT_DIR, "assets", "kick_icon.png"),
    "exit": os.path.join(SCRIPT_DIR, "assets", "exit_icon.png")
}


class ToolTip:
    """Tooltip class to show helper text when hovering over a widget."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.tooltip_instance = self  # allow external refresh/update

        # Bind events to show/hide tooltip on mouse enter/leave
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def update_text(self, new_text):
        """Update the tooltip text and hide it if currently shown."""
        self.text = new_text
        if self.tooltip:
            self.hide_tooltip()

    def show_tooltip(self, event=None):
        """Display the tooltip near the widget, centered above it."""
        if self.tooltip or not self.text:
            return  # Tooltip already shown or no text to display

        # Create a new top-level window for the tooltip
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.overrideredirect(True)  # Remove window decorations

        # Create a label with the tooltip text and style it
        label = tk.Label(self.tooltip, text=self.text, foreground="#FFFFFF", background="#232333",
                         relief="solid", borderwidth=1, font=("Arial", 10))
        label.pack()

        self.tooltip.update_idletasks()  # Make sure geometry is updated

        # Get the absolute position and size of the widget
        widget_x = self.widget.winfo_rootx()
        widget_y = self.widget.winfo_rooty()
        widget_width = self.widget.winfo_width()

        tooltip_width = self.tooltip.winfo_width()
        tooltip_height = self.tooltip.winfo_height()

        # Calculate tooltip position (centered horizontally above the widget)
        x = widget_x + (widget_width // 2) - (tooltip_width // 2)
        y = widget_y - tooltip_height - 5  # 5 pixels above widget

        self.tooltip.geometry(f"+{x}+{y}")
        self.tooltip.update()

    def hide_tooltip(self, event=None):
        """Destroy the tooltip window if it exists."""
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


class InfoButtonToolTip(ToolTip):
    """Special tooltip class for the info button, positioned differently."""

    def show_tooltip(self, event=None):
        """Display tooltip to the left and above the info button."""
        if self.tooltip or not self.text:
            return

        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.overrideredirect(True)

        label = tk.Label(self.tooltip, text=self.text, foreground="#FFFFFF", background="#232333",
                         relief="solid", borderwidth=1, font=("Arial", 10))
        label.pack()

        self.tooltip.update_idletasks()

        widget_x = self.widget.winfo_rootx()
        widget_y = self.widget.winfo_rooty()

        tooltip_width = self.tooltip.winfo_width()
        tooltip_height = self.tooltip.winfo_height()

        # Position tooltip to the left and above the info icon
        x = widget_x - tooltip_width
        y = widget_y - tooltip_height

        self.tooltip.geometry(f"+{x}+{y}")
        self.tooltip.update()


class ServerGui:
    """Main GUI class for teacher control app."""

    def __init__(self, port, root, command_queue, frame_queue):
        """
        Initialize the ServerGui instance.

        :param port: Port number the server listens on.
        :type port: int
        :param root: Tkinter root window.
        :type root: tkinter.Tk
        :param command_queue: Queue for sending commands to clients.
        :type command_queue: queue.Queue
        :param frame_queue: Queue for receiving frames/screenshots from clients.
        :type frame_queue: queue.Queue
        """

        def get_local_ip():
            """
            Get local IP address for display; fallback to error message if unavailable.

            :return: Local IP address or error message.
            :rtype: str
            """
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))  # Use Google's DNS server for IP discovery
                ip = s.getsockname()[0]
                s.close()
                return ip
            except Exception as e:
                return f"Error: {e}"

        self.ip = get_local_ip()
        self.port = port
        self.root = root
        self.command_queue = command_queue
        self.frame_queue = frame_queue

        # Maintain a set of kicked client addresses for blocking
        self.kicked_addresses = set()
        self.kicked_lock = threading.Lock()

        # Graceful shutdown management
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.shutdown_event = threading.Event()

        # Window setup
        self.root.title("Teacher Control App")
        self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}")
        self.root.configure(bg='#232333')

        # Screen dimensions and button sizing
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight() - TASKBAR_HEIGHT
        self.fullscreen_size = (
            math.floor(RATIO * (self.screen_height - BUTTON_SIZE)),
            self.screen_height - BUTTON_SIZE - 5
        )
        self.button_size = self.fullscreen_size

        # Track GUI elements and states
        self.buttons = {}
        self.images = []
        self.fullscreen_buttons = self.fullscreen_buttons_create()
        self.fullscreen_widget = None
        self.fullscreen_address = ''
        self.control_switch = False
        self.block_states = {}

        # Key handling and debouncing
        self.last_key_press_time = {}
        self.pressed_keys = set()
        self.pressed_keys_lock = threading.Lock()

        # Bind keyboard events
        self.root.bind("<KeyPress>", self.on_key_press)
        self.root.bind("<KeyRelease>", self.on_key_release)

        # Display when no clients are connected
        self.no_clients_label = None
        self.show_no_clients_message()

        # IP and port info label
        self.info_label = None
        self.add_info_button()

    def add_info_button(self):
        """
        Add an information icon to the bottom-right corner of the GUI,
        which displays the server's IP, port, and connected clients.
        """
        try:
            info_icon_image = Image.open(ICON_FILES["info"])
        except (FileNotFoundError, KeyError) as e:
            print("Error loading info icon:", e)
            return

        info_icon = ImageTk.PhotoImage(info_icon_image)
        self.info_label = tk.Label(self.root, image=info_icon, background="#232333")
        self.info_label.image = info_icon  # Prevent garbage collection

        x = self.screen_width - self.info_label.image.width() - 10
        y = self.screen_height - self.info_label.image.height() - 10
        self.info_label.place(x=x, y=y)

        info = self.get_info_text()
        self.info_label.tooltip = InfoButtonToolTip(self.info_label, info)

    def get_info_text(self):
        """
        Generate the tooltip text for the info icon.

        :return: Tooltip text with IP, port, and client count.
        :rtype: str
        """
        return f"IP: {self.ip}\nPort: {self.port}\nConnections: {len(self.buttons)}"

    def organize_screens(self):
        """
        Organize and place client screen buttons dynamically based on the number of clients
        and available screen space, avoiding overlap with the info icon.
        """
        total_buttons = len(self.buttons)
        print(f"[GUI] Organizing {total_buttons} screens")

        if total_buttons == 0:
            self.show_no_clients_message()
            return

        if self.no_clients_label:
            self.no_clients_label.destroy()
            self.no_clients_label = None

        for button in self.buttons.values():
            button.place_forget()

        # Determine available space
        usable_width = self.screen_width
        usable_height = self.screen_height
        margin = 20

        if self.info_label:
            info_x = self.info_label.winfo_x()
            info_y = self.info_label.winfo_y()
            info_width = self.info_label.winfo_width()
            info_height = self.info_label.winfo_height()

            if info_y + info_height + margin > self.screen_height - BUTTON_SIZE:
                usable_height = info_y - margin

            if info_x + info_width + margin > self.screen_width - BUTTON_SIZE:
                usable_width = info_x - margin

        # Layout computation
        num_buttons_per_row = math.ceil(math.sqrt(total_buttons))
        number_of_rows = math.ceil(total_buttons / num_buttons_per_row)
        num_buttons_in_last_row = total_buttons % num_buttons_per_row or num_buttons_per_row

        if num_buttons_per_row == number_of_rows:
            button_height = math.floor(usable_height / number_of_rows)
            button_width = math.floor(RATIO * button_height)
        else:
            button_width = math.floor(usable_width / num_buttons_per_row)
            button_height = math.floor(1 / RATIO * button_width)

        current_row = 0
        current_column = 0
        self.button_size = (button_width, button_height)

        for address, button in self.buttons.items():
            if current_row == number_of_rows - 1:
                row_buttons = num_buttons_in_last_row
            else:
                row_buttons = num_buttons_per_row

            x_offset = (self.screen_width - (button_width * row_buttons)) // 2
            y_offset = (usable_height - (button_height * number_of_rows)) // 2

            x_position = x_offset + (current_column * button_width)
            y_position = y_offset + (current_row * button_height)

            button.place(x=x_position, y=y_position, width=button_width, height=button_height)

            current_column += 1
            if current_column >= num_buttons_per_row:
                current_column = 0
                current_row += 1

    def show_no_clients_message(self):
        """
        Display a message in the center of the screen indicating that no clients are connected.
        """
        if not self.no_clients_label:
            self.no_clients_label = tk.Label(
                self.root,
                text="No Clients Connected",
                font=("Arial", 24),
                fg="white",
                bg="#232333"
            )
            self.no_clients_label.place(relx=0.5, rely=0.5, anchor="center")

    def _add_screen_on_main_thread(self, address, preview_photo):
        """
        Add a new client screen preview button to the GUI on the main thread.

        :param address: Client's network address.
        :type address: str
        :param preview_photo: Tkinter PhotoImage preview of the client's screen.
        :type preview_photo: ImageTk.PhotoImage
        """
        print(f"[GUI] Added a new screen")
        button = tk.Button(self.root, image=preview_photo, background="#232333",
                           command=lambda: self.toggle_fullscreen(address, b""))
        button.image = preview_photo
        button.image_id = id(preview_photo)  # Track image to avoid redundant updates
        self.buttons[address] = button
        self.images.append(preview_photo)  # Keep a reference to avoid garbage collection

        info = self.get_info_text()
        self.info_label.tooltip.update_text(info)  # Update tooltip info

        # Organize screens and notify clients of new resize if no fullscreen is active
        if not self.fullscreen_widget:
            self.organize_screens()
            self.command_queue.put((None, f"resize:{self.button_size[0]}:{self.button_size[1]}"))

    def update_screen(self, address, image_bytes):
        """
        Receive updated screen image bytes from a client and schedule GUI update.

        :param address: Client's network address.
        :type address: str
        :param image_bytes: Raw image data bytes of the client's screen.
        :type image_bytes: bytes
        """
        if self.shutdown_event.is_set():
            return  # Ignore updates if server is shutting down

        if address in self.kicked_addresses:
            print(f"[GUI] Ignoring frame update from kicked / disconnected client {address}")
            return

        print(f"[GUI] Updating image for {address}")
        try:
            image = Image.open(BytesIO(image_bytes))

            preview_photo = None
            fullscreen_photo = None

            if self.fullscreen_address == address:
                # Resize fullscreen image if needed
                if image.size != self.fullscreen_size:
                    fullscreen_image = image.resize(self.fullscreen_size)
                    self.command_queue.put((address, f"resize:{self.fullscreen_size[0]}:{self.fullscreen_size[1]}"))
                else:
                    fullscreen_image = image
                fullscreen_photo = ImageTk.PhotoImage(fullscreen_image)
            else:
                # Resize preview image if needed
                if image.size != self.button_size:
                    preview_image = image.resize(self.button_size)
                    self.command_queue.put((address, f"resize:{self.button_size[0]}:{self.button_size[1]}"))
                else:
                    preview_image = image
                preview_photo = ImageTk.PhotoImage(preview_image)

            # Schedule GUI update on the main thread
            self.root.after(0, lambda: self._update_screen_on_main_thread(address, preview_photo, fullscreen_photo))
        except Exception as e:
            print(f"[GUI] Error processing image from {address}: {e}")

    def _update_screen_on_main_thread(self, address, preview_photo, fullscreen_photo):
        """
        Update the GUI components for a client's screen on the main thread.

        :param address: Client's network address.
        :type address: str
        :param preview_photo: Tkinter PhotoImage for the preview button, or None.
        :type preview_photo: ImageTk.PhotoImage or None
        :param fullscreen_photo: Tkinter PhotoImage for fullscreen display, or None.
        :type fullscreen_photo: ImageTk.PhotoImage or None
        """
        if self.shutdown_event.is_set():
            return  # Prevent updates after shutdown

        if address in self.kicked_addresses:
            print(f"[GUI] Skipping update for kicked / disconnected client {address}")
            return

        if fullscreen_photo is not None:
            # Update fullscreen widget if active and address matches
            if self.fullscreen_widget is not None and self.fullscreen_address == address:
                if getattr(self.fullscreen_widget, "image_id", None) != id(fullscreen_photo):
                    self.fullscreen_widget.config(image=fullscreen_photo)
                    self.fullscreen_widget.image = fullscreen_photo
                    self.fullscreen_widget.image_id = id(fullscreen_photo)
            return  # No button update needed in fullscreen mode

        if preview_photo is not None:
            if address in self.buttons:
                button = self.buttons[address]

                if getattr(button, "image_id", None) != id(preview_photo):
                    button.config(image=preview_photo)
                    button.image = preview_photo
                    button.image_id = id(preview_photo)
            else:
                # Add new preview button if not found
                self._add_screen_on_main_thread(address, preview_photo)

    def toggle_fullscreen(self, address, image_bytes):
        """
        Toggle fullscreen preview mode for a selected client screen.

        :param address: Client's network address to display fullscreen.
        :type address: str
        :param image_bytes: Optional raw image data for fullscreen (used if no cached button image).
        :type image_bytes: bytes
        """
        self.fullscreen_address = address

        # Pause all other clients to focus on fullscreen client
        self.command_queue.put((self.fullscreen_address, "pause"))

        # Hide all preview buttons while in fullscreen
        for btn in self.buttons.values():
            btn.place_forget()

        # Attempt to use cached preview image, else load from bytes
        button = self.buttons.get(address)
        if button and hasattr(button, "image"):
            photo = button.image
        else:
            try:
                image = Image.open(BytesIO(image_bytes))
                photo = ImageTk.PhotoImage(image)
            except Exception as e:
                print(f"[GUI] Failed to load image for {address}: {e}")
                return

        # Create and display fullscreen widget centered on screen
        self.fullscreen_widget = tk.Button(self.root, image=photo, background="#232333")
        self.fullscreen_widget.image = photo
        self.fullscreen_widget.image_id = id(photo)
        self.fullscreen_widget.bind("<Button>", self.handle_mouse_click)
        self.fullscreen_widget.place(
            x=(self.screen_width - self.fullscreen_size[0]) // 2,
            y=0
        )

        self.fullscreen_buttons_show()  # Show fullscreen control buttons

        # Restore block/unblock state for this client
        is_blocked = self.block_states.get(address, False)
        self.update_block_button("unblock" if is_blocked else "block")

        # Reset control switch and update control button UI
        self.control_switch = False
        self.update_control_button("control start")

    def fullscreen_buttons_create(self):
        """
        Create fullscreen control buttons (pause, block, exit, etc.) centered below the fullscreen image.

        Buttons are initially disabled and hidden; stored in a dict by name.

        :return: Dictionary mapping button names to Tkinter Button objects.
        :rtype: dict[str, tk.Button]
        """
        buttons = {}
        total_buttons = len(FULLSCREEN_BUTTON_NAMES) + 1  # Extra one for "exit" button
        offset = (self.screen_width - total_buttons * BUTTON_SIZE) // 2  # Center buttons horizontally

        for i, name in enumerate(FULLSCREEN_BUTTON_NAMES + ["exit"]):
            x = offset + i * BUTTON_SIZE
            y = self.fullscreen_size[1] + 6  # Place just below fullscreen image

            # Map button name to method or exit_fullscreen
            command = self.exit_fullscreen if name == "exit" else getattr(self, name.replace(" ", "_"))

            # Load and resize icon image for button
            icon_image = Image.open(ICON_FILES[name]).resize((BUTTON_SIZE, BUTTON_SIZE))
            icon = ImageTk.PhotoImage(icon_image)

            # Create button, initially disabled and hidden
            button = tk.Button(self.root, image=icon, background="#232333", state=tk.DISABLED, command=command)
            button.image = icon  # Keep reference to prevent GC
            button.tooltip = ToolTip(button, TOOLTIPS[name])  # Attach tooltip

            button.place(x=x, y=y)
            # Save placement info for later show/hide
            button.place_info = {"x": x, "y": y, "width": BUTTON_SIZE, "height": BUTTON_SIZE}
            button.place_forget()  # Hide initially
            buttons[name] = button

        return buttons

    def fullscreen_buttons_show(self):
        """Show and enable all fullscreen control buttons."""
        for button in self.fullscreen_buttons.values():
            info = button.place_info
            button.place(**info)
            button.lift()  # Bring on top
            button.config(state=tk.NORMAL)

    def fullscreen_buttons_hide(self):
        """Hide and disable all fullscreen control buttons."""
        for button in self.fullscreen_buttons.values():
            button.place_forget()
            button.config(state=tk.DISABLED)

    def exit_fullscreen(self):
        """Exit fullscreen mode, restore buttons, and unpause the client."""
        if self.fullscreen_widget:
            self.fullscreen_widget.destroy()
            self.fullscreen_widget = None

        # Notify client to unpause
        self.command_queue.put((self.fullscreen_address, "unpause"))

        self.fullscreen_address = None  # Clear fullscreen state

        self.control_switch = False
        self.fullscreen_buttons_hide()
        self.organize_screens()  # Show previews again

    def handle_mouse_click(self, event):
        """
        Handle mouse click events on fullscreen widget by sending scaled coordinates to client.

        :param event: Tkinter mouse event.
        """
        if self.fullscreen_widget and self.fullscreen_address and self.control_switch:
            x, y = event.x, event.y
            # Scale click coordinates from fullscreen size to client's 1920x1080 resolution
            scaled_x = int(x * 1920 / self.fullscreen_size[0])
            scaled_y = int(y * 1080 / self.fullscreen_size[1])
            scaled_x = min(scaled_x, 1920)
            scaled_y = min(scaled_y, 1080)
            self.command_queue.put((self.fullscreen_address, f"button:{event.num}:{scaled_x}:{scaled_y}"))

    def on_key_press(self, event):
        """
        Handle key press events when controlling a fullscreen client.

        Implements debounce to prevent flooding, sends "key_down" commands.

        :param event: Tkinter keyboard event.
        """
        if self.fullscreen_widget and self.fullscreen_address and self.control_switch:
            key = event.keysym
            now = time.time()

            with self.pressed_keys_lock:
                last_time = self.last_key_press_time.get(key, 0)
                if now - last_time < 0.03:  # 30 ms debounce
                    return
                self.last_key_press_time[key] = now

                if key not in self.pressed_keys:
                    try:
                        self.command_queue.put_nowait((self.fullscreen_address, f"key_down:{key}"))
                        self.pressed_keys.add(key)
                    except queue.Full:
                        print(f"[KeyPress] Queue full, couldn't send key_down:{key}")

    def on_key_release(self, event):
        """
        Handle key release events when controlling a fullscreen client.

        Sends "key_up" commands and cleans up tracking.

        :param event: Tkinter keyboard event.
        """
        if self.fullscreen_widget and self.fullscreen_address and self.control_switch:
            key = event.keysym
            with self.pressed_keys_lock:
                if key in self.pressed_keys:
                    try:
                        self.command_queue.put_nowait((self.fullscreen_address, f"key_up:{key}"))
                    except queue.Full:
                        print(f"[KeyRelease] Queue full, couldn't send key_up:{key}")
                    self.pressed_keys.discard(key)
                    self.last_key_press_time.pop(key, None)

    def control_start(self):
        """Enable control mode for the fullscreen client."""
        if self.fullscreen_address:
            self.control_switch = True
            self.update_control_button("control stop")

    def control_stop(self):
        """Disable control mode for the fullscreen client."""
        if self.fullscreen_address:
            self.control_switch = False
            self.update_control_button("control start")

    def update_control_button(self, name):
        """
        Update the control button's icon and command.

        :param name: Button state name (e.g., "control start" or "control stop").
        """
        btn = self.fullscreen_buttons["control start"]
        new_icon = ImageTk.PhotoImage(Image.open(ICON_FILES[name]).resize((BUTTON_SIZE, BUTTON_SIZE)))
        btn.config(image=new_icon, command=getattr(self, name.replace(" ", "_")))
        btn.image = new_icon
        btn.tooltip.update_text(TOOLTIPS[name])

    def block(self):
        """
        Block input/control from the fullscreen client if not localhost.

        Updates button and internal block state.
        """
        if self.fullscreen_address and "127.0.0.1" not in self.fullscreen_address:
            self.command_queue.put((self.fullscreen_address, "block"))
            self.block_states[self.fullscreen_address] = True
            self.update_block_button("unblock")

    def unblock(self):
        """
        Unblock input/control from the fullscreen client.

        Updates button and internal block state.
        """
        if self.fullscreen_address:
            self.command_queue.put((self.fullscreen_address, "unblock"))
            self.block_states[self.fullscreen_address] = False
            self.update_block_button("block")

    def update_block_button(self, name):
        """
        Update the block/unblock button icon and command.

        :param name: Button state name ("block" or "unblock").
        """
        btn = self.fullscreen_buttons["block"]
        new_icon = ImageTk.PhotoImage(Image.open(ICON_FILES[name]).resize((BUTTON_SIZE, BUTTON_SIZE)))
        btn.config(image=new_icon, command=getattr(self, name))
        btn.image = new_icon
        btn.tooltip.update_text(TOOLTIPS[name])

    def kick(self, address=None):
        """
        Kick a client, disconnecting it and cleaning up resources.

        :param address: Optional address to kick; defaults to fullscreen client.
        """
        target = address or self.fullscreen_address
        if not target:
            print("[kick] No address to kick.")
            return

        self.command_queue.put((target, "kick"))

        with self.kicked_lock:
            self.kicked_addresses.add(target)

        self.cleanup(target)

    def cleanup(self, target):
        """
        Clean up resources related to a kicked or disconnected client.

        Removes buttons, block state, queued frames, and updates GUI.

        :param target: Client address to clean up.
        """
        if target in self.buttons:
            self.buttons[target].destroy()
            del self.buttons[target]

        if target in self.block_states:
            del self.block_states[target]

        info = self.get_info_text()
        self.info_label.tooltip.update_text(info)

        self.remove_frames_for_address(target)

        if self.fullscreen_address == target:
            self.exit_fullscreen()
        else:
            self.organize_screens()

    def on_close(self):
        """Handle application close event by signaling shutdown and destroying the GUI."""
        self.shutdown_event.set()  # Notify other threads
        self.root.after(0, self.root.destroy)  # Safely exit Tkinter main loop

    def allow_address(self, address):
        """Allow a previously kicked client address to reconnect."""
        with self.kicked_lock:
            if address in self.kicked_addresses:
                self.kicked_addresses.remove(address)

    def remove_frames_for_address(self, address):
        """
        Remove all queued frames associated with a specific client address.

        Prevents processing frames from kicked clients.

        :param address: Client address whose frames to remove.
        """
        temp_list = []

        # Drain queue, keep only frames not from the given address
        while not self.frame_queue.empty():
            try:
                item = self.frame_queue.get_nowait()
                if item[0] != address:
                    temp_list.append(item)
            except queue.Empty:
                break

        # Put valid frames back in the queue
        for item in temp_list:
            self.frame_queue.put(item)

    def run(self):
        """Start the Tkinter GUI event loop."""
        self.root.mainloop()