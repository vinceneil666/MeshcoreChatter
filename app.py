"""meshcore-chat - an IRC-style terminal chat client for a MeshCore companion node.

Usage:
    python app.py                  # shows a device picker (BLE + serial)
    python app.py /dev/ttyACM0     # connect straight to a serial port, no picker
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, Label, ListItem, ListView, RichLog, Static

from mc_client import MeshCoreClient
from meshcore import EventType
import history_store


@dataclass
class Target:
    key: str
    kind: str  # "chan" or "dm"
    label: str
    dst: object  # channel idx (int) for chan, contact dict / prefix str for dm
    history: list[str] = field(default_factory=list)
    unread: int = 0


# ---------------------------------------------------------------- picker

class DevicePickerScreen(Screen):
    """Scan for MeshCore devices (BLE + serial) and let the user arrow-key/Enter one."""

    CSS = """
    DevicePickerScreen {
        align: center middle;
    }
    #picker_box {
        width: 70%;
        height: 70%;
        border: heavy $accent;
        padding: 1 2;
    }
    #scan_status {
        height: 2;
        color: $text-muted;
    }
    #device_list {
        height: 1fr;
        border: solid $accent;
    }
    """

    BINDINGS = [
        Binding("r", "rescan", "Rescan"),
        Binding("ctrl+q", "quit_app", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="picker_box"):
            yield Static("Scanning for MeshCore devices...", id="scan_status")
            yield ListView(id="device_list")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self.scan(), exclusive=True)

    async def scan(self) -> None:
        status = self.query_one("#scan_status", Static)
        list_view = self.query_one("#device_list", ListView)
        list_view.clear()
        status.update("Scanning for MeshCore devices...")

        choices: list[tuple[str, str, str]] = []  # (kind, ident, label)

        try:
            from bleak import BleakScanner

            status.update("Scanning BLE (a few seconds)...")
            devices = await BleakScanner.discover(timeout=4.0)
            for d in devices:
                if d.name and d.name.startswith("MeshCore-"):
                    choices.append(("ble", d.address, f"BLE   {d.name}  ({d.address})"))
        except Exception:
            pass  # no BLE adapter / bleak unavailable - just skip BLE devices

        import serial.tools.list_ports

        for port, desc, _hwid in sorted(serial.tools.list_ports.comports()):
            choices.append(("serial", port, f"USB   {port}  {desc}"))

        if not choices:
            status.update("[bold red]No devices found.[/] Press r to rescan, ctrl+q to quit.")
            return

        status.update(f"Found {len(choices)} device(s). ↑/↓ and Enter to connect, r to rescan.")
        for kind, ident, label in choices:
            item = ListItem(Label(label))
            item.device_choice = (kind, ident)
            list_view.append(item)
        list_view.index = 0
        list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        choice = getattr(event.item, "device_choice", None)
        if choice:
            self.dismiss(choice)

    def action_rescan(self) -> None:
        self.run_worker(self.scan(), exclusive=True)

    def action_quit_app(self) -> None:
        self.app.exit()


# ------------------------------------------------------------------ chat

class ChatScreen(Screen):
    CSS = """
    ChatScreen {
        layout: vertical;
        background: $surface;
    }
    #body {
        layout: horizontal;
        height: 1fr;
    }
    #sidebar {
        width: 30;
        border-right: heavy $accent;
        background: $panel;
    }
    #sidebar ListView {
        height: 1fr;
    }
    #main {
        width: 1fr;
        layout: vertical;
    }
    #statusbar {
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    #chatlog {
        height: 1fr;
        padding: 0 1;
    }
    ListItem {
        padding: 0 1;
    }
    ListItem.-unread Label {
        text-style: bold;
        color: $warning;
    }
    ListItem.-active {
        background: $accent 30%;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit_app", "Quit"),
        Binding("f1", "show_help", "Help"),
        Binding("ctrl+up", "prev_target", "Prev chat"),
        Binding("ctrl+down", "next_target", "Next chat"),
        Binding("ctrl+l", "clear_pane", "Clear"),
    ]

    def __init__(self, connection: tuple[str, str]):
        super().__init__()
        self.connection = connection  # (kind, ident) - kind is "serial" or "ble"
        self.client = MeshCoreClient()
        self.targets: dict[str, Target] = {}
        self.target_order: list[str] = []
        self.active_key: str | None = None
        self.list_item_by_key: dict[str, ListItem] = {}
        self.device_id: str | None = None
        self.saved_history: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ UI

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield ListView(id="target_list")
            with Vertical(id="main"):
                yield Static("Connecting...", id="statusbar")
                yield RichLog(id="chatlog", wrap=True, markup=True, highlight=False)
                yield Input(placeholder="Message, or /help for commands", id="input")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#input", Input).focus()
        self.run_worker(self.startup(), exclusive=True)

    # ------------------------------------------------------------- connect

    async def startup(self) -> None:
        log = self.query_one("#chatlog", RichLog)
        kind, ident = self.connection
        log.write(f"[dim]Connecting to MeshCore node ({kind}: {ident})...[/]")
        try:
            await self.client.connect(kind, ident)
        except Exception as exc:  # noqa: BLE001 - surface any connect failure to the user
            log.write(f"[bold red]Connection failed:[/] {exc}")
            self.query_one("#statusbar", Static).update("[bold red]disconnected[/]")
            return

        self.mc = self.client.mc
        self.mc.subscribe(EventType.CONTACT_MSG_RECV, self.on_contact_msg)
        self.mc.subscribe(EventType.CHANNEL_MSG_RECV, self.on_channel_msg)

        self.device_id = self.mc.self_info.get("public_key") or self.client.self_name
        self.saved_history = history_store.load(self.device_id)

        self.rebuild_sidebar()
        first_chan = next((k for k in self.target_order if k.startswith("chan#")), None)
        if first_chan:
            self.switch_target(first_chan)

        self.update_status()
        log.write(f"[bold green]Connected as {self.client.self_name}[/]. Type /help for commands.")

    def rebuild_sidebar(self) -> None:
        list_view = self.query_one("#target_list", ListView)
        list_view.clear()
        self.list_item_by_key.clear()
        self.target_order.clear()

        for ch in self.client.mc.channels:
            # channel slots are pre-allocated on the device; skip unconfigured
            # ones (empty name) except slot 0, which is always the default channel
            if not ch["channel_name"].strip() and ch["channel_idx"] != 0:
                continue
            key = f"chan#{ch['channel_idx']}"
            label = ch["channel_name"] or f"channel {ch['channel_idx']}"
            if key not in self.targets:
                self.targets[key] = Target(
                    key=key, kind="chan", label=label, dst=ch["channel_idx"],
                    history=list(self.saved_history.get(key, [])),
                )
            else:
                self.targets[key].label = label
            self.target_order.append(key)

        for contact in self.client.contact_list():
            key = f"dm#{contact['public_key'][:12]}"
            if key not in self.targets:
                self.targets[key] = Target(
                    key=key, kind="dm", label=contact["adv_name"], dst=contact,
                    history=list(self.saved_history.get(key, [])),
                )
            else:
                self.targets[key].dst = contact
                self.targets[key].label = contact["adv_name"]
            self.target_order.append(key)

        for key in self.target_order:
            item = self._make_list_item(key)
            self.list_item_by_key[key] = item
            list_view.append(item)

    def _make_list_item(self, key: str) -> ListItem:
        t = self.targets[key]
        icon = "Chan: " if t.kind == "chan" else "@ "
        label = Label(f"{icon}{t.label}")
        item = ListItem(label)
        item.target_key = key
        item.label_widget = label
        if key == self.active_key:
            item.add_class("-active")
        if t.unread:
            item.add_class("-unread")
        return item

    def _refresh_list_item(self, key: str) -> None:
        item = self.list_item_by_key.get(key)
        if item is None:
            return
        t = self.targets[key]
        icon = "Chan: " if t.kind == "chan" else "@ "
        text = f"{icon}{t.label}" + (f"  ({t.unread})" if t.unread else "")
        item.label_widget.update(text)
        item.set_class(key == self.active_key, "-active")
        item.set_class(bool(t.unread), "-unread")

    def update_status(self) -> None:
        bar = self.query_one("#statusbar", Static)
        if self.active_key and self.active_key in self.targets:
            t = self.targets[self.active_key]
            kind = "channel" if t.kind == "chan" else "direct message"
            bar.update(f"[b]{self.client.self_name}[/]  |  {kind}: [b]{t.label}[/]  |  ctrl+up/down: switch  |  /help: commands")
        else:
            bar.update(f"[b]{self.client.self_name}[/]  |  no chat selected")

    # -------------------------------------------------------------- switch

    def switch_target(self, key: str) -> None:
        if key not in self.targets:
            return
        self.active_key = key
        t = self.targets[key]
        t.unread = 0

        log = self.query_one("#chatlog", RichLog)
        log.clear()
        for line in t.history:
            log.write(line)

        for k in self.target_order:
            self._refresh_list_item(k)
        self.update_status()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = getattr(event.item, "target_key", None)
        if key:
            self.switch_target(key)
            self.query_one("#input", Input).focus()

    # ------------------------------------------------------------- receive

    def _append(self, key: str, line: str) -> None:
        if key not in self.targets:
            # message from a contact/channel not yet in the sidebar
            self.targets[key] = Target(
                key=key, kind="dm", label=key.split("#", 1)[1], dst=key.split("#", 1)[1],
                history=list(self.saved_history.get(key, [])),
            )
            self.target_order.append(key)
            list_view = self.query_one("#target_list", ListView)
            item = self._make_list_item(key)
            self.list_item_by_key[key] = item
            list_view.append(item)

        t = self.targets[key]
        t.history.append(line)
        if len(t.history) > history_store.MAX_MESSAGES:
            t.history = t.history[-history_store.MAX_MESSAGES:]
        if key == self.active_key:
            self.query_one("#chatlog", RichLog).write(line)
        else:
            t.unread += 1
        self._refresh_list_item(key)
        self.persist_history()

    def persist_history(self) -> None:
        if not self.device_id:
            return
        merged = dict(self.saved_history)
        for key, t in self.targets.items():
            if t.history:
                merged[key] = t.history[-history_store.MAX_MESSAGES:]
        self.saved_history = merged
        history_store.save(self.device_id, merged)

    async def on_contact_msg(self, event) -> None:
        data = event.payload
        contact = self.client.contact_by_prefix(data["pubkey_prefix"])
        name = contact["adv_name"] if contact else data["pubkey_prefix"]
        key = f"dm#{(contact['public_key'][:12] if contact else data['pubkey_prefix'])}"
        ts = time.strftime("%H:%M:%S")
        self._append(key, f"[dim]{ts}[/] [bold cyan]{name}[/]: {data['text']}")

    async def on_channel_msg(self, event) -> None:
        data = event.payload
        idx = data["channel_idx"]
        key = f"chan#{idx}"
        ts = time.strftime("%H:%M:%S")
        self._append(key, f"[dim]{ts}[/] {data['text']}")

    # --------------------------------------------------------------- send

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.query_one("#input", Input).value = ""
        if not text:
            return
        if text.startswith("/"):
            await self.handle_command(text)
            return
        if self.active_key is None:
            self.query_one("#chatlog", RichLog).write("[bold red]No chat selected. Use /join or /msg first.[/]")
            return
        await self.send_to_active(text)

    async def send_to_active(self, text: str) -> None:
        t = self.targets[self.active_key]
        log = self.query_one("#chatlog", RichLog)
        ts = time.strftime("%H:%M:%S")

        if t.kind == "chan":
            full_text = f"{self.client.self_name}: {text}"
            line = f"[dim]{ts}[/] [bold green]{self.client.self_name}[/]: {text}"
            self._append(t.key, line)
            res = await self.client.send_channel(t.dst, full_text)
            if res is None or res.type == EventType.ERROR:
                log.write("[bold red]  ^ failed to send[/]")
        else:
            line = f"[dim]{ts}[/] [bold green]{self.client.self_name}[/]: {text}"
            self._append(t.key, line)
            ok = await self.client.send_dm(t.dst, text)
            if not ok:
                log.write("[bold red]  ^ no ack, delivery uncertain[/]")

    # ------------------------------------------------------------ commands

    async def handle_command(self, text: str) -> None:
        log = self.query_one("#chatlog", RichLog)
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("q", "quit", "exit"):
            self.app.exit()
        elif cmd in ("help", "h", "?"):
            self.show_help()
        elif cmd in ("join", "j", "ch", "channel"):
            self.join_channel(arg)
        elif cmd in ("msg", "dm", "query"):
            self.open_dm(arg)
        elif cmd in ("contacts", "c"):
            await self.client.mc.ensure_contacts(follow=True)
            self.rebuild_sidebar()
            log.write("[dim]contact list refreshed[/]")
        elif cmd in ("channels",):
            await self.client.fetch_channels(force=True)
            self.rebuild_sidebar()
            log.write("[dim]channel list refreshed[/]")
        elif cmd in ("newchannel", "addchannel", "nc"):
            await self.create_channel(arg)
        elif cmd in ("delchannel", "rmchannel", "leave"):
            await self.delete_channel(arg)
        elif cmd == "clear":
            self.action_clear_pane()
        else:
            log.write(f"[bold red]Unknown command:[/] /{cmd}  (try /help)")

    async def create_channel(self, arg: str) -> None:
        log = self.query_one("#chatlog", RichLog)
        if not arg:
            log.write("[bold red]Usage: /newchannel <name> [hex-secret][/]\n"
                       "  Omit the secret to auto-derive a shared key from the name -\n"
                       "  anyone who configures the same name joins the same channel.")
            return
        parts = arg.split()
        name = parts[0]
        secret = bytes.fromhex(parts[1]) if len(parts) > 1 else None
        idx, err = await self.client.add_channel(name, secret)
        if err:
            log.write(f"[bold red]Could not create channel:[/] {err}")
            return
        self.rebuild_sidebar()
        self.switch_target(f"chan#{idx}")
        log.write(f"[bold green]Created '#{name}' in slot {idx}[/]")

    def _find_channel_key(self, arg: str) -> str | None:
        if arg.isdigit():
            key = f"chan#{arg}"
            if key in self.targets:
                return key
        for key in self.target_order:
            t = self.targets[key]
            if t.kind == "chan" and arg.lower() in t.label.lower():
                return key
        return None

    def join_channel(self, arg: str) -> None:
        if not arg:
            self.query_one("#chatlog", RichLog).write("[bold red]Usage: /join <name-or-number>[/]")
            return
        match = self._find_channel_key(arg)
        if match:
            self.switch_target(match)
        else:
            self.query_one("#chatlog", RichLog).write(f"[bold red]No channel matching '{arg}'[/]")

    async def delete_channel(self, arg: str) -> None:
        log = self.query_one("#chatlog", RichLog)
        if not arg:
            log.write("[bold red]Usage: /delchannel <name-or-number>[/]")
            return
        key = self._find_channel_key(arg)
        if key is None:
            log.write(f"[bold red]No channel matching '{arg}'[/]")
            return
        t = self.targets[key]
        if t.dst == 0:
            log.write("[bold red]Refusing to delete slot 0 (Public) - reconfigure it with /newchannel instead if you really want to.[/]")
            return

        err = await self.client.remove_channel(t.dst)
        if err:
            log.write(f"[bold red]Could not delete channel:[/] {err}")
            return

        was_active = key == self.active_key
        del self.targets[key]
        self.target_order.remove(key)
        item = self.list_item_by_key.pop(key, None)
        if item is not None:
            item.remove()
        self.saved_history.pop(key, None)
        self.persist_history()
        log.write(f"[bold green]Deleted channel '{t.label}'[/]")

        if was_active:
            self.active_key = None
            if self.target_order:
                self.switch_target(self.target_order[0])
            else:
                self.query_one("#chatlog", RichLog).clear()
                self.update_status()

    def open_dm(self, arg: str) -> None:
        if not arg:
            self.query_one("#chatlog", RichLog).write("[bold red]Usage: /msg <name>[/]")
            return
        match = None
        for key in self.target_order:
            t = self.targets[key]
            if t.kind == "dm" and arg.lower() in t.label.lower():
                match = key
                break
        if match:
            self.switch_target(match)
        else:
            self.query_one("#chatlog", RichLog).write(f"[bold red]No contact matching '{arg}'[/]")

    def show_help(self) -> None:
        self.query_one("#chatlog", RichLog).write(
            "[bold]Commands:[/]\n"
            "  /join <name|#>   switch channel\n"
            "  /msg <name>      open a direct message with a contact\n"
            "  /newchannel <name> [hex-secret]   create/configure a channel\n"
            "  /delchannel <name|#>   delete a channel\n"
            "  /contacts        refresh contact list\n"
            "  /channels        refresh channel list\n"
            "  /clear           clear the current pane\n"
            "  /quit            exit\n"
            "[bold]Keys:[/] ctrl+up/ctrl+down switch chats, ctrl+l clear, ctrl+q quit"
        )

    # ------------------------------------------------------------- actions

    def action_show_help(self) -> None:
        self.show_help()

    def action_clear_pane(self) -> None:
        if self.active_key:
            self.targets[self.active_key].history.clear()
        self.query_one("#chatlog", RichLog).clear()

    def action_next_target(self) -> None:
        self._step_target(1)

    def action_prev_target(self) -> None:
        self._step_target(-1)

    def _step_target(self, delta: int) -> None:
        if not self.target_order:
            return
        if self.active_key not in self.target_order:
            self.switch_target(self.target_order[0])
            return
        i = self.target_order.index(self.active_key)
        i = (i + delta) % len(self.target_order)
        self.switch_target(self.target_order[i])

    def action_quit_app(self) -> None:
        self.app.exit()

    async def on_unmount(self) -> None:
        await self.client.disconnect()


# ------------------------------------------------------------------- app

class MeshChatApp(App):
    def __init__(self, connection: tuple[str, str] | None = None):
        super().__init__()
        self.initial_connection = connection  # set to skip the picker

    async def on_mount(self) -> None:
        self.run_worker(self.startup_flow(), exclusive=True)

    async def startup_flow(self) -> None:
        connection = self.initial_connection
        if connection is None:
            connection = await self.push_screen_wait(DevicePickerScreen())
            if connection is None:
                self.exit()
                return
        await self.push_screen(ChatScreen(connection))


def main() -> None:
    connection = None
    if len(sys.argv) > 1:
        connection = ("serial", sys.argv[1])
    MeshChatApp(connection).run()


if __name__ == "__main__":
    main()
