# MeshcoreChatter

An IRC-style terminal chat client for a [MeshCore](https://github.com/meshcore-dev/MeshCore) companion radio node, built with [Textual](https://textual.textualize.io/).

Connects to a MeshCore companion device (over USB serial or BLE), and gives you a proper terminal UI on top of it: a channel/contact sidebar, a scrolling message pane, unread badges, and slash commands - instead of driving the mesh one line at a time.

## Features

- **Device picker on startup** - scans for BLE MeshCore devices (`MeshCore-*`) and lists all serial ports, navigate with arrow keys, `Enter` to connect.
- **Sidebar** listing channels (`Chan: name`) and direct-message contacts (`@ name`), with unread counts.
- **Persistent history** - the last 50 messages of every chat are remembered across restarts, keyed to the connected node's own public key (so it follows that physical device regardless of which `/dev/ttyACMx` it enumerates as, or whether you connect over USB or BLE).
- **Slash commands**: `/join`, `/msg`, `/newchannel`, `/delchannel`, `/contacts`, `/channels`, `/clear`, `/quit`, `/help`.
- **Keyboard-first**: `ctrl+up` / `ctrl+down` to switch chats, `ctrl+l` to clear the pane, `ctrl+q` to quit, `f1` for help.

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
git clone https://github.com/<you>/MeshcoreChatter.git
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
| `/contacts` | Refresh the contact list from the device |
| `/channels` | Refresh the channel list from the device |
| `/clear` | Clear the current pane |
| `/quit` | Exit |

Outgoing channel messages are automatically prefixed with your node's advertised name (`Name: message`), since MeshCore's group-channel protocol doesn't carry sender identity itself - this is what lets other MeshCore users tell who's talking in a channel.

## How history persistence works

Message history lives in `~/.meshcore-chat/history/<node-public-key>.json`, one file per physical node, capped at the last 50 messages per chat. It's identified by the node's public key rather than the connection path, so switching from USB to BLE (or the port renumbering after a reboot) doesn't lose or fork your history - only connecting to a genuinely different node does.

## Project layout

- `app.py` - the Textual application (device picker screen + chat screen)
- `mc_client.py` - thin async wrapper around the `meshcore` library
- `history_store.py` - per-device message history persistence
- `run.sh` - launcher
