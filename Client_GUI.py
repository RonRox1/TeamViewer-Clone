#Client_GUI.py
from tkinter import ttk


class ClientGui:
    """
    A simple GUI application using tkinter to display the status of a client
    sharing its screen with a server at a specific IP address and port.
    """

    def __init__(self, root, address):
        """
        Initialize the GUI.

        :param root: The main tkinter root window.
        :type root: tk.Tk
        :param address: A tuple containing IP address and port number.
        :type address: tuple
        """
        self.root = root
        self.address = address

        # Configure the main window appearance
        self.root.title("Client Status")
        self.root.configure(bg="#e6f2ff")
        self.root.resizable(False, False)

        # Create and pack a label that shows connection status
        self.label = ttk.Label(
            self.root,
            text=f"Sharing screen with: {self.address[0]} on port: {self.address[1]}",
            font=("Helvetica", 14),
            foreground="green"
        )
        self.label.pack(expand=True, pady=30)

        # Schedule a geometry update after 100 milliseconds
        self.root.after(100, self.update_geometry)

        # Set up window close protocol
        self.root.wm_protocol("WM_DELETE_WINDOW", self.on_close)

    def update_geometry(self):
        """
        Dynamically adjusts the window width based on the label size
        to ensure proper spacing and visibility.
        """
        self.root.update()
        label_width = self.label.winfo_width()
        print("Label width:", label_width)  # Debug print for label width
        self.root.geometry(f"{label_width + 20}x120")  # Adjust window size

    def on_close(self):
        """
        Handler for window close event.
        Currently does nothing—to block client closing window.
        """
        pass

    def run(self):
        """
        Start the main GUI loop.
        """
        self.root.mainloop()
