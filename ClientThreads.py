#ClientThreads.py
import socket
import Encryption
import threading
import time
import zlib

from FunctionsModule import InputController, UserBlocker, take_screenshot, recv_all

# Frames per second for screen sharing
FPS = 10


class Client(threading.Thread):
    """
    The Client class handles connection to a remote server, input commands, screen sharing,
    encryption key exchange, and user interaction blocking.
    """

    def __init__(self, address, port, disconnect_callback=None):
        """
        Initialize the Client thread and prepare for server connection.

        :param address: IP address of the server.
        :type address: str
        :param port: Port number of the server.
        :type port: int
        :param disconnect_callback: Callback executed on disconnection.
        :type disconnect_callback: callable, optional
        """
        super().__init__()
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.address = address
        self.port = port
        self.disconnect_callback = disconnect_callback
        self._disconnected = False
        self._lock = threading.Lock()

        # RSA encryption setup
        self.private_key, self.public_key = Encryption.generate_rsa_keys()
        self.server_rsa_key = None
        self.server_aes_key = None

        # Threading and control mechanisms
        self.pause_event = threading.Event()
        self.screen_share = None
        self.img_size = (1920, 1080)
        self.block_event = threading.Event()
        self.block_event_lock = threading.Lock()
        self.blocker = UserBlocker()
        self.input_controller = InputController(self.block_event, self.block_event_lock, self.blocker)
        self.stop_event = threading.Event()

    def run(self):
        """
        Run the client thread to connect to the server, handle commands,
        and manage screen sharing.
        """
        stop_reason = "client crashed"
        try:
            self.client.connect((self.address, self.port))
            print(f"[Client] Connected to server at {self.address}:{self.port}")
            self.key_exchange()

            self.screen_share = ScreenShare(self.client, self.server_aes_key, self.pause_event)
            self.screen_share.start()

            while not self.stop_event.is_set():
                try:
                    # Receive command length and actual command (AES encrypted)
                    cmd_len_bytes = recv_all(self.client, 4)
                    cmd_len = int.from_bytes(cmd_len_bytes, 'big')

                    iv = recv_all(self.client, 16)
                    encrypted_cmd = recv_all(self.client, cmd_len)
                    command = Encryption.decrypt_aes(self.server_aes_key, iv, encrypted_cmd).decode()

                    # Handle input-related commands
                    if command.startswith(("key_down", "key_up", "button")):
                        self.input_controller.handle_command(command)

                    # Handle resize command
                    elif command.startswith("resize"):
                        try:
                            _, width, height = command.split(":")
                            width, height = int(width), int(height)
                            print(f"[Client] Resizing to: {width}x{height}")
                            self.img_size = (width, height)
                            if self.screen_share:
                                self.screen_share.update_size(self.img_size)
                        except ValueError as e:
                            print(f"[Client] Invalid resize command: {command} ({e})")

                    # Handle session termination command
                    elif command == "kick":
                        stop_reason = "kicked from session"
                        print("[Client] Received kick command.")
                        break

                    # Block/unblock user input
                    if command == "block":
                        with self.block_event_lock:
                            self.block_event.set()
                        self.blocker.start_blocking()
                        print("Blocking: True")
                    elif command == "unblock":
                        with self.block_event_lock:
                            self.block_event.clear()
                        self.blocker.stop_blocking()
                        print("Blocking: False")

                    # Pause/unpause screen sharing
                    elif command == "pause":
                        self.pause_event.set()
                        print("Paused: True")
                    elif command == "unpause":
                        self.pause_event.clear()
                        print("Paused: False")

                except (ConnectionResetError, ConnectionError) as e:
                    print(f"[Client] Error: {e}")
                    stop_reason = "session closed"
                    break
                except Exception as e:
                    print(f"[Client] Error: {e}")
                    break

        finally:
            self.stop(stop_reason)

    def key_exchange(self):
        """
        Perform RSA public key exchange with the server and receive AES session key.
        """
        # Send our public key to the server
        pub_key_bytes = Encryption.serialize_public_key(self.public_key)
        self.client.send(len(pub_key_bytes).to_bytes(4, 'big'))
        self.client.send(pub_key_bytes)

        # Receive server's public key
        server_key_len = int.from_bytes(recv_all(self.client, 4), 'big')
        server_key_bytes = recv_all(self.client, server_key_len)
        self.server_rsa_key = Encryption.deserialize_public_key(server_key_bytes)

        # Receive AES session key encrypted with our public RSA key
        aes_key_len = int.from_bytes(recv_all(self.client, 4), 'big')
        encrypted_aes_key = recv_all(self.client, aes_key_len)
        self.server_aes_key = Encryption.rsa_decrypt(self.private_key, encrypted_aes_key)

    def stop(self, stop_reason):
        """
        Stop the client gracefully, terminate screen sharing, and clean up.

        :param stop_reason: Reason for stopping the client (used in callback).
        :type stop_reason: str
        """
        with self._lock:
            if self._disconnected:
                return
            self._disconnected = True

            self.stop_event.set()
            if self.screen_share:
                self.screen_share.stop()
            if self.blocker:
                self.blocker.stop_blocking()
            self.client.close()
            if self.disconnect_callback:
                self.disconnect_callback(stop_reason)


