#App.py
import tkinter as tk
from tkinter import ttk
import queue
import subprocess
import sys
import os
import socket
import ipaddress

from ClientThreads import Client
from Client_GUI import ClientGui
from ServerThreads import Server
from Server_GUI import ServerGui

# Define default IP addresses and port
DEFAULT_PORT = '12345'
DEFAULT_CLIENT_IP = '127.0.0.1'
DEFAULT_SERVER_IP = '0.0.0.0'


class StarterApp:
    """
    A GUI application that lets the user choose between Client or Server mode,
    enter configuration details (IP and Port), and launch the corresponding mode.
    """

    def __init__(self, root, reason=None):
        """
        Initialize the starter application GUI.

        :param root: The root tkinter window.
        :type root: tk.Tk
        :param reason: Reason for relaunching the app (e.g., disconnection).
        :type reason: str, optional
        """
        self.root = root
        self.root.title("Client/Server Launcher")
        self.root.geometry("640x360")
        self.root.configure(bg="#f0f0f0")
        self.root.resizable(False, False)

        self.reason = reason
        self.client_switch = None

        # GUI elements initialized as None
        self.client_button = None
        self.server_button = None
        self.input_frame = None
        self.start_button = None
        self.title_label = None
        self.button_frame = None
        self.ip_label = None
        self.ip_entry = None
        self.port_label = None
        self.port_entry = None
        self.info_label = None

        self.create_widgets()

    def create_widgets(self):
        """
        Create the initial GUI widgets for selecting client/server mode.
        """
        if self.reason:
            reason_label = ttk.Label(
                self.root,
                text=f"Previous session ended: {self.reason}",
                foreground="red",
                font=("Helvetica", 10)
            )
            reason_label.pack(pady=(10, 0))

        self.title_label = ttk.Label(self.root, text="Select Mode", font=("Helvetica", 18))
        self.title_label.pack(pady=30)

        self.button_frame = ttk.Frame(self.root)
        self.button_frame.pack()

        self.client_button = ttk.Button(self.button_frame, text="Client", command=self.client_mode)
        self.client_button.grid(row=0, column=0, padx=20, ipadx=20, ipady=10)

        self.server_button = ttk.Button(self.button_frame, text="Server", command=self.server_mode)
        self.server_button.grid(row=0, column=1, padx=20, ipadx=20, ipady=10)

        self.input_frame = ttk.Frame(self.root)
        self.start_button = ttk.Button(self.root, text="Start", command=self.start_pressed)

    def clear_initial_buttons(self):
        """
        Remove the initial mode selection buttons from the UI.
        """
        self.client_button.grid_forget()
        self.server_button.grid_forget()
        self.button_frame.pack_forget()
        self.title_label.pack_forget()

    def client_mode(self):
        """
        Configure the interface for client mode.
        """
        self.clear_initial_buttons()
        self.client_switch = True
        self.show_input_fields()

    def server_mode(self):
        """
        Configure the interface for server mode.
        """
        self.clear_initial_buttons()
        self.client_switch = False
        self.show_input_fields()

    def show_input_fields(self):
        """
        Show input fields for IP and Port based on selected mode.
        """
        self.input_frame.pack(pady=40)
        row = 0

        if self.client_switch:
            self.ip_label = ttk.Label(self.input_frame, text="IP Address:")
            self.ip_label.grid(row=row, column=0, sticky='e', padx=10, pady=5)
            self.ip_entry = ttk.Entry(self.input_frame, foreground="gray")
            self.ip_entry.grid(row=row, column=1, padx=10, pady=5)
            self.add_placeholder(self.ip_entry, DEFAULT_CLIENT_IP)
            row += 1

        self.port_label = ttk.Label(self.input_frame, text="Port:")
        self.port_label.grid(row=row, column=0, sticky='e', padx=10, pady=5)
        self.port_entry = ttk.Entry(self.input_frame, foreground="gray")
        self.port_entry.grid(row=row, column=1, padx=10, pady=5)
        self.add_placeholder(self.port_entry, DEFAULT_PORT)

        self.info_label = ttk.Label(self.input_frame, text="", foreground="red")
        self.info_label.grid(row=row + 1, column=0, columnspan=2, pady=10)
        self.info_label.grid_remove()

        self.start_button.pack(pady=20)

    def add_placeholder(self, entry, placeholder):
        """
        Add placeholder behavior to an entry field.

        :param entry: Entry widget.
        :type entry: tk.Entry
        :param placeholder: Placeholder text.
        :type placeholder: str
        """
        entry.insert(0, placeholder)
        entry.config(foreground="gray")

        def on_focus_in(event):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.config(foreground="black")

        def on_focus_out(event):
            if entry.get() == "":
                entry.insert(0, placeholder)
                entry.config(foreground="gray")

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    def is_valid_ip(self, ip):
        """
        Check if the provided IP address is valid.

        :param ip: IP address string.
        :type ip: str
        :return: True if valid, False otherwise.
        :rtype: bool
        """
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    def is_port_available(self, port):
        """
        Check if the given port is available on localhost.

        :param port: Port number.
        :type port: int
        :return: True if available, False if in use.
        :rtype: bool
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) != 0

    def can_connect_to_server(self, ip, port):
        """
        Check if a connection can be made to a server.

        :param ip: IP address.
        :type ip: str
        :param port: Port number.
        :type port: int
        :return: True if connection is possible, False otherwise.
        :rtype: bool
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            return sock.connect_ex((ip, port)) == 0

    def start_pressed(self):
        """
        Validate user input and launch the appropriate mode (client/server).
        """
        port_str = self.port_entry.get()
        ip_val = self.ip_entry.get() if self.ip_entry else DEFAULT_SERVER_IP

        try:
            port = int(port_str)
            if not (1024 <= port <= 65535):
                raise ValueError
        except ValueError:
            self.info_label.config(text="Port must be a number between 1024 and 65535.")
            self.info_label.grid()
            return

        if self.client_switch and not self.is_valid_ip(ip_val):
            self.info_label.config(text="Invalid IP address.")
            self.info_label.grid()
            return

        if self.client_switch:
            if not self.can_connect_to_server(ip_val, port):
                self.info_label.config(text="Cannot connect to server at given IP/Port.")
                self.info_label.grid()
                return
        else:
            if not self.is_port_available(port):
                self.info_label.config(text="Port is already in use. Server may already be running.")
                self.info_label.grid()
                return

        self.root.destroy()

        if self.client_switch:
            run_client_mode(ip_val, port)
        else:
            run_server_mode(ip_val, port)

    def run(self):
        """
        Run the main tkinter loop.
        """
        self.root.mainloop()


