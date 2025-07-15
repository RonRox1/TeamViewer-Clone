#ServerThreads.py
import threading
import Encryption
import socket
import queue
import zlib
import time
from FunctionsModule import recv_all  # Helper to receive fixed amount of bytes from socket

FPS = 10  # Frames per second for limiting frame handling rate


class Server(threading.Thread):
    """
    TCP Server for handling encrypted client connections, receiving image frames, and dispatching commands.

    :param ip: IP address to bind the server.
    :param port: Port number to listen on.
    :param app: Reference to the application object for GUI and state interactions.
    :param command_queue: Queue for sending commands to clients.
    :param frame_queue: Queue for handling incoming frames from clients.
    :param close_callback: Optional callback to be called when the server stops.
    """
    def __init__(self, ip, port, app, command_queue, frame_queue, close_callback=None):
        super().__init__()
        self.ip = ip
        self.port = port
        self.app = app
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # TCP socket

        self.close_callback = close_callback  # Optional callback when server closes

        # Generate RSA key pair for secure key exchange
        self.private_key, self.public_key = Encryption.generate_rsa_keys()
        # Generate AES symmetric key for encrypting communication after exchange
        self.aes_key = Encryption.generate_aes_key()

        self.rsa_keys = {}  # Store clients' RSA public keys after key exchange
        self.rsa_keys_lock = threading.Lock()  # Lock for thread-safe access to rsa_keys

        self.client_sockets_and_threads = {}  # Map client address -> (socket, handler thread)
        self.clients_lock = threading.Lock()  # Lock for thread-safe client dict access

        self.command_queue = command_queue  # Queue of commands to send to clients
        self.frame_queue = frame_queue  # Queue of received frames from clients

        self.pause_event = threading.Event()  # Used to pause/unpause clients
        self.condition = threading.Condition()  # Condition variable (not shown used here)
        self.stop_event = threading.Event()  # Signal to stop the server and threads

        # Thread that sends commands from the queue to clients
        self.command_sender = CommandConsumer(self.client_sockets_and_threads, self.clients_lock, self.command_queue,
                                              self.pause_event, self.app)
        # Thread that consumes frames from clients and updates the app UI
        self.frame_updater = FrameConsumer(self.app, self.frame_queue)

    def run(self):
        """
        Main server loop that listens for incoming connections, handles key exchange, and starts handler threads.
        """
        stop_reason = "session closed"  # Default stop reason
        try:
            # Bind and listen on given IP and port
            self.server.bind((self.ip, self.port))
            self.server.listen(100)  # Allow backlog of 100 connections
            print(f"[Server] TCP Server listening on port: {self.port}")

            # Start the command sender and frame updater threads
            self.command_sender.start()
            self.frame_updater.start()

            # Main loop to accept new clients and handle key exchange
            while not self.stop_event.is_set():
                client_socket, client_address = self.key_exchange()
                if client_socket:
                    print(f"[Server] Accepted connection from {client_address}")

                    # Notify client of UI button size for resizing input areas
                    button_width, button_height = self.app.button_size
                    self.command_queue.put((client_address, f"resize:{button_width}:{button_height}"))

                    # If paused, send pause command to the new client immediately
                    if self.pause_event.is_set():
                        try:
                            iv, encrypted_command = Encryption.encrypt_aes(self.aes_key, b"pause")
                            client_socket.send(len(encrypted_command).to_bytes(4, 'big'))
                            client_socket.send(iv)
                            client_socket.send(encrypted_command)
                            print("[Server] Pause sent to new client")
                        except Exception as e:
                            print(f"[Server] Failed to send pause to new client {client_address}: {e}")

                    # Create and start a client handler thread to receive frames from this client
                    handler = ClientHandler(client_socket, client_address, self.frame_queue, self.aes_key, self.app)
                    with self.clients_lock:
                        self.client_sockets_and_threads[client_address] = (client_socket, handler)
                    handler.start()

        except Exception as e:
            stop_reason = "server crashed"
            print(f"[Server] Unexpected exception: {e}")
        finally:
            self.stop(stop_reason)

    def stop(self, stop_reason):
        """
        Stops the server and all running threads and connections.

        :param stop_reason: A message indicating the reason for stopping the server.
        """
        # Signal all threads and connections to stop
        self.stop_event.set()

        # Close all client connections and stop their threads
        with self.clients_lock:
            for sock, handler in self.client_sockets_and_threads.values():
                handler.stop()
                sock.close()

        # Stop the command sender and frame updater threads
        self.command_sender.stop()
        self.frame_updater.stop()

        # Close the server socket
        self.server.close()

        # Call the optional close callback (e.g., for UI updates)
        if self.close_callback:
            self.close_callback(stop_reason)

    def key_exchange(self):
        """
        Performs RSA key exchange with a new client and sends the AES key.

        :returns: Tuple of (client_socket, client_address) if successful, else (None, None).
        """
        # Perform RSA key exchange with a newly connecting client
        if self.stop_event.is_set():
            return None, None

        try:
            client_socket, client_address = self.server.accept()

            if self.stop_event.is_set():
                client_socket.close()
                return None, None

            # Set short timeout for key exchange phase
            client_socket.settimeout(5)
            try:
                # Receive length and then client's public key bytes
                client_key_len = int.from_bytes(recv_all(client_socket, 4), 'big')
                client_key_bytes = recv_all(client_socket, client_key_len)
                # Deserialize client RSA public key
                client_key = Encryption.deserialize_public_key(client_key_bytes)
            except socket.timeout:
                client_socket.close()
                return None, None

            # Send server's public key to client
            server_key_bytes = Encryption.serialize_public_key(self.public_key)
            client_socket.send(len(server_key_bytes).to_bytes(4, 'big'))
            client_socket.send(server_key_bytes)

            # Encrypt AES key with client's RSA public key and send
            encrypted_aes_key = Encryption.rsa_encrypt(client_key, self.aes_key)
            client_socket.send(len(encrypted_aes_key).to_bytes(4, 'big'))
            client_socket.send(encrypted_aes_key)

            client_socket.settimeout(None)  # Remove timeout for normal operation

            # Save the client's public key for future reference
            with self.rsa_keys_lock:
                self.rsa_keys[client_address] = client_key

            # Allow the app to accept input/frames from this address
            self.app.allow_address(client_address)

            return client_socket, client_address
        except Exception as e:
            print(f"[Server] Key exchange error: {e}")
            return None, None


