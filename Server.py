"""
╔══════════════════════════════════════════════════════╗
║   PyChat Server  —  with Private Messaging           ║
║   Supports: PRIVATE:<to>:<msg>  and  BROADCAST:<msg> ║
╚══════════════════════════════════════════════════════╝
"""

import socket
import threading
from datetime import datetime


# ── Protocol constants ────────────────────────────────────────────────────────
PREFIX_PRIVATE   = "PRIVATE"
PREFIX_BROADCAST = "BROADCAST"
SEP              = ":"         


# ──────────────────────────────────────────────────────────────────────────────

class ClientHandler:
    """
    Manages a single connected client in its own daemon thread.

    Wire protocol (client → server)
    ─────────────────────────────────────────────────────
    First line sent after connect:
        <username>\\n                    — registration

    Subsequent lines:
        PRIVATE:<receiver>:<message>\\n  — private message
        BROADCAST:<message>\\n           — broadcast to all others
        /users\\n                        — list online users
        /quit\\n                         — clean disconnect

    Wire protocol (server → client)
    ─────────────────────────────────────────────────────
        [HH:MM:SS] [PRIVATE from <sender>] <message>
        [HH:MM:SS] <sender>: <message>          <- broadcast
        [SERVER] <status text>                  <- system notices
        [ERROR]  <error text>                   <- error responses
    """

    def __init__(self, conn: socket.socket, addr: tuple, server: "ChatServer"):
        self.conn     = conn
        self.addr     = addr
        self.server   = server
        self.username: str | None = None
        self._thread  = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def send(self, message: str):
        """Deliver a newline-terminated message to this client."""
        try:
            self.conn.sendall((message + "\n").encode("utf-8"))
        except OSError:
            pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self):
        try:
            self._register()
            if self.username:
                self._message_loop()
        except (OSError, ConnectionResetError):
            pass
        finally:
            self._cleanup()

    def _register(self):
        """
        Step 1: collect a unique username from the new client.
        The server sends a prompt; the client's very first line is the name.
        """
        self.send("[SERVER] Welcome to PyChat! Send your username to continue.")

        while True:
            raw = self.conn.recv(256)
            if not raw:
                return
            name = raw.decode("utf-8").strip()
            if not name:
                self.send("[ERROR] Username cannot be empty. Try again.")
                continue
            if self.server.is_username_taken(name):
                self.send(f"[ERROR] Username '{name}' is already taken. Try another.")
                continue
            # Success — register with the server
            self.username = name
            self.server.register(self)
            self.send(f"[SERVER] Registered as '{name}'. You can now chat!")
            self.server.broadcast_system(
                f"{name} joined the chat.", exclude=self
            )
            print(f"[{self._now()}] + {name} connected from {self.addr}")
            return

    def _message_loop(self):
        """Step 2: relay messages until the client disconnects."""
        while True:
            data = self.conn.recv(4096)
            if not data:
                break

            line = data.decode("utf-8").strip()
            if not line:
                continue

            if line == "/quit":
                break
            elif line == "/users":
                self._handle_users()
            elif line.startswith(f"{PREFIX_PRIVATE}{SEP}"):
                self._handle_private(line)
            elif line.startswith(f"{PREFIX_BROADCAST}{SEP}"):
                self._handle_broadcast(line)
            else:
                # Treat any bare text as a broadcast (backwards compatibility)
                self._handle_broadcast(f"{PREFIX_BROADCAST}{SEP}{line}")

    def _handle_private(self, line: str):
        """
        Parse  PRIVATE:<receiver>:<message>
        and deliver to the named recipient only.
        """
        # Split into at most 3 parts so the message body may contain ':'
        parts = line.split(SEP, 2)
        if len(parts) < 3 or not parts[1].strip() or not parts[2].strip():
            self.send("[ERROR] Format: PRIVATE:<username>:<message>")
            return

        _, receiver_name, message = parts
        receiver_name = receiver_name.strip()
        message       = message.strip()

        if receiver_name == self.username:
            self.send("[ERROR] You cannot send a private message to yourself.")
            return

        target = self.server.find_client(receiver_name)
        if target is None:
            self.send(f"[ERROR] User '{receiver_name}' is not online.")
            return

        ts = self._now()
        target.send(f"[{ts}] [PRIVATE from {self.username}] {message}")
        self.send(f"[{ts}] [PRIVATE to {receiver_name}] {message}")
        print(f"[{ts}] PRIVATE {self.username} -> {receiver_name}: {message}")

    def _handle_broadcast(self, line: str):
        """
        Parse  BROADCAST:<message>
        and relay to all other connected clients.
        """
        parts = line.split(SEP, 1)
        if len(parts) < 2 or not parts[1].strip():
            self.send("[ERROR] Format: BROADCAST:<message>")
            return

        message = parts[1].strip()
        ts      = self._now()
        payload = f"[{ts}] {self.username}: {message}"
        self.server.broadcast(payload, exclude=self)
        self.send(payload)   # echo back so sender sees their own message
        print(f"[{ts}] BROADCAST {self.username}: {message}")

    def _handle_users(self):
        """Reply with a list of currently online usernames."""
        names = self.server.get_usernames()
        self.send("[SERVER] Online: " + ", ".join(names))

    def _cleanup(self):
        self.server.unregister(self)
        if self.username:
            self.server.broadcast_system(f"{self.username} left the chat.")
            print(f"[{self._now()}] - {self.username} disconnected.")
        try:
            self.conn.close()
        except OSError:
            pass

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%H:%M:%S")


# ──────────────────────────────────────────────────────────────────────────────

class ChatServer:
    """
    Accepts TCP connections and maintains the username -> ClientHandler map.

    All mutation of `_clients` is protected by `_lock` so concurrent
    handler threads never race on the shared registry.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 5555):
        self.host = host
        self.port = port
        self._clients: dict[str, ClientHandler] = {}   # {username: handler}
        self._lock    = threading.Lock()

    # ── Registry helpers ──────────────────────────────────────────────────────

    def register(self, handler: ClientHandler):
        with self._lock:
            self._clients[handler.username] = handler

    def unregister(self, handler: ClientHandler):
        with self._lock:
            if handler.username and self._clients.get(handler.username) is handler:
                del self._clients[handler.username]

    def is_username_taken(self, name: str) -> bool:
        with self._lock:
            return name in self._clients

    def find_client(self, username: str) -> ClientHandler | None:
        with self._lock:
            return self._clients.get(username)

    def get_usernames(self) -> list[str]:
        with self._lock:
            return sorted(self._clients.keys())

    # ── Broadcast helpers ─────────────────────────────────────────────────────

    def broadcast(self, message: str, exclude: ClientHandler | None = None):
        """Send to all clients except `exclude`."""
        with self._lock:
            targets = list(self._clients.values())
        for handler in targets:
            if handler is not exclude:
                handler.send(message)

    def broadcast_system(self, text: str, exclude: ClientHandler | None = None):
        ts = datetime.now().strftime("%H:%M:%S")
        self.broadcast(f"[{ts}] [SERVER] {text}", exclude=exclude)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen()
        print(f"[SERVER] Listening on {self.host}:{self.port}")
        print(f"[SERVER] Protocol: PRIVATE:<user>:<msg> | BROADCAST:<msg> | /users | /quit\n")

        try:
            while True:
                conn, addr = sock.accept()
                ClientHandler(conn, addr, server=self).start()
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down.")
        finally:
            sock.close()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ChatServer(host="0.0.0.0", port=5555).start()