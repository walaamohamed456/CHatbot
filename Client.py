"""
╔══════════════════════════════════════════════════════╗
║   PyChat GUI Client  —  Private Messaging Edition    ║
║   Technologies: Python, tkinter, socket, threading   ║
╚══════════════════════════════════════════════════════╝

Run:
    python client_gui.py
    python client_gui.py 192.168.1.10
    python client_gui.py 192.168.1.10 5555
"""

import socket
import threading
import sys
import tkinter as tk
from tkinter import scrolledtext, messagebox, font as tkfont
from datetime import datetime


# ── Palette ───────────────────────────────────────────────────────────────────
BG_DEEP     = "#0f1117"   
BG_PANEL    = "#16181f"   
BG_CHAT     = "#0f1117"   
BG_INPUT    = "#1c1f2a"   
BG_BUBBLE_O = "#1e2235"   
BG_BUBBLE_S = "#1a3a5c"   
BG_BUBBLE_P = "#2a1a3e"   
BG_BUBBLE_PS= "#1a2a3e"   
BG_HOVER    = "#1e2130"   
BG_SEL      = "#1f2d45"  
C_ACCENT    = "#4f8ef7"  
C_PRIVATE   = "#a78bfa"  
C_SUCCESS   = "#34d399"   
C_WARNING   = "#fbbf24"   
C_ERROR     = "#f87171"   
C_MUTED     = "#4a5068"   
C_TEXT      = "#d4d8f0"   
C_SUBTLE    = "#2a2f45"   
C_SELF_NAME = "#60a5fa"   
C_OTHER_NAME= "#a78bfa"   

FONT_BODY   = ("Consolas", 11)
FONT_BOLD   = ("Consolas", 11, "bold")
FONT_SMALL  = ("Consolas", 9)
FONT_TITLE  = ("Consolas", 13, "bold")
FONT_MONO   = ("Consolas", 10)


# ──────────────────────────────────────────────────────────────────────────────

class LoginDialog(tk.Toplevel):
    """
    Modal window: collect server host, port, and username.
    Sets self.result = (host, port, username) on success, or None on cancel.
    """

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title("PyChat — connect")
        self.configure(bg=BG_PANEL)
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._build()
        self._center(parent)
        self.protocol("WM_DELETE_WINDOW", parent.destroy)

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG_DEEP, pady=24)
        hdr.pack(fill="x")
        tk.Label(hdr, text="PYCHAT", font=("Consolas", 22, "bold"),
                 bg=BG_DEEP, fg=C_ACCENT).pack()
        tk.Label(hdr, text="private messaging client",
                 font=FONT_SMALL, bg=BG_DEEP, fg=C_MUTED).pack(pady=(2, 0))

        # Separator
        tk.Frame(self, bg=C_SUBTLE, height=1).pack(fill="x")

        form = tk.Frame(self, bg=BG_PANEL, padx=28)
        form.pack(fill="x", pady=16)

        self._vars = {}
        fields = [
            ("HOST",     "127.0.0.1", "server address"),
            ("PORT",     "5555",      "tcp port"),
            ("USERNAME", "",          "your display name"),
        ]
        for key, default, hint in fields:
            tk.Label(form, text=key, font=FONT_SMALL,
                     bg=BG_PANEL, fg=C_MUTED, anchor="w").pack(fill="x", pady=(10, 2))
            var = tk.StringVar(value=default)
            self._vars[key] = var
            frm = tk.Frame(form, bg=C_SUBTLE, padx=1, pady=1)
            frm.pack(fill="x")
            e = tk.Entry(frm, textvariable=var, font=FONT_MONO,
                         bg=BG_INPUT, fg=C_TEXT,
                         insertbackground=C_ACCENT,
                         relief="flat", bd=0)
            e.pack(fill="x", ipady=8, padx=1, pady=1)
            if key == "USERNAME":
                e.focus_set()

        tk.Frame(form, bg=C_SUBTLE, height=1).pack(fill="x", pady=(16, 0))

        btn = tk.Button(form, text="CONNECT  →",
                        font=FONT_BOLD,
                        bg=C_ACCENT, fg="#ffffff",
                        activebackground="#3a7de8",
                        activeforeground="#ffffff",
                        relief="flat", bd=0, cursor="hand2",
                        command=self._submit)
        btn.pack(fill="x", pady=(12, 4), ipady=10)
        self.bind("<Return>", lambda _: self._submit())

    def _submit(self):
        host     = self._vars["HOST"].get().strip()
        port_str = self._vars["PORT"].get().strip()
        username = self._vars["USERNAME"].get().strip()

        if not username:
            messagebox.showwarning("Missing username", "Enter a display name.", parent=self)
            return
        try:
            port = int(port_str)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid port", "Port must be 1–65535.", parent=self)
            return

        self.result = (host, port, username)
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        w  = self.winfo_width()
        h  = self.winfo_height()
        self.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")


