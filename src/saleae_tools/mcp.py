"""Probe the Logic 2 MCP server (Streamable HTTP, default 127.0.0.1:10530).

Saleae does not publish the tool list, so this asks the server. Stdlib only.
Register the server with Claude Code separately::

    claude mcp add --transport http logic2 http://127.0.0.1:10530
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = "http://127.0.0.1:10530"
PROTOCOL = "2025-06-18"


class McpError(RuntimeError):
    pass


def _post(
    url: str, payload: dict[str, Any], session: str | None, timeout: float
) -> tuple[Any, str | None]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL,
            **({"Mcp-Session-Id": session} if session else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            session = resp.headers.get("Mcp-Session-Id", session)
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read().decode()
    except urllib.error.URLError as e:
        raise McpError(f"cannot reach MCP server at {url}: {e.reason}") from e
    if not body.strip():
        return None, session
    if "text/event-stream" in ctype:
        msgs = [
            json.loads(line[5:].strip())
            for line in body.splitlines()
            if line.startswith("data:") and line[5:].strip()
        ]
        return (msgs[-1] if msgs else None), session
    return json.loads(body), session


def list_tools(url: str = DEFAULT_URL, timeout: float = 5.0) -> list[dict[str, Any]]:
    """Initialize a session and return the server's ``tools/list`` result."""
    init, session = _post(
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "saleae-tools", "version": "0.1.0"},
            },
        },
        None,
        timeout,
    )
    if not init or "result" not in init:
        raise McpError(f"unexpected initialize reply: {init!r}")
    _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session, timeout)
    reply, _ = _post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session, timeout)
    if not reply or "result" not in reply:
        raise McpError(f"unexpected tools/list reply: {reply!r}")
    tools: list[dict[str, Any]] = reply["result"].get("tools", [])
    return tools