def run_client_mode(ip, port):
    """
    Start the client application.

    :param ip: IP address to connect to.
    :type ip: str
    :param port: Port to connect to.
    :type port: int
    """
    def relaunch(reason=None):
        print(f"[Run Client] Relaunching StarterApp due to: {reason}")
        subprocess.Popen([sys.executable, os.path.abspath(__file__), reason or "disconnected"])
        sys.exit(0)

    def on_disconnect(reason):
        print(f"[Run Client] Client disconnect reason: {reason}")
        try:
            root.after(0, root.destroy)
        except Exception as e:
            print("[Run Client] Error during root destruction:", e)
        relaunch(reason)

    root = tk.Tk()
    status_window = ClientGui(root, (ip, port))
    client = Client(ip, port, disconnect_callback=on_disconnect)
    client.start()

    try:
        status_window.run()
    finally:
        print("[Run Client] Stopping client")
        client.stop("disconnected from server")


def run_server_mode(ip, port):
    """
    Start the server application.

    :param ip: IP address to bind to.
    :type ip: str
    :param port: Port to bind to.
    :type port: int
    """
    def relaunch(reason=None):
        print(f"[Run Server] Relaunching StarterApp due to: {reason}")
        subprocess.Popen([sys.executable, os.path.abspath(__file__), reason or "session stopped"])
        os._exit(0)

    def on_server_close(reason):
        print(f"[Run Server] Server close reason: {reason}")
        try:
            root.after(0, root.destroy)
        except Exception as e:
            print("[Run Server] Error during root destruction:", e)
        relaunch(reason)

    root = tk.Tk()
    command_queue = queue.Queue()
    frame_queue = queue.Queue()

    app = ServerGui(port, root, command_queue, frame_queue)
    server = Server(ip, port, app, command_queue, frame_queue, close_callback=on_server_close)
    server.start()

    try:
        app.run()
    finally:
        print("[Run Server] Stopping server")
        app.shutdown_event.set()
        server.stop("session closed")
        server.join()


def main():
    """
    Entry point for the application. Launches the starter GUI.
    If a reason is passed as a command-line argument, show it.
    """
    reason = None
    if len(sys.argv) > 1:
        reason = sys.argv[1]
    root = tk.Tk()
    app = StarterApp(root, reason)
    app.run()

if __name__ == "__main__":
    main()
