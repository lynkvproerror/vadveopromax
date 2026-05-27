from __future__ import annotations

import argparse
import json
import secrets
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workflow.manager import WorkflowManager
from workflow_live_smoke import (
    SmokeController,
    _get_app_control_session,
    _get_paygate_tier,
    _log,
    _preflight_or_raise,
    _request_block_reason,
    _wait_for_request,
)


def _build_character_prompt() -> str:
    return ", ".join(
        [
            "Studio portrait headshot of a Japanese female character",
            "subject directly faces the camera, head perfectly straight with zero tilt and zero turn",
            "shoulders square to camera, axially symmetric pose, nose centered, both eyes equally visible at the same height",
            "Clean Girl makeup styling, fresh dewy skin with sheer skin-tint coverage, healthy natural radiance",
            "brushed-up laminated brows with clear brow gel finish, minimal eye makeup, glossy plump lips with lip-oil sheen",
            "slicked-back low bun or polished sleek hair, simple modern minimalist outfit, delicate gold hoop earrings",
            "relaxed friendly expression with a gentle subtle smile, soft natural gaze, soft natural daylight, airy bright tone, clean minimalist backdrop",
            "head and shoulders framing, centered composition, sharp focus on face",
            "strictly front-on orientation, no head tilt, no head turn, no profile angle, no three-quarter view, no over-the-shoulder pose",
            "no glasses, no hat, no mask, no occlusion, nothing covering the face",
            "photorealistic, ultra-detailed, consistent character reference",
        ]
    )


def _build_storyboard_prompt(topic: str, *, rows: int = 2, cols: int = 2) -> str:
    total = rows * cols
    clean_topic = str(topic or "").strip() or "untitled story"
    return " ".join(
        [
            f'Create a visual storyboard for "{clean_topic}" as a SINGLE composite IMAGE',
            f"arranged in a {rows}x{cols} grid ({rows} rows, {cols} columns, {total} tiles total).",
            "Each tile shows one beat of the story.",
            f"Tiles read left-to-right, top-to-bottom in narrative order (1 -> {total}).",
            "STRICT layout rules:",
            "Clean WHITE MARGINS between every tile with no overlapping borders and no bleed between tiles.",
            "Each tile is rectangular, identical size, and sharply separated from its neighbors.",
            f"In the TOP-LEFT corner of every tile, place a small NUMBER label (1, 2, 3, ..., {total}) that is readable and consistent across all tiles.",
            "BENEATH each tile, outside the picture area in the white margin below, print a SHORT one-sentence caption describing the action of that beat in the same language as the topic.",
        ]
    )


def _build_storyboard_video_prompt(total_frames: int = 4) -> str:
    return (
        "A 10-seconds cinematic animated film trailer following narrative progression "
        f"from exactly frame 1 to frame {int(total_frames)} of the image reference"
    )


def _first_media_id(request_row: dict[str, Any]) -> str:
    media_ids = [str(item) for item in list((request_row.get("result") or {}).get("media_ids") or []) if str(item or "").strip()]
    if not media_ids:
        raise RuntimeError(f"Request {request_row.get('id')} completed without media ids")
    return media_ids[0]


def _board_output_files(board_output_dir: Path) -> list[str]:
    return [str(path) for path in board_output_dir.rglob("*") if path.is_file()]


def _cancel_on_runtime_block(manager: WorkflowManager, request_id: int, label: str, log_path: Path):
    def _callback(row: dict[str, Any]) -> str | None:
        reason = _request_block_reason(manager, row)
        if not reason:
            return None
        try:
            manager._cancel_local_request(request_id)
        except Exception:
            pass
        _log(f"{label}: fail-fast runtime block -> {reason}", log_path=log_path)
        return f"{label} blocked during execution: {reason}"

    return _callback


