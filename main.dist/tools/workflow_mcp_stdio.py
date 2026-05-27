from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from tools.workflow_mcp_cli import DEFAULT_DESCRIPTOR, _load_descriptor, _request
except ImportError:
    from workflow_mcp_cli import DEFAULT_DESCRIPTOR, _load_descriptor, _request

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "flow-pro-max-local"
SERVER_VERSION = "1.0"


def _resolve_connection() -> tuple[str, str]:
    descriptor_path = Path(
        os.environ.get("FLOW_PRO_MAX_MCP_DESCRIPTOR")
        or DEFAULT_DESCRIPTOR
    )
    payload = _load_descriptor(descriptor_path)
    base_url = str(payload.get("base_url") or "").rstrip("/")
    token = str(payload.get("token") or "")
    if not base_url or not token:
        raise RuntimeError("Missing MCP base_url or token in descriptor")
    return base_url, token


def _tool_descriptors(base_url: str, token: str) -> list[dict[str, Any]]:
    rows = _request("GET", f"{base_url}/api/mcp/tools", token).get("tools") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        params = list(row.get("params") or [])
        properties = {str(name): {} for name in params if str(name).strip()}
        out.append(
            {
                "name": str(row.get("name") or ""),
                "description": f"Flow Pro Max workflow tool ({str(row.get('capability') or 'read')})",
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                    "additionalProperties": True,
                },
            }
        )
    return out


def _write_message(payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        text = line.decode("utf-8", errors="replace").strip()
        if not text or ":" not in text:
            continue
        key, value = text.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length") or "0")
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    payload = json.loads(body.decode("utf-8"))
    return payload if isinstance(payload, dict) else None


def _success(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _handle_request(message: dict[str, Any], base_url: str, token: str) -> dict[str, Any] | None:
    method = str(message.get("method") or "")
    message_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if not method:
        return _error(message_id, -32600, "Invalid request")
    if method == "initialize":
        return _success(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _success(message_id, {})
    if method == "tools/list":
        return _success(message_id, {"tools": _tool_descriptors(base_url, token)})
    if method == "tools/call":
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if not tool_name:
            return _error(message_id, -32602, "tools/call requires params.name")
        try:
            data = _request("POST", f"{base_url}/api/mcp/tools/{tool_name}/invoke", token, arguments)
            content = data.get("content") if isinstance(data, dict) and "content" in data else data
            return _success(
                message_id,
                {
                    "content": [{"type": "text", "text": json.dumps(content, ensure_ascii=False, indent=2)}],
                    "structuredContent": content,
                    "isError": False,
                },
            )
        except Exception as exc:
            return _success(
                message_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
    if method == "resources/list":
        return _success(message_id, {"resources": []})
    if method == "prompts/list":
        return _success(message_id, {"prompts": []})
    return _error(message_id, -32601, f"Method not found: {method}")


def main() -> int:
    try:
        base_url, token = _resolve_connection()
    except Exception as exc:
        sys.stderr.write(f"workflow_mcp_stdio bootstrap failed: {exc}\n")
        sys.stderr.flush()
        return 1

    while True:
        message = _read_message()
        if message is None:
            return 0
        response = _handle_request(message, base_url, token)
        if response is not None and "id" in response:
            _write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
