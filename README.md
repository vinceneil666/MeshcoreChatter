# MeshcoreChatter

An IRC-style terminal chat client for a [MeshCore](https://github.com/meshcore-dev/MeshCore) companion radio node, built with [Textual](https://textual.textualize.io/).

Connects to a MeshCore companion device (over USB serial or BLE), and gives you a proper terminal UI on top of it: a channel/contact sidebar, a scrolling message pane, unread badges, and slash commands - instead of driving the mesh one line at a time.

## Features

- **Device picker on startup** - scans for BLE MeshCore devices (`MeshCore-*`) and lists all serial ports, navigate with arrow keys, `Enter` to connect.
- **Sidebar** listing channels (`Chan: name`) and direct-message contacts (`@ name`), with unread counts.
- **Persistent history** - the last 50 messages of every chat are remembered across restarts, keyed to the connected node's own public key (so it follows that physical device regardless of which `/dev/ttyACMx` it enumerates as, or whether you connect over USB or BLE).
- **Slash commands**: `/join`, `/msg`, `/newchannel`, `/delchannel`, `/corescope`, `/reply`, `/contacts`, `/channels`, `/clear`, `/quit`, `/help`.
- **Keyboard-first**: `ctrl+up` / `ctrl+down` to switch chats, `ctrl+r` to reply, `esc` to cancel a reply, `ctrl+l` to clear the pane, `ctrl+q` to quit, `f1` for help.
- **Live CoreScope analytics panel** - at startup, pick a [CoreScope](https://github.com/Kpa-clawbot/CoreScope) analytics server (from a predefined list in `corescope_servers.txt`, or type your own URL, or skip). A panel at the bottom of the chat screen shows a simple, deduplicated list of the actual repeaters that relayed the last few messages in the active channel (resolved from the packet's real hop path, not just who observed it).
- **Reply to a message** - `ctrl+r` (or `/reply`) opens a picker of recent messages in the current chat; click one, or arrow-key + Enter. Your next message goes out with a compact quote of the original prepended, and a banner shows what you're replying to until you send or cancel (`Esc`).

## Requirements

- Python 3.10+
- A MeshCore node flashed with **companion** firmware (BLE or USB variant - see the [MeshCore releases](https://github.com/meshcore-dev/MeshCore/releases)). Room-server / repeater firmware will not work with this client.
- On Linux, your user needs access to the serial device, typically via the `dialout` group:
  ```
  sudo usermod -aG dialout $USER
  # log out and back in for it to take effect
  ```

## Install

```bash
git clone https://github.com/vinceneil666/MeshcoreChatter.git
cd MeshcoreChatter
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Run

```bash
./run.sh
```

With no arguments this shows the device picker (BLE scan + serial port list). To skip the picker and connect straight to a known serial port:

```bash
./run.sh /dev/ttyACM0
```

If you're running this over SSH, launch it inside `tmux` or `screen` so the session survives a disconnect:

```bash
tmux new -s mesh
./run.sh
# ctrl+b d to detach, `tmux attach -t mesh` to come back
```

## Usage

| Key | Action |
|---|---|
| `↑` / `↓` + `Enter` | Navigate/select in the device picker and sidebar |
| `ctrl+up` / `ctrl+down` | Switch between chats |
| `ctrl+l` | Clear the current pane |
| `ctrl+q` | Quit |
| `f1` | Help |

| Command | Description |
|---|---|
| `/join <name\|#>` | Switch to a channel |
| `/msg <name>` | Open a direct message with a contact |
| `/newchannel <name> [hex-secret]` | Create/configure a channel. Omit the secret to auto-derive a shared key from the name - anyone who configures the same name joins the same channel. |
| `/delchannel <name\|#>` | Delete a channel (refuses to delete slot 0 / Public) |
| `/corescope <url\|off>` | Set or disable the live CoreScope analytics server |
| `/reply` | Open a picker to choose a recent message to reply to |
| `/contacts` | Refresh the contact list from the device |
| `/channels` | Refresh the channel list from the device |
| `/clear` | Clear the current pane |
| `/quit` | Exit |

Outgoing channel messages are automatically prefixed with your node's advertised name (`Name: message`), since MeshCore's group-channel protocol doesn't carry sender identity itself - this is what lets other MeshCore users tell who's talking in a channel.

## How history persistence works

Message history lives in `~/.meshcore-chat/history/<node-public-key>.json`, one file per physical node, capped at the last 50 messages per chat. It's identified by the node's public key rather than the connection path, so switching from USB to BLE (or the port renumbering after a reboot) doesn't lose or fork your history - only connecting to a genuinely different node does.

## CoreScope live analytics

[CoreScope](https://github.com/Kpa-clawbot/CoreScope) is a separate, community-run MeshCore packet analyzer with a public REST API (no auth required by default). For the last few messages in the active channel, this app fetches each packet's real recorded hop path (`GET /api/packets/{id}`) and resolves those hash prefixes to repeater names (`GET /api/resolve-hops`), then shows a simple deduplicated list of the repeaters actually involved - not just who happened to observe the packet.

Predefined servers are read from `corescope_servers.txt` (one `Name = https://host` per line, `#` for comments) and offered in the startup picker alongside a free-text URL field and a skip option. Change or disable it later at any time with `/corescope <url>` / `/corescope off`. It only covers channels (group broadcasts) - direct messages are point-to-point encrypted and aren't visible to a passive analyzer, so the panel shows a placeholder for those.

## Replying to a message

MeshCore's own protocol has no concept of threaded replies - there's no message-ID field to point back to. `ctrl+r` opens a picker over your recent messages in the current chat (click a row, or arrow-key + Enter); once picked, your next message is sent with a short quote of the original prepended (`↩Sender: "snippet" | your reply`), which is how the recipient - on this client or any other MeshCore client - sees the context. Only messages sent or received during the current session are pickable (reply targets aren't persisted across restarts). `Esc` cancels a pending reply.

## Project layout

- `app.py` - the Textual application (device picker screen, CoreScope server picker screen, chat screen)
- `mc_client.py` - thin async wrapper around the `meshcore` library
- `history_store.py` - per-device message history persistence
- `corescope_client.py` - thin async client for the CoreScope REST API
- `corescope_servers.txt` - predefined CoreScope server list offered at startup
- `run.sh` - launcher