def _run_chain_smoke(args: argparse.Namespace) -> dict[str, Any]:
    smoke_root = Path(args.smoke_root).expanduser() if args.smoke_root else Path(
        tempfile.mkdtemp(prefix="workflow-chain-smoke-")
    )
    smoke_root.mkdir(parents=True, exist_ok=True)
    log_path = smoke_root / "chain_smoke.log"
    report_path = Path(args.report_path).expanduser() if args.report_path else smoke_root / "chain_smoke_report.json"

    runtime_base_url = str(args.runtime_base_url or "http://127.0.0.1:8100").rstrip("/")
    session_id = str(args.session_id or "").strip() or _get_app_control_session(runtime_base_url) or secrets.token_hex(16)
    paygate_tier = str(args.paygate_tier or "").strip() or _get_paygate_tier(runtime_base_url)

    _log(
        f"chain-smoke runtime={runtime_base_url} session_id={session_id} paygate_tier={paygate_tier}",
        log_path=log_path,
    )

    controller = SmokeController(
        runtime_base_url,
        session_id,
        ttl_seconds=20,
        source_name="workflow_chain_smoke",
    )
    manager = WorkflowManager(
        controller,
        app_data_dir=smoke_root / "appdata",
        frontend_dist_dir=REPO_ROOT / "workflow_frontend" / "dist",
    )

    success = False
    try:
        host_url = manager.start()
        _log(f"workflow host started at {host_url}", log_path=log_path)

        output_root = smoke_root / "output"
        input_root = smoke_root / "resource_input"
        output_root.mkdir(parents=True, exist_ok=True)
        input_root.mkdir(parents=True, exist_ok=True)
        manager._set_workflow_resource_input_folder(str(input_root))
        manager._set_workflow_output_folder(str(output_root), apply_existing=False)

        board = manager.store.create_board(str(args.board_name or "Workflow Chain Smoke"))
        board_id = int(board["id"])
        manager.store.patch_ui_state({"active_board_id": board_id})

        character_node = manager.store.create_node(
            board_id=board_id,
            node_type="character",
            x=120,
            y=160,
            data={
                "title": "Chain character",
                "charCountry": "jp",
                "charGender": "female",
                "charVibe": "clean",
            },
            status="idle",
        )
        image_node = manager.store.create_node(
            board_id=board_id,
            node_type="image",
            x=360,
            y=160,
            data={
                "title": "Chain still",
                "prompt": "Premium editorial hero still of the same character in a modern lofi product scene, soft daylight, clean background, controlled highlights.",
            },
            status="idle",
        )
        image_video_node = manager.store.create_node(
            board_id=board_id,
            node_type="video",
            x=620,
            y=180,
            data={
                "title": "Chain motion",
                "prompt": "Animate the still with subtle premium motion, preserve subject framing, maintain product visibility, breathable idle movement.",
            },
            status="idle",
        )
        storyboard_node = manager.store.create_node(
            board_id=board_id,
            node_type="Storyboard",
            x=360,
            y=380,
            data={
                "title": "Chain storyboard",
                "aiBrief": "Cinematic four-shot storyboard of the same character introducing a lofi product scene",
                "storyboardGrid": "2x2",
            },
            status="idle",
        )
        storyboard_video_node = manager.store.create_node(
            board_id=board_id,
            node_type="video",
            x=620,
            y=420,
            data={
                "title": "Storyboard motion",
                "prompt": _build_storyboard_video_prompt(4),
            },
            status="idle",
        )

        manager.store.create_edge(board_id=board_id, source_id=int(character_node["id"]), target_id=int(image_node["id"]))
        manager.store.create_edge(board_id=board_id, source_id=int(image_node["id"]), target_id=int(image_video_node["id"]))
        manager.store.create_edge(board_id=board_id, source_id=int(character_node["id"]), target_id=int(storyboard_node["id"]))
        manager.store.create_edge(board_id=board_id, source_id=int(storyboard_node["id"]), target_id=int(storyboard_video_node["id"]))

        project = manager._ensure_board_project(board_id)
        project_id = str(project.get("flow_project_id") or "").strip()
        if not project_id:
            raise RuntimeError("No board project id returned")
        _log(f"chain-smoke board project ready: {project_id}", log_path=log_path)

        character_body = {
            "node_id": int(character_node["id"]),
            "type": "gen_image",
            "params": {
                "prompt": _build_character_prompt(),
                "project_id": project_id,
                "aspect_ratio": "IMAGE_ASPECT_RATIO_SQUARE",
                "paygate_tier": paygate_tier,
                "variant_count": 1,
                "image_model": "NANO_BANANA_PRO",
            },
        }
        _preflight_or_raise(
            manager,
            str(character_body["type"]),
            dict(character_body["params"]),
            label="character_request",
            log_path=log_path,
            require_dispatch_now=True,
        )
        character_request = manager._create_local_request(character_body)
        character_request_id = int(character_request["id"])
        character_request = _wait_for_request(
            manager,
            character_request_id,
            label="character_request",
            timeout_seconds=float(args.image_timeout_seconds or 900),
            log_path=log_path,
            fail_fast=_cancel_on_runtime_block(manager, character_request_id, "character_request", log_path),
        )
        if str(character_request.get("status") or "") != "done":
            raise RuntimeError(
                f"Character request did not complete successfully: {character_request.get('error') or character_request.get('status')}"
            )
        character_media_id = _first_media_id(character_request)

        image_body = {
            "node_id": int(image_node["id"]),
            "type": "gen_image",
            "params": {
                "prompt": str((image_node.get("data") or {}).get("prompt") or ""),
                "project_id": project_id,
                "aspect_ratio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "paygate_tier": paygate_tier,
                "variant_count": 1,
                "image_model": "NANO_BANANA_PRO",
                "ref_media_ids": [character_media_id],
            },
        }
        _preflight_or_raise(
            manager,
            str(image_body["type"]),
            dict(image_body["params"]),
            label="image_request",
            log_path=log_path,
            require_dispatch_now=True,
        )
        image_request = manager._create_local_request(image_body)
        image_request_id = int(image_request["id"])
        image_request = _wait_for_request(
            manager,
            image_request_id,
            label="image_request",
            timeout_seconds=float(args.image_timeout_seconds or 900),
            log_path=log_path,
            fail_fast=_cancel_on_runtime_block(manager, image_request_id, "image_request", log_path),
        )
        if str(image_request.get("status") or "") != "done":
            raise RuntimeError(
                f"Image request did not complete successfully: {image_request.get('error') or image_request.get('status')}"
            )
        image_media_id = _first_media_id(image_request)

        image_video_body = {
            "node_id": int(image_video_node["id"]),
            "type": "gen_video",
            "params": {
                "prompt": str((image_video_node.get("data") or {}).get("prompt") or ""),
                "project_id": project_id,
                "aspect_ratio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
                "paygate_tier": paygate_tier,
                "video_quality": str(args.video_quality or "lite_relaxed"),
                "download_quality": str(args.video_output_quality or "720p"),
                "start_media_ids": [image_media_id],
            },
        }
        _preflight_or_raise(
            manager,
            str(image_video_body["type"]),
            dict(image_video_body["params"]),
            label="image_video_request",
            log_path=log_path,
            require_dispatch_now=True,
        )
        image_video_request = manager._create_local_request(image_video_body)
        image_video_request_id = int(image_video_request["id"])
        image_video_request = _wait_for_request(
            manager,
            image_video_request_id,
            label="image_video_request",
            timeout_seconds=float(args.video_timeout_seconds or 1800),
            log_path=log_path,
            fail_fast=_cancel_on_runtime_block(manager, image_video_request_id, "image_video_request", log_path),
        )
        if str(image_video_request.get("status") or "") != "done":
            raise RuntimeError(
                f"Image->video request did not complete successfully: {image_video_request.get('error') or image_video_request.get('status')}"
            )
        image_video_media_id = _first_media_id(image_video_request)

        storyboard_prompt = _build_storyboard_prompt(
            str((storyboard_node.get("data") or {}).get("aiBrief") or ""),
            rows=2,
            cols=2,
        )
        storyboard_body = {
            "node_id": int(storyboard_node["id"]),
            "type": "gen_image",
            "params": {
                "prompt": storyboard_prompt,
                "project_id": project_id,
                "aspect_ratio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "paygate_tier": paygate_tier,
                "variant_count": 1,
                "image_model": "NANO_BANANA_PRO",
                "ref_media_ids": [character_media_id],
            },
        }
        _preflight_or_raise(
            manager,
            str(storyboard_body["type"]),
            dict(storyboard_body["params"]),
            label="storyboard_request",
            log_path=log_path,
            require_dispatch_now=True,
        )
        storyboard_request = manager._create_local_request(storyboard_body)
        storyboard_request_id = int(storyboard_request["id"])
        storyboard_request = _wait_for_request(
            manager,
            storyboard_request_id,
            label="storyboard_request",
            timeout_seconds=float(args.image_timeout_seconds or 900),
            log_path=log_path,
            fail_fast=_cancel_on_runtime_block(manager, storyboard_request_id, "storyboard_request", log_path),
        )
        if str(storyboard_request.get("status") or "") != "done":
            raise RuntimeError(
                f"Storyboard request did not complete successfully: {storyboard_request.get('error') or storyboard_request.get('status')}"
            )
        storyboard_media_id = _first_media_id(storyboard_request)

        storyboard_video_body = {
            "node_id": int(storyboard_video_node["id"]),
            "type": "gen_video",
            "params": {
                "prompt": _build_storyboard_video_prompt(4),
                "project_id": project_id,
                "aspect_ratio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
                "paygate_tier": paygate_tier,
                "video_quality": str(args.video_quality or "lite_relaxed"),
                "download_quality": str(args.video_output_quality or "720p"),
                "start_media_ids": [storyboard_media_id],
            },
        }
        _preflight_or_raise(
            manager,
            str(storyboard_video_body["type"]),
            dict(storyboard_video_body["params"]),
            label="storyboard_video_request",
            log_path=log_path,
            require_dispatch_now=True,
        )
        storyboard_video_request = manager._create_local_request(storyboard_video_body)
        storyboard_video_request_id = int(storyboard_video_request["id"])
        storyboard_video_request = _wait_for_request(
            manager,
            storyboard_video_request_id,
            label="storyboard_video_request",
            timeout_seconds=float(args.video_timeout_seconds or 1800),
            log_path=log_path,
            fail_fast=_cancel_on_runtime_block(manager, storyboard_video_request_id, "storyboard_video_request", log_path),
        )
        if str(storyboard_video_request.get("status") or "") != "done":
            raise RuntimeError(
                f"Storyboard->video request did not complete successfully: {storyboard_video_request.get('error') or storyboard_video_request.get('status')}"
            )
        storyboard_video_media_id = _first_media_id(storyboard_video_request)

        board_output_dir = manager._workflow_output_dir_for_board(board_id)
        deadline = time.time() + 30.0
        output_files: list[str] = []
        while time.time() < deadline:
            output_files = _board_output_files(board_output_dir)
            if len(output_files) >= 5:
                break
            time.sleep(2.0)

        node_states = {
            str(node_id): manager.store.get_node(int(node_id))
            for node_id in [
                character_node["id"],
                image_node["id"],
                image_video_node["id"],
                storyboard_node["id"],
                storyboard_video_node["id"],
            ]
        }

        success = True
        report = {
            "success": True,
            "runtime_base_url": runtime_base_url,
            "session_id": session_id,
            "host_url": host_url,
            "smoke_root": str(smoke_root),
            "log_path": str(log_path),
            "input_root": str(input_root),
            "output_root": str(output_root),
            "board_id": board_id,
            "project_id": project_id,
            "paygate_tier": paygate_tier,
            "requests": {
                "character": character_request,
                "image": image_request,
                "image_video": image_video_request,
                "storyboard": storyboard_request,
                "storyboard_video": storyboard_video_request,
            },
            "media_ids": {
                "character": character_media_id,
                "image": image_media_id,
                "image_video": image_video_media_id,
                "storyboard": storyboard_media_id,
                "storyboard_video": storyboard_video_media_id,
            },
            "cached_media": {
                "character": str(manager._find_cached_media_path(character_media_id) or ""),
                "image": str(manager._find_cached_media_path(image_media_id) or ""),
                "image_video": str(manager._find_cached_media_path(image_video_media_id) or ""),
                "storyboard": str(manager._find_cached_media_path(storyboard_media_id) or ""),
                "storyboard_video": str(manager._find_cached_media_path(storyboard_video_media_id) or ""),
            },
            "board_output_dir": str(board_output_dir),
            "output_files": output_files,
            "node_states": node_states,
            "preview_urls": {
                "character": f"{host_url}/media/{character_media_id}",
                "image": f"{host_url}/media/{image_media_id}",
                "image_video": f"{host_url}/media/{image_video_media_id}",
                "storyboard": f"{host_url}/media/{storyboard_media_id}",
                "storyboard_video": f"{host_url}/media/{storyboard_video_media_id}",
            },
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"chain smoke report written to {report_path}", log_path=log_path)

        if args.keep_host:
            _log("keep_host enabled; process will stay alive for browser smoke", log_path=log_path)
            while True:
                time.sleep(1.0)
        return report
    except Exception as exc:
        report = {
            "success": False,
            "runtime_base_url": runtime_base_url,
            "session_id": session_id,
            "smoke_root": str(smoke_root),
            "log_path": str(log_path),
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"chain smoke failed: {exc}", log_path=log_path)
        return report
    finally:
        if not args.keep_host:
            try:
                manager.stop()
            except Exception:
                pass
            controller.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real executable-chain workflow smoke against the local exact backend.")
    parser.add_argument("--runtime-base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--paygate-tier", default="")
    parser.add_argument("--smoke-root", default="")
    parser.add_argument("--report-path", default="")
    parser.add_argument("--board-name", default="Workflow Chain Smoke")
    parser.add_argument("--video-quality", default="lite_relaxed")
    parser.add_argument("--video-output-quality", default="720p")
    parser.add_argument("--image-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--video-timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--keep-host", action="store_true")
    args = parser.parse_args()

    report = _run_chain_smoke(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