# ──────────────────────────────────────────────────────────────────────────────

class ChatApp(tk.Tk):
    """
    Main application window.

    Layout
    ──────
    ┌─────────┬────────────────────────────┐
    │ Sidebar │  Header (channel / DM name)│
    │  - #general            ├────────────────────────────┤
    │  - DMs                 │  Message area (scrolled)   │
    │    Ali                 ├────────────────────────────┤
    │    Sara                │  Input bar                 │
    └─────────┴────────────────────────────┘
    """

    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("PyChat")
        self.configure(bg=BG_DEEP)
        self.minsize(640, 520)
        self.geometry("860x620")

        self._sock: socket.socket | None = None
        self._net:  "NetworkLayer | None" = None
        self._username = ""

        # State: current conversation context
        # None  → #general broadcast
        # "Ali" → DM to Ali
        self._dm_target: str | None = None
        self._online_users: list[str] = []

        # ── Login ──────────────────────────────────────────────────────────
        dlg = LoginDialog(self)
        self.wait_window(dlg)
        if not dlg.result:
            return

        host, port, self._username = dlg.result

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.connect((host, port))
        except (ConnectionRefusedError, OSError) as exc:
            messagebox.showerror("Connection failed",
                                 f"Could not reach {host}:{port}\n\n{exc}")
            self.destroy()
            return

        self._build_ui()
        self.deiconify()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._net = NetworkLayer(
            sock      = self._sock,
            username  = self._username,
            on_line   = lambda line: self.after(0, self._on_server_line, line),
            on_disconnect = lambda: self.after(0, self._on_disconnected),
        )
        self._net.start()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Sidebar ────────────────────────────────────────────────────────
        self._sidebar = tk.Frame(self, bg=BG_PANEL, width=210)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        # Logo
        logo_row = tk.Frame(self._sidebar, bg=BG_DEEP)
        logo_row.pack(fill="x")
        tk.Label(logo_row, text="PYCHAT",
                 font=("Consolas", 14, "bold"),
                 bg=BG_DEEP, fg=C_ACCENT,
                 padx=14, pady=14).pack(side="left")

        # User row
        user_row = tk.Frame(self._sidebar, bg=BG_PANEL)
        user_row.pack(fill="x", padx=10, pady=6)
        initials = self._username[:2].upper()
        tk.Label(user_row, text=initials,
                 font=("Consolas", 11, "bold"),
                 bg=C_ACCENT, fg="white",
                 width=3, padx=2, pady=3).pack(side="left")
        tk.Label(user_row, text=self._username,
                 font=FONT_BOLD, bg=BG_PANEL,
                 fg=C_TEXT, anchor="w").pack(side="left", padx=6)

        self._status_dot = tk.Label(user_row, text="●",
                                     font=("Consolas", 9),
                                     bg=BG_PANEL, fg=C_SUCCESS)
        self._status_dot.pack(side="right", padx=4)

        tk.Frame(self._sidebar, bg=C_SUBTLE, height=1).pack(fill="x", padx=8, pady=4)

        # Broadcast channel button
        self._general_btn = self._make_channel_btn("# general", self._open_general)
        self._general_btn.configure(bg=BG_SEL)   # selected by default

        tk.Frame(self._sidebar, bg=C_SUBTLE, height=1).pack(fill="x", padx=8, pady=4)

        # DM section header
        dm_hdr = tk.Frame(self._sidebar, bg=BG_PANEL)
        dm_hdr.pack(fill="x", padx=8)
        tk.Label(dm_hdr, text="DIRECT MESSAGES",
                 font=("Consolas", 8), bg=BG_PANEL,
                 fg=C_MUTED, anchor="w").pack(side="left")
        refresh_btn = tk.Button(dm_hdr, text="↺",
                                font=("Consolas", 10),
                                bg=BG_PANEL, fg=C_MUTED,
                                activebackground=BG_HOVER,
                                relief="flat", bd=0, cursor="hand2",
                                command=self._request_users)
        refresh_btn.pack(side="right")

        # Scrollable DM list
        dm_frame = tk.Frame(self._sidebar, bg=BG_PANEL)
        dm_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self._dm_list_frame = tk.Frame(dm_frame, bg=BG_PANEL)
        self._dm_list_frame.pack(fill="x")

        # Commands hint at bottom
        tk.Frame(self._sidebar, bg=C_SUBTLE, height=1).pack(fill="x", padx=8, pady=4)
        hint = tk.Frame(self._sidebar, bg=BG_PANEL)
        hint.pack(fill="x", padx=10, pady=6)
        for label, cmd in [("private msg",  "PRIVATE:<user>:<msg>"),
                            ("broadcast",    "BROADCAST:<msg>"),
                            ("list users",   "/users"),
                            ("quit",         "/quit")]:
            row = tk.Frame(hint, bg=BG_PANEL)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{label}:", font=FONT_SMALL,
                     bg=BG_PANEL, fg=C_MUTED, width=11, anchor="w").pack(side="left")
            tk.Label(row, text=cmd, font=("Consolas", 8),
                     bg=BG_PANEL, fg=C_ACCENT, anchor="w").pack(side="left")

        # ── Main area ──────────────────────────────────────────────────────
        main = tk.Frame(self, bg=BG_CHAT)
        main.pack(side="left", fill="both", expand=True)

        # Header bar
        self._header_frame = tk.Frame(main, bg=BG_PANEL, height=46)
        self._header_frame.pack(fill="x")
        self._header_frame.pack_propagate(False)
        self._header_label = tk.Label(
            self._header_frame,
            text="# general  —  broadcast channel",
            font=FONT_BOLD, bg=BG_PANEL,
            fg=C_TEXT, anchor="w", padx=16)
        self._header_label.pack(side="left", fill="y")

        # Notification badge (top right of header)
        self._notif_label = tk.Label(
            self._header_frame, text="",
            font=FONT_SMALL, bg=BG_PANEL, fg=C_WARNING, padx=12)
        self._notif_label.pack(side="right", fill="y")

        tk.Frame(main, bg=C_SUBTLE, height=1).pack(fill="x")

        # Scrollable chat area
        self._chat = scrolledtext.ScrolledText(
            main,
            state="disabled",
            wrap="word",
            font=FONT_BODY,
            bg=BG_CHAT, fg=C_TEXT,
            bd=0, relief="flat",
            padx=16, pady=10,
            cursor="arrow",
            insertbackground=C_ACCENT,
            selectbackground=C_SUBTLE,
        )
        self._chat.pack(fill="both", expand=True)
        self._chat.vbar.configure(
            bg=BG_PANEL, troughcolor=BG_CHAT,
            activebackground=C_ACCENT, width=5
        )

        # ── Text tags ──────────────────────────────────────────────────────
        self._chat.tag_configure("self_name",  font=FONT_BOLD, foreground=C_SELF_NAME)
        self._chat.tag_configure("other_name", font=FONT_BOLD, foreground=C_OTHER_NAME)
        self._chat.tag_configure("priv_name",  font=FONT_BOLD, foreground=C_PRIVATE)
        self._chat.tag_configure("timestamp",  font=FONT_SMALL, foreground=C_MUTED)
        self._chat.tag_configure("msg_self",
            font=FONT_BODY, foreground=C_TEXT,
            background=BG_BUBBLE_S,
            lmargin1=14, lmargin2=14, rmargin=120,
            spacing1=3, spacing3=3)
        self._chat.tag_configure("msg_other",
            font=FONT_BODY, foreground=C_TEXT,
            background=BG_BUBBLE_O,
            lmargin1=14, lmargin2=14, rmargin=120,
            spacing1=3, spacing3=3)
        self._chat.tag_configure("msg_priv_recv",
            font=FONT_BODY, foreground="#c4b5fd",
            background=BG_BUBBLE_P,
            lmargin1=14, lmargin2=14, rmargin=120,
            spacing1=3, spacing3=3)
        self._chat.tag_configure("msg_priv_sent",
            font=FONT_BODY, foreground="#93c5fd",
            background=BG_BUBBLE_PS,
            lmargin1=14, lmargin2=14, rmargin=120,
            spacing1=3, spacing3=3)
        self._chat.tag_configure("system",
            font=FONT_SMALL, foreground=C_MUTED,
            justify="center", spacing1=2, spacing3=2)
        self._chat.tag_configure("error",
            font=FONT_SMALL, foreground=C_ERROR,
            justify="center", spacing1=2, spacing3=2)
        self._chat.tag_configure("warning",
            font=FONT_SMALL, foreground=C_WARNING,
            justify="center", spacing1=2, spacing3=2)

        # ── Input bar ──────────────────────────────────────────────────────
        tk.Frame(main, bg=C_SUBTLE, height=1).pack(fill="x")
        input_bar = tk.Frame(main, bg=BG_PANEL, pady=10)
        input_bar.pack(fill="x")

        # Mode pill (shows "# general" or "→ Ali")
        self._mode_label = tk.Label(
            input_bar,
            text="# general",
            font=("Consolas", 9),
            bg=BG_INPUT, fg=C_ACCENT,
            padx=8, pady=0,
            relief="flat")
        self._mode_label.pack(side="left", padx=(12, 4), ipady=5)

        input_inner = tk.Frame(input_bar, bg=C_SUBTLE, padx=1, pady=1)
        input_inner.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self._entry = tk.Entry(
            input_inner,
            font=FONT_BODY,
            bg=BG_INPUT, fg=C_TEXT,
            insertbackground=C_ACCENT,
            relief="flat", bd=0,
        )
        self._entry.pack(fill="x", ipady=9, padx=2, pady=1)
        self._entry.bind("<Return>", lambda _: self._send())
        self._entry.bind("<FocusIn>",
            lambda _: input_inner.configure(bg=C_ACCENT))
        self._entry.bind("<FocusOut>",
            lambda _: input_inner.configure(bg=C_SUBTLE))
        self._entry.focus_set()

        send_btn = tk.Button(
            input_bar,
            text="SEND",
            font=FONT_BOLD,
            bg=C_ACCENT, fg="white",
            activebackground="#3a7de8",
            activeforeground="white",
            relief="flat", bd=0,
            cursor="hand2",
            padx=16,
            command=self._send,
        )
        send_btn.pack(side="right", padx=(0, 12), ipady=9)

    # ── Sidebar helpers ────────────────────────────────────────────────────

    def _make_channel_btn(self, label: str, cmd) -> tk.Button:
        btn = tk.Button(
            self._sidebar,
            text=label,
            font=FONT_BODY,
            bg=BG_PANEL, fg=C_TEXT,
            activebackground=BG_HOVER,
            activeforeground=C_TEXT,
            relief="flat", bd=0,
            cursor="hand2",
            anchor="w", padx=14,
            command=cmd,
        )
        btn.pack(fill="x", ipady=5)
        btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=BG_HOVER))
        btn.bind("<Leave>", lambda e, b=btn: b.configure(
            bg=BG_SEL if b == getattr(self, "_active_btn", None) else BG_PANEL))
        return btn

    def _open_general(self):
        self._dm_target = None
        self._update_channel_ui(None)

    def _open_dm(self, user: str):
        self._dm_target = user
        self._update_channel_ui(user)

    def _update_channel_ui(self, dm_user: str | None):
        # Update header
        if dm_user:
            self._header_label.configure(
                text=f"  {dm_user}  —  private conversation")
            self._mode_label.configure(text=f"→ {dm_user}")
        else:
            self._header_label.configure(
                text="# general  —  broadcast channel")
            self._mode_label.configure(text="# general")

        # Highlight correct sidebar button
        self._general_btn.configure(
            bg=BG_SEL if dm_user is None else BG_PANEL)
        for btn in getattr(self, "_dm_buttons", {}).values():
            btn.configure(bg=BG_PANEL)
        if dm_user and dm_user in getattr(self, "_dm_buttons", {}):
            self._dm_buttons[dm_user].configure(bg=BG_SEL)

    def _rebuild_dm_list(self, users: list[str]):
        """Rebuild the DM user list in the sidebar."""
        self._online_users = [u for u in users if u != self._username]

        for widget in self._dm_list_frame.winfo_children():
            widget.destroy()

        self._dm_buttons = {}
        for user in self._online_users:
            btn = self._make_channel_btn(
                f"  ● {user}",
                lambda u=user: self._open_dm(u)
            )
            btn.configure(font=FONT_SMALL, fg=C_SUCCESS)
            self._dm_buttons[user] = btn

        if not self._online_users:
            tk.Label(self._dm_list_frame,
                     text="  (no one online)",
                     font=FONT_SMALL, bg=BG_PANEL,
                     fg=C_MUTED).pack(anchor="w", padx=14, pady=3)

        # Re-apply selection highlight
        self._update_channel_ui(self._dm_target)

    # ── Sending ────────────────────────────────────────────────────────────

    def _send(self):
        text = self._entry.get().strip()
        if not text or not self._net:
            return
        self._entry.delete(0, "end")

        # Commands pass through raw
        if text in ("/quit", "/users"):
            self._net.send(text)
            if text == "/quit":
                self._on_close()
            return

        # If in a DM channel and text doesn't already start with PRIVATE:
        if self._dm_target and not text.startswith("PRIVATE:") \
                             and not text.startswith("BROADCAST:"):
            wire = f"PRIVATE:{self._dm_target}:{text}"
        elif text.startswith("PRIVATE:") or text.startswith("BROADCAST:"):
            wire = text
        else:
            wire = f"BROADCAST:{text}"

        self._net.send(wire)

        # Optimistic local echo for non-private messages
        if not wire.startswith("PRIVATE:"):
            ts = datetime.now().strftime("%H:%M:%S")
            self._append_bubble(ts, self._username, text, "self")

    # ── Receiving ─────────────────────────────────────────────────────────

    def _on_server_line(self, line: str):
        """Dispatch an incoming server line to the correct renderer."""

        # ── User list response ─────────────────────────────────────────────
        if "[SERVER] Online:" in line:
            parts = line.split("Online:", 1)
            if len(parts) == 2:
                users = [u.strip() for u in parts[1].split(",") if u.strip()]
                self._rebuild_dm_list(users)
            self._append_system(line)
            return

        # ── Errors ────────────────────────────────────────────────────────
        if line.startswith("[ERROR]"):
            self._append_error(line)
            return

        # ── System / server notices ────────────────────────────────────────
        if "[SERVER]" in line or "joined" in line or "left" in line:
            self._append_system(line)
            # If a new user joined, auto-refresh the user list
            if "joined" in line:
                self.after(300, self._request_users)
            if "left" in line:
                self.after(300, self._request_users)
            return

        # ── Private received ───────────────────────────────────────────────
        if "[PRIVATE from" in line:
            # Format: [HH:MM:SS] [PRIVATE from Ali] text
            try:
                ts_end  = line.index("]") + 1
                ts      = line[1:ts_end-1]
                rest    = line[ts_end:].strip()
                # rest = "[PRIVATE from Ali] text"
                p_end   = rest.index("]") + 1
                sender  = rest[rest.index("from ")+5:rest.index("]")]
                msg     = rest[p_end:].strip()
                self._append_bubble(ts, sender, msg, "priv_recv")
                self._notif_label.configure(
                    text=f"  ● private from {sender}  ")
                self.after(3000, lambda: self._notif_label.configure(text=""))
            except (ValueError, IndexError):
                self._append_system(line)
            return

        # ── Private sent confirmation ──────────────────────────────────────
        if "[PRIVATE to" in line:
            try:
                ts_end  = line.index("]") + 1
                ts      = line[1:ts_end-1]
                rest    = line[ts_end:].strip()
                p_end   = rest.index("]") + 1
                target  = rest[rest.index("to ")+3:rest.index("]")]
                msg     = rest[p_end:].strip()
                self._append_bubble(ts, f"you → {target}", msg, "priv_sent")
            except (ValueError, IndexError):
                self._append_system(line)
            return

        # ── Broadcast ─────────────────────────────────────────────────────
        try:
            ts_end  = line.index("]") + 1
            ts      = line[1:ts_end-1]
            rest    = line[ts_end:].strip()
            colon   = rest.index(":")
            name    = rest[:colon].strip()
            msg     = rest[colon+1:].strip()
            is_self = (name == self._username)
            if not is_self:
                self._append_bubble(ts, name, msg, "other")
            # Self echo is already shown optimistically
        except (ValueError, IndexError):
            self._append_system(line)

    # ── Message renderers ──────────────────────────────────────────────────

    def _append_bubble(self, ts: str, name: str, text: str, kind: str):
        """
        kind: "self" | "other" | "priv_recv" | "priv_sent"
        """
        name_tag_map = {
            "self":      "self_name",
            "other":     "other_name",
            "priv_recv": "priv_name",
            "priv_sent": "priv_name",
        }
        msg_tag_map = {
            "self":      "msg_self",
            "other":     "msg_other",
            "priv_recv": "msg_priv_recv",
            "priv_sent": "msg_priv_sent",
        }
        name_tag = name_tag_map.get(kind, "other_name")
        msg_tag  = msg_tag_map.get(kind, "msg_other")

        prefix = "🔒 " if "priv" in kind else ""

        self._chat.configure(state="normal")
        self._chat.insert("end", f"  {prefix}{name}  ", name_tag)
        self._chat.insert("end", f"{ts}\n", "timestamp")
        self._chat.insert("end", f"  {text}  \n\n", msg_tag)
        self._chat.configure(state="disabled")
        self._chat.see("end")

    def _append_system(self, text: str):
        self._chat.configure(state="normal")
        self._chat.insert("end", f"\n  {text}\n\n", "system")
        self._chat.configure(state="disabled")
        self._chat.see("end")

    def _append_error(self, text: str):
        self._chat.configure(state="normal")
        self._chat.insert("end", f"\n  {text}\n\n", "error")
        self._chat.configure(state="disabled")
        self._chat.see("end")

    # ── Connection events ──────────────────────────────────────────────────

    def _on_disconnected(self):
        self._status_dot.configure(fg=C_ERROR)
        self._header_label.configure(text="  [disconnected]")
        self._append_error("── Connection to server lost ──")
        self._entry.configure(state="disabled")

    def _request_users(self):
        if self._net:
            self._net.send("/users")

    def _on_close(self):
        if self._net:
            self._net.stop()
        self.destroy()


