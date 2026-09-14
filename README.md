# MeshcoreChatter

An IRC-style terminal chat client for a [MeshCore](https://github.com/meshcore-dev/MeshCore) companion radio node, built with [Textual](https://textual.textualize.io/).

Connects to a MeshCore companion device (over USB serial or BLE), and gives you a proper terminal UI on top of it: a channel/contact sidebar, a scrolling message pane, unread badges, and slash commands - instead of driving the mesh one line at a time.

## Features

- **Device picker on startup** - scans for BLE MeshCore devices (`MeshCore-*`) and lists all serial ports, navigate with arrow keys, `Enter` to connect.
- **Sidebar** listing channels (`Chan: name`) and direct-message contacts (`@ name`), with unread counts.
- **Persistent history** - the last 50 messages of every chat are remembered across restarts, keyed to the connected node's own public key (so it follows that physical device regardless of which `/dev/ttyACMx` it enumerates as, or whether you connect over USB or BLE).
- **Slash commands**: `/join`, `/msg`, `/newchannel`, `/delchannel`, `/addcontact`, `/importcontact`, `/mycard`, `/corescope`, `/reply`, `/contacts`, `/channels`, `/clear`, `/quit`, `/help`.
- **Keyboard-first**: `ctrl+up` / `ctrl+down` to switch chats, `ctrl+r` to reply, `esc` to cancel a reply, `ctrl+l` to clear the pane, `ctrl+q` to quit, `f1` for help, `f2` for app info.
- **Live CoreScope analytics panel** - at startup, pick a [CoreScope](https://github.com/Kpa-clawbot/CoreScope) analytics server (from a predefined list in `corescope_servers.txt`, or type your own URL, or skip). A panel at the bottom of the chat screen shows a simple, deduplicated list of the actual repeaters that relayed the last few messages in the active channel (resolved from the packet's real hop path, not just who observed it).
- **Reply to a message** - `ctrl+r` (or `/reply`) opens a picker of recent messages in the current chat; click one, or arrow-key + Enter. Your next message goes out prefixed with just the original sender's name, and a banner shows who you're replying to until you send or cancel (`Esc`).
- **Adding contacts** - `/addcontact` a known public key directly, `/importcontact` a card someone shared with you, or `/mycard` to get your own shareable card to hand to someone else.

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
| `f2` | App info (name, description, developer, GitHub link) |

| Command | Description |
|---|---|
| `/join <name\|#>` | Switch to a channel |
| `/msg <name>` | Open a direct message with a contact |
| `/newchannel <name> [hex-secret]` | Create/configure a channel. Omit the secret to auto-derive a shared key from the name - anyone who configures the same name joins the same channel. |
| `/delchannel <name\|#>` | Delete a channel (refuses to delete slot 0 / Public) |
| `/addcontact <pubkey-hex> <name>` | Manually add a contact you already know the 64-char public key of |
| `/importcontact meshcore://<hex>` | Import a contact from a card someone shared with you |
| `/mycard [name]` | Get a shareable `meshcore://` card - your own node's, or a known contact's, to hand to someone else for `/importcontact` |
| `/corescope <url\|off>` | Set or disable the live CoreScope analytics server |
| `/corescope view <repeaters\|paths>` | Switch the analytics panel between the repeater list and the per-message hop-path view |
| `/reply` | Open a picker to choose a recent message to reply to |
| `/contacts` | Refresh the contact list from the device |
| `/channels` | Refresh the channel list from the device |
| `/clear` | Clear the current pane |
| `/quit` | Exit |

Outgoing channel messages go out as just the message text - MeshCore's group-channel protocol carries no sender identity of its own, so there's no way for recipients to attribute a channel message to you. Your own pane still shows your name next to what you send, but that's local display only, not part of the broadcast.

## How history persistence works

Message history lives in `~/.meshcore-chat/history/<node-public-key>.json`, one file per physical node, capped at the last 50 messages per chat. It's identified by the node's public key rather than the connection path, so switching from USB to BLE (or the port renumbering after a reboot) doesn't lose or fork your history - only connecting to a genuinely different node does.

## CoreScope live analytics

[CoreScope](https://github.com/Kpa-clawbot/CoreScope) is a separate, community-run MeshCore packet analyzer with a public REST API (no auth required by default). For the last few messages in the active channel, this app fetches each packet's real recorded hop path (`GET /api/packets/{id}`) and resolves those hash prefixes to repeater names (`GET /api/resolve-hops`), then shows a simple deduplicated list of the repeaters actually involved - not just who happened to observe the packet.

Predefined servers are read from `corescope_servers.txt` (one `Name = https://host` per line, `#` for comments) and offered in the startup picker alongside a free-text URL field and a skip option. Change or disable it later at any time with `/corescope <url>` / `/corescope off`. It only covers channels (group broadcasts) - direct messages are point-to-point encrypted and aren't visible to a passive analyzer, so the panel shows a placeholder for those.

By default the panel shows the deduplicated repeater-list view above. Switch to `/corescope view paths` for a per-message view instead: the last 4 messages in the active channel, each with a shortened text snippet followed by the raw hop path its packet took (e.g. `"Hei"  ->  4DFF5A -> B13244`) - useful for seeing which specific route each message actually traveled, rather than just the pooled set of repeaters involved. `/corescope view repeaters` switches back.

CoreScope's own remote observer(s) can hear channel traffic your node never did, so the paths view checks each message against your own chat history for that channel and appends `(not received locally)` to any message CoreScope saw that your node didn't.

## Replying to a message

MeshCore's own protocol has no concept of threaded replies - there's no message-ID field to point back to. `ctrl+r` opens a picker over your recent messages in the current chat (click a row, or arrow-key + Enter); once picked, your next message is sent with just the original sender's name prepended, using the `@[Name] message` mention style already used natively by other clients on the mesh - no quoted excerpt of the original message, only who you're replying to. If the original message has no identifiable sender, name inference falls back to whatever convention the sender's own client used to bake identity into the text - either that same `@[Name] message` style, or the plainer `Name: message` style - and if neither is present (e.g. a bare "ping"), no prefix is added at all. Only messages sent or received during the current session are pickable (reply targets aren't persisted across restarts). `Esc` cancels a pending reply.

## Adding contacts

MeshCore normally builds your contact list from adverts your node overhears on the mesh, but you can also add someone directly:

- **`/addcontact <pubkey-hex> <name>`** - if you already know someone's full 64-character public key (e.g. from a `pubkey` note, a map, another tool), this adds them straight away with no advert or card needed.
- **`/importcontact meshcore://<hex>`** - imports a contact from a card someone else exported and sent you (over chat, email, a QR code, however).
- **`/mycard [name]`** - exports a shareable `meshcore://...` card: with no argument, it's your own node's card (hand this to someone else so *they* can `/importcontact` you); with a name, it re-exports one of your existing contacts' cards to pass along.

## Project layout

- `app.py` - the Textual application (device picker screen, CoreScope server picker screen, chat screen)
- `mc_client.py` - thin async wrapper around the `meshcore` library
- `history_store.py` - per-device message history persistence
- `corescope_client.py` - thin async client for the CoreScope REST API
- `corescope_servers.txt` - predefined CoreScope server list offered at startup
- `run.sh` - launcher