class ClientHandler(threading.Thread):
    """
    Handles receiving frames from an individual client over a secure channel.

    :param client_socket: The socket connected to the client.
    :param client_address: Tuple representing the client's IP and port.
    :param frame_queue: Queue where the received frames are placed.
    :param aes_key: AES key for decrypting received data.
    :param app: Reference to the application for state and UI updates.
    """
    def __init__(self, client_socket, client_address, frame_queue, aes_key, app):
        super().__init__()
        self.client_socket = client_socket
        self.client_address = client_address
        self.frame_queue = frame_queue
        self.aes_key = aes_key
        self.app = app
        self.stop_event = threading.Event()
        self.min_frame_interval = 1.0 / FPS  # Enforce max FPS
        self.last_frame_time = 0  # Timestamp of last received frame

    def run(self):
        """
        Main loop that receives encrypted and compressed image frames from the client,
        decrypts and decompresses them, and puts them in the frame queue.
        """
        try:
            while not self.stop_event.is_set():
                current_time = time.time()
                elapsed = current_time - self.last_frame_time

                # Sleep if frames are arriving too fast (enforce FPS limit)
                if elapsed < self.min_frame_interval:
                    time.sleep(self.min_frame_interval - elapsed)

                # Receive size of incoming frame (8 bytes)
                image_size = int.from_bytes(recv_all(self.client_socket, 8), byteorder='big')
                if image_size == 0:
                    raise ConnectionError("Received empty frame size")

                # Receive AES IV and encrypted image bytes
                iv = recv_all(self.client_socket, 16)
                encrypted_img = recv_all(self.client_socket, image_size)

                # Decrypt and decompress the frame image data
                frame = Encryption.decrypt_aes(self.aes_key, iv, encrypted_img)
                frame = zlib.decompress(frame)

                timestamp = time.time()
                # Put the frame into the shared queue with client address and timestamp
                self.frame_queue.put((self.client_address, frame, timestamp))
                self.last_frame_time = timestamp

        except Exception as e:
            print(f"[ClientHandler] {self.client_address} error: {e}")
            if not self.app.shutdown_event.is_set():
                try:
                    # Request app cleanup of this client from the GUI thread
                    self.app.root.after(0, lambda: self.app.cleanup(self.client_address))
                except RuntimeError as tk_err:
                    print(f"[ClientHandler] GUI already closed for {self.client_address}: {tk_err}")
        finally:
            try:
                self.client_socket.close()
            except OSError as e:
                print(f"[ClientHandler] Error closing socket for {self.client_address}: {e}")

    def stop(self):
        """
        Signals the thread to stop receiving frames.
        """
        # Signal to stop receiving frames and close the thread
        self.stop_event.set()