class ScreenShare(threading.Thread):
    """
    The ScreenShare class handles periodic screen capturing, compression,
    encryption, and transmission to the server.
    """

    def __init__(self, client, aes_key, pause_event):
        """
        Initialize the screen sharing thread.

        :param client: Socket used for sending screen data.
        :type client: socket.socket
        :param aes_key: AES key for encrypting screen data.
        :type aes_key: bytes
        :param pause_event: Event to pause/resume screen sharing.
        :type pause_event: threading.Event
        """
        super().__init__()
        self.client = client
        self.aes_key = aes_key
        self.img_size = (1920, 1080)
        self.stop_event = threading.Event()
        self.pause_event = pause_event
        self._lock = threading.Lock()

    def run(self):
        """
        Continuously capture, compress, encrypt, and send screen frames to the server.
        """
        while not self.stop_event.is_set():
            if self.pause_event.is_set():
                time.sleep(0.5)
                continue

            try:
                print("[Screen Share] Taking screenshot...")
                start = time.perf_counter()

                with self._lock:
                    width, height = self.img_size

                # Capture screen image
                image_bytes = take_screenshot(width, height, quality=75)
                if not image_bytes:
                    print("[Screen Share] Screenshot failed or returned empty")
                    time.sleep(0.5)
                    continue

                # Compress image data
                compressed_bytes = zlib.compress(image_bytes, level=6)
                if not compressed_bytes:
                    print("[Screen Share] Compression failed")
                    time.sleep(0.5)
                    continue

                # Encrypt the compressed data
                iv, encrypted = Encryption.encrypt_aes(self.aes_key, compressed_bytes)
                if not encrypted:
                    print("[Screen Share] Encryption failed")
                    time.sleep(0.5)
                    continue

                # Send data to server
                self.client.sendall(len(encrypted).to_bytes(8, 'big'))
                self.client.sendall(iv)
                self.client.sendall(encrypted)

                print(f"[Screen Share] Frame sent | raw={len(image_bytes)} | compressed={len(compressed_bytes)} | encrypted={len(encrypted)}")

                # Maintain frame rate
                elapsed = time.perf_counter() - start
                time.sleep(max(0, (1 / FPS) - elapsed))

            except Exception as e:
                print(f"[Screen Share] Error: {e}")
                time.sleep(1)

    def update_size(self, new_size):
        """
        Update the screen capture resolution.

        :param new_size: New resolution as (width, height).
        :type new_size: tuple
        """
        with self._lock:
            print(f"[Screen Share] Updating image size to: {new_size}")
            self.img_size = new_size

    def stop(self):
        """
        Stop the screen sharing thread.
        """
        self.stop_event.set()