# ──────────────────────────────────────────────────────────────────────────────

class NetworkLayer:
    """
    All socket I/O lives here — zero tkinter imports.

    • `start()` — opens a daemon recv thread; handles the username handshake.
    • `send(text)` — called from the main thread.
    • `stop()` — closes the socket gracefully.

    Callbacks (always called from the recv thread; the caller is responsible
    for scheduling them onto the main thread via `after()`):
        on_line(line: str)   — a complete server message arrived
        on_disconnect()       — connection dropped
    """

    def __init__(self, sock, username, on_line, on_disconnect):
        self._sock         = sock
        self._username     = username
        self._on_line      = on_line
        self._on_disconnect = on_disconnect
        self._running      = False
        self._registered   = threading.Event()

    def start(self):
        self._running = True
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def send(self, text: str):
        try:
            self._sock.sendall((text + "\n").encode("utf-8"))
        except OSError:
            pass

    def stop(self):
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass

    def _recv_loop(self):
        buf = ""
        username_sent = False

        while self._running:
            try:
                chunk = self._sock.recv(4096).decode("utf-8")
                if not chunk:
                    break

                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    # Intercept the server's username prompt and respond
                    if not username_sent and "username" in line.lower():
                        self.send(self._username)
                        username_sent = True
                        continue

                    self._on_line(line)

            except OSError:
                break

        if self._running:
            self._on_disconnect()
        self._running = False


# ── Entry point ───────────────────────────────────────────────────────────────

def _parse_args():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    try:
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 5555
    except ValueError:
        print("Usage: python client_gui.py [host] [port]")
        sys.exit(1)
    return host, port


if __name__ == "__main__":
    host, port = _parse_args()

   
    app = ChatApp()

    app.mainloop()