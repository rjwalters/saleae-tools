import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from saleae_tools.mcp import McpError, list_tools


class _Handler(BaseHTTPRequestHandler):
    sse = False

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        msg = json.loads(self.rfile.read(n) or b"{}")
        if msg.get("method") == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        if msg["method"] == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "serverInfo": {"name": "fake"},
            }
        elif msg["method"] == "tools/list":
            assert self.headers.get("Mcp-Session-Id") == "s1"
            result = {
                "tools": [{"name": "start_capture", "description": "Start a capture.\nMore."}]
            }
        else:
            result = {}
        reply = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        body = (
            f"event: message\ndata: {json.dumps(reply)}\n\n" if self.sse else json.dumps(reply)
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if self.sse else "application/json")
        self.send_header("Mcp-Session-Id", "s1")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(params=[False, True], ids=["json", "sse"])
def server(request):
    handler = type("H", (_Handler,), {"sse": request.param})
    srv = HTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_list_tools(server):
    tools = list_tools(server)
    assert [t["name"] for t in tools] == ["start_capture"]


def test_unreachable():
    with pytest.raises(McpError, match="cannot reach"):
        list_tools("http://127.0.0.1:1", timeout=0.5)


def test_cli_mcp_tools(server, capsys):
    from saleae_tools.cli import main

    assert main(["mcp-tools", "--url", server]) == 0
    assert capsys.readouterr().out.startswith("start_capture\tStart a capture.")