class FrameConsumer(threading.Thread):
    """
    Consumes image frames from the queue and updates the UI accordingly.

    :param app: Reference to the application for UI updates.
    :param frame_queue: Queue containing incoming frames from clients.
    """
    def __init__(self, app, frame_queue):
        super().__init__()
        self.app = app
        self.frame_queue = frame_queue
        self.max_frame_age = 0.5  # Discard frames older than 0.5 seconds
        self.stop_event = threading.Event()

    def run(self):
        """
        Main loop that consumes frames and triggers screen updates if frames are fresh.
        """
        while not self.stop_event.is_set():
            try:
                # Wait for a new frame from any client, timeout after 1 second
                client_address, frame, timestamp = self.frame_queue.get(timeout=1)
                # Only update screen if frame is fresh enough
                if time.time() - timestamp <= self.max_frame_age:
                    # Update screen only if no fullscreen widget or fullscreen client matches frame client
                    if not self.app.fullscreen_widget or self.app.fullscreen_address == client_address:
                        self.app.update_screen(client_address, frame)
                else:
                    print(f"[FrameConsumer] Dropped stale frame from {client_address}")
            except queue.Empty:
                continue  # No frame available, continue loop

    def stop(self):
        """
        Signals the frame consumer to stop processing frames.
        """
        # Signal to stop processing frames
        self.stop_event.set()


class CommandConsumer(threading.Thread):
    """
    Sends encrypted commands to one or more clients based on the queue input.

    :param clients_dict: Dictionary mapping client addresses to (socket, handler thread).
    :param clients_lock: Lock for thread-safe access to the client dictionary.
    :param command_queue: Queue containing commands to be sent.
    :param pause_event: Event signaling whether the system is paused.
    :param app: Reference to the application for callbacks and UI handling.
    """

    def __init__(self, clients_dict, clients_lock, command_queue, pause_event, app):
        super().__init__()
        self.app = app
        self.clients_dict = clients_dict  # Dictionary of client sockets and handlers
        self.clients_lock = clients_lock
        self.command_queue = command_queue  # Queue of commands to send to clients
        self.pause_event = pause_event
        self.stop_event = threading.Event()

    def run(self):
        """
        Main loop that listens for commands in the queue and dispatches them to appropriate clients.
        Supports pause, unpause, resize, and other custom commands.
        """
        while not self.stop_event.is_set():
            try:
                # Wait for next command, timeout after 1 second
                client_address, cmd = self.command_queue.get(timeout=1)
                print(f"[CommandConsumer] Command: {cmd}")

                if cmd in ("pause", "unpause"):
                    # Handle global pause/unpause commands
                    if cmd == "pause":
                        self.pause_event.set()
                    else:
                        self.pause_event.clear()

                    with self.clients_lock:
                        # Send pause/unpause command to all clients except sender
                        for addr, (sock, thread) in list(self.clients_dict.items()):
                            if addr != client_address:
                                try:
                                    iv, encrypted_cmd = Encryption.encrypt_aes(thread.aes_key, cmd.encode())
                                    sock.send(len(encrypted_cmd).to_bytes(4, 'big'))
                                    sock.send(iv)
                                    sock.send(encrypted_cmd)
                                except Exception as e:
                                    print(f"[CommandConsumer] Failed to send command to {addr}: {e}")
                                    thread.stop()
                                    del self.clients_dict[addr]
                                    self.app.root.after(0, lambda: self.app.cleanup(addr))
                    continue

                elif cmd.startswith("resize"):
                    # Handle resize commands either for a specific client or all
                    with self.clients_lock:
                        targets = []
                        if client_address is None:
                            # Broadcast to all clients
                            targets = list(self.clients_dict.items())
                        elif client_address in self.clients_dict:
                            # Send only to specified client
                            targets = [(client_address, self.clients_dict[client_address])]

                        for addr, (sock, thread) in targets:
                            try:
                                iv, encrypted_cmd = Encryption.encrypt_aes(thread.aes_key, cmd.encode())
                                sock.send(len(encrypted_cmd).to_bytes(4, 'big'))
                                sock.send(iv)
                                sock.send(encrypted_cmd)
                            except Exception as e:
                                print(f"[CommandConsumer] Failed to send resize to {addr}: {e}")
                                thread.stop()
                                del self.clients_dict[addr]
                                self.app.root.after(0, lambda: self.app.cleanup(addr))
                    continue

                else:
                    # Handle other commands directed at specific client
                    with self.clients_lock:
                        if client_address in self.clients_dict:
                            sock, thread = self.clients_dict[client_address]
                            aes_key = thread.aes_key
                            try:
                                iv, encrypted_cmd = Encryption.encrypt_aes(aes_key, cmd.encode())
                                sock.send(len(encrypted_cmd).to_bytes(4, 'big'))
                                sock.send(iv)
                                sock.send(encrypted_cmd)

                                # If the command is "kick", stop the client handler and remove client
                                if cmd == "kick":
                                    thread.stop()
                                    del self.clients_dict[client_address]

                            except Exception as e:
                                print(f"[CommandConsumer] Unexpected error with {client_address}: {e}")
                                thread.stop()
                                del self.clients_dict[client_address]
                                self.app.root.after(0, lambda: self.app.kick(client_address))
            except queue.Empty:
                continue  # No command available, continue loop

    def stop(self):
        """
        Signals the command consumer to stop processing commands.
        """
        # Signal to stop processing commands
        self.stop_event.set()