"""Thin async wrapper around the meshcore library for the chat TUI."""
from __future__ import annotations

from typing import Optional

from meshcore import MeshCore, EventType


class MeshCoreClient:
    def __init__(self) -> None:
        self.mc: Optional[MeshCore] = None

    async def connect(self, kind: str, ident: str, baudrate: int = 115200) -> None:
        if kind == "serial":
            self.mc = await MeshCore.create_serial(ident, baudrate, auto_reconnect=True)
        elif kind == "ble":
            self.mc = await MeshCore.create_ble(address=ident, auto_reconnect=True)
        else:
            raise ValueError(f"Unknown connection kind: {kind!r}")
        if self.mc is None:
            raise ConnectionError(f"Could not connect to MeshCore node ({kind}: {ident})")
        await self.mc.ensure_contacts()
        await self.fetch_channels(force=True)
        await self.mc.start_auto_message_fetching()

    async def disconnect(self) -> None:
        if self.mc is not None:
            await self.mc.disconnect()

    async def fetch_channels(self, force: bool = False) -> list[dict]:
        """Channel slots aren't listable in bulk - probe indices until GET_CHANNEL errors."""
        if force or not hasattr(self.mc, "channels"):
            channels = []
            idx = 0
            while True:
                res = await self.mc.commands.get_channel(idx)
                if res.type == EventType.ERROR:
                    break
                info = res.payload
                info["channel_secret"] = info["channel_secret"].hex()
                channels.append(info)
                idx += 1
            self.mc.channels = channels
        return self.mc.channels

    @property
    def self_name(self) -> str:
        if self.mc and self.mc.self_info:
            return self.mc.self_info.get("name", "me")
        return "me"

    def contact_list(self) -> list[dict]:
        """Chat-capable contacts (type CHAT or ROOM) for the DM sidebar."""
        if not self.mc:
            return []
        return sorted(
            (c for c in self.mc.contacts.values() if c.get("type") in (1, 3)),
            key=lambda c: c.get("adv_name", "").lower(),
        )

    def contact_by_prefix(self, prefix: str) -> Optional[dict]:
        return self.mc.get_contact_by_key_prefix(prefix) if self.mc else None

    async def add_channel(self, name: str, secret: Optional[bytes] = None) -> tuple[Optional[int], Optional[str]]:
        """Configure a channel into the first free device slot.

        If `secret` is omitted, the key is derived from `name` (sha256), which is
        how MeshCore group channels normally work: anyone who configures the same
        name lands on the same channel automatically.
        """
        idx = 0
        while True:
            res = await self.mc.commands.get_channel(idx)
            if res.type == EventType.ERROR:
                return None, "no free channel slots on this device"
            if not res.payload["channel_name"].strip():
                break
            idx += 1

        res = await self.mc.commands.set_channel(idx, name, secret)
        if res is None or res.type == EventType.ERROR:
            return None, "device rejected the channel"

        await self.fetch_channels(force=True)
        return idx, None

    async def remove_channel(self, idx: int) -> Optional[str]:
        """Blank out a channel slot. There's no dedicated 'delete' command in the
        protocol - clearing name+secret is how MeshCore clients free a slot."""
        res = await self.mc.commands.set_channel(idx, "", b"\x00" * 16)
        if res is None or res.type == EventType.ERROR:
            return "device rejected clearing the channel"
        await self.fetch_channels(force=True)
        return None

    async def send_channel(self, idx: int, text: str):
        return await self.mc.commands.send_chan_msg(idx, text)

    async def send_dm(self, dst, text: str):
        """dst may be a full contact dict, or a raw pubkey-prefix hex string
        for a sender we haven't added as a contact yet."""
        return await self.mc.commands.send_msg_with_retry(
            dst, text, max_attempts=3, flood_after=2, max_flood_attempts=1
        )
