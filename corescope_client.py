"""Async client for a CoreScope (https://github.com/Kpa-clawbot/CoreScope) MeshCore
analytics server's public REST API. No authentication is required by a stock
CoreScope instance, but an API key can be supplied if a deployment requires one.
"""
from __future__ import annotations

import urllib.parse
from typing import Optional

import httpx


class CoreScopeClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: float = 8.0):
        self.base_url = base_url.rstrip("/")
        headers = {"X-API-Key": api_key} if api_key else {}
        self._http = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=timeout)

    async def health(self) -> dict:
        r = await self._http.get("/api/health")
        r.raise_for_status()
        return r.json()

    async def channel_messages(self, channel_hash: str, limit: int = 10) -> list[dict]:
        """Recent decoded messages CoreScope has observed for a channel (identified
        by its `#name` or `Public`, matching MeshCore's own channel_hash convention)."""
        encoded = urllib.parse.quote(channel_hash, safe="")
        r = await self._http.get(f"/api/channels/{encoded}/messages", params={"limit": limit})
        r.raise_for_status()
        return r.json().get("messages", [])

    async def node_paths(self, pubkey: str) -> dict:
        """Routing paths CoreScope has reconstructed to/through a node."""
        r = await self._http.get(f"/api/nodes/{pubkey}/paths")
        r.raise_for_status()
        return r.json()

    async def packet_path(self, packet_id: int) -> list[str]:
        """The ordered list of hop hash-prefixes (e.g. "5CE881") a packet's header
        recorded - i.e. the repeaters it was relayed through, in order."""
        r = await self._http.get(f"/api/packets/{packet_id}")
        r.raise_for_status()
        return r.json().get("path", [])

    async def resolve_hops(self, hop_prefixes: list[str]) -> dict[str, str]:
        """Resolve hop hash-prefixes to repeater names. Returns {prefix: name}."""
        if not hop_prefixes:
            return {}
        r = await self._http.get("/api/resolve-hops", params={"hops": ",".join(hop_prefixes)})
        r.raise_for_status()
        resolved = r.json().get("resolved", {})
        return {prefix: info.get("name", prefix) for prefix, info in resolved.items()}

    async def stats(self) -> dict:
        r = await self._http.get("/api/stats")
        r.raise_for_status()
        return r.json()

    async def aclose(self) -> None:
        await self._http.aclose()
