from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests


DEFAULT_DESCRIPTOR = Path.home() / ".flowpromax" / "workflow" / "mcp_descriptor.json"


def _load_descriptor(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid MCP descriptor: {path}")
    return payload


def _resolve_connection(args) -> tuple[str, str]:
    descriptor_path = Path(
        args.descriptor
        or os.environ.get("FLOW_PRO_MAX_MCP_DESCRIPTOR")
        or DEFAULT_DESCRIPTOR
    )
    payload = _load_descriptor(descriptor_path)
    base_url = str(args.base_url or payload.get("base_url") or "").rstrip("/")
    token = str(args.token or payload.get("token") or "")
    if not base_url or not token:
        raise RuntimeError("Missing MCP base_url or token")
    return base_url, token


def _request(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.request(
        method=method.upper(),
        url=url,
        headers={"Authorization": f"Bearer {token}"},
        json=payload if payload is not None else None,
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {"value": data}


def cmd_manifest(args) -> int:
    base_url, token = _resolve_connection(args)
    data = _request("GET", f"{base_url}/api/mcp/manifest", token)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_list_tools(args) -> int:
    base_url, token = _resolve_connection(args)
    data = _request("GET", f"{base_url}/api/mcp/tools", token)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_invoke(args) -> int:
    base_url, token = _resolve_connection(args)
    payload: dict[str, Any] = {}
    if args.json_file:
        payload = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    data = _request("POST", f"{base_url}/api/mcp/tools/{args.tool}/invoke", token, payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_import_board(args) -> int:
    base_url, token = _resolve_connection(args)
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    data = _request("POST", f"{base_url}/api/mcp/tools/workflow_import_board/invoke", token, payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_export_board(args) -> int:
    base_url, token = _resolve_connection(args)
    data = _request(
        "POST",
        f"{base_url}/api/mcp/tools/workflow_export_board/invoke",
        token,
        {"board_id": int(args.board_id)},
    )
    output_path = Path(args.out)
    output_path.write_text(json.dumps(data.get("content") or data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(output_path))
    return 0


def cmd_upload_file(args) -> int:
    base_url, token = _resolve_connection(args)
    payload = {
        "file_path": str(Path(args.file)),
        "project_id": str(args.project_id),
    }
    if args.file_name:
        payload["file_name"] = str(args.file_name)
    data = _request("POST", f"{base_url}/api/mcp/tools/workflow_upload_file/invoke", token, payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_upload_url(args) -> int:
    base_url, token = _resolve_connection(args)
    payload = {
        "url": str(args.url),
        "project_id": str(args.project_id),
    }
    if args.file_name:
        payload["file_name"] = str(args.file_name)
    data = _request("POST", f"{base_url}/api/mcp/tools/workflow_upload_url/invoke", token, payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_media_status(args) -> int:
    base_url, token = _resolve_connection(args)
    data = _request(
        "POST",
        f"{base_url}/api/mcp/tools/workflow_get_media_status/invoke",
        token,
        {"media_id": str(args.media_id)},
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_media_info(args) -> int:
    base_url, token = _resolve_connection(args)
    data = _request(
        "POST",
        f"{base_url}/api/mcp/tools/workflow_get_media_info/invoke",
        token,
        {"media_id": str(args.media_id)},
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_plan_board(args) -> int:
    base_url, token = _resolve_connection(args)
    brief = str(args.brief or "")
    if args.brief_file:
        brief = Path(args.brief_file).read_text(encoding="utf-8")
    payload = {
        "brief": brief,
        "node_limit": int(args.node_limit),
        "dry_run": bool(args.dry_run),
    }
    if args.board_name:
        payload["board_name"] = str(args.board_name)
    data = _request("POST", f"{base_url}/api/mcp/tools/workflow_plan_board/invoke", token, payload)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Flow Pro Max local MCP CLI")
    parser.add_argument("--descriptor", help="Path to MCP descriptor JSON")
    parser.add_argument("--base-url", help="Override loopback base URL")
    parser.add_argument("--token", help="Override MCP bearer token")

    sub = parser.add_subparsers(dest="command", required=True)

    manifest = sub.add_parser("manifest", help="Print MCP manifest")
    manifest.set_defaults(func=cmd_manifest)

    tools = sub.add_parser("list-tools", help="List MCP tools")
    tools.set_defaults(func=cmd_list_tools)

    invoke = sub.add_parser("invoke", help="Invoke a tool using the MCP invoke schema")
    invoke.add_argument("tool", help="Tool name")
    invoke.add_argument("--json-file", help="JSON file containing tool args")
    invoke.set_defaults(func=cmd_invoke)

    imp = sub.add_parser("import-board", help="Import a Flowboard board JSON via MCP")
    imp.add_argument("file", help="Path to workflow JSON file")
    imp.set_defaults(func=cmd_import_board)

    exp = sub.add_parser("export-board", help="Export a board to JSON via MCP")
    exp.add_argument("board_id", type=int, help="Board id")
    exp.add_argument("out", help="Output JSON path")
    exp.set_defaults(func=cmd_export_board)

    upload_file = sub.add_parser("upload-file", help="Upload a local file through workflow MCP")
    upload_file.add_argument("file", help="Local file path")
    upload_file.add_argument("project_id", help="Flow project id")
    upload_file.add_argument("--file-name", help="Optional override name for the uploaded file")
    upload_file.set_defaults(func=cmd_upload_file)

    upload_url = sub.add_parser("upload-url", help="Upload a remote URL through workflow MCP")
    upload_url.add_argument("url", help="Remote asset URL")
    upload_url.add_argument("project_id", help="Flow project id")
    upload_url.add_argument("--file-name", help="Optional override file name")
    upload_url.set_defaults(func=cmd_upload_url)

    media_status = sub.add_parser("media-status", help="Read media availability/status via workflow MCP")
    media_status.add_argument("media_id", help="Media id")
    media_status.set_defaults(func=cmd_media_status)

    media_info = sub.add_parser("media-info", help="Read media metadata via workflow MCP")
    media_info.add_argument("media_id", help="Media id")
    media_info.set_defaults(func=cmd_media_info)

    plan = sub.add_parser("plan-board", help="Generate a workflow board from a brief via MCP planner")
    plan.add_argument("brief", nargs="?", help="Planner brief text")
    plan.add_argument("--brief-file", help="Read planner brief from a text file")
    plan.add_argument("--board-name", help="Optional board name override")
    plan.add_argument("--node-limit", type=int, default=8, help="Maximum number of planned nodes")
    plan.add_argument("--dry-run", action="store_true", help="Plan without persisting the board")
    plan.set_defaults(func=cmd_plan_board)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
