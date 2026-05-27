from __future__ import annotations

import argparse
import json
import secrets
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workflow.manager import WorkflowManager


class RuntimeShim:
    def __init__(self, base_url: str):
        self.base_url = str(base_url or "").rstrip("/")

    def is_healthy(self, timeout: float = 1.0) -> bool:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=timeout)
            return bool(response.ok)
        except Exception:
            return False


class SmokeController:
    def __init__(self, base_url: str, session_id: str, *, ttl_seconds: int = 20, source_name: str = "workflow_live_smoke"):
        self._flowkit_runtime = RuntimeShim(base_url)
        self._flowkit_app_session_id = str(session_id or "").strip() or secrets.token_hex(16)
        self._workflow_dispatch_active_supplier = None
        self._ttl_seconds = max(5, min(int(ttl_seconds or 20), 120))
        self._source_name = str(source_name or "").strip() or "workflow_live_smoke"
        self._stop_event = threading.Event()
        self._heartbeat_lock = threading.Lock()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="workflow-live-smoke-heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def set_workflow_dispatch_active_supplier(self, supplier) -> None:
        self._workflow_dispatch_active_supplier = supplier if callable(supplier) else None

    def _workflow_dispatch_active(self) -> bool:
        supplier = self._workflow_dispatch_active_supplier
        if not callable(supplier):
            return False
        try:
            return bool(supplier())
        except Exception:
            return False

    def _send_heartbeat(self) -> None:
        if not self._flowkit_runtime.is_healthy(timeout=0.8):
            return
        payload = {
            "session_id": self._flowkit_app_session_id,
            "ttl_seconds": self._ttl_seconds,
            "dispatch_enabled": bool(self._workflow_dispatch_active()),
            "metadata": {
                "app_running": True,
                "is_processing": False,
                "workflow_dispatch_active": bool(self._workflow_dispatch_active()),
                "queue_count": 0,
                "manual_stop_requested": False,
                "source": self._source_name,
            },
        }
        requests.post(
            f"{self._flowkit_runtime.base_url}/api/app-control/heartbeat",
            json=payload,
            timeout=1.5,
        )

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self._heartbeat_lock:
                    self._send_heartbeat()
            except Exception:
                pass
            self._stop_event.wait(4.0)

    def _schedule_flowkit_app_control_heartbeat(self, *, force: bool = False) -> None:
        if not force and self._heartbeat_lock.locked():
            return

        def _worker() -> None:
            try:
                with self._heartbeat_lock:
                    self._send_heartbeat()
            except Exception:
                pass

        threading.Thread(target=_worker, name="workflow-live-smoke-heartbeat-force", daemon=True).start()

    def shutdown(self) -> None:
        self._stop_event.set()
        self._heartbeat_thread.join(timeout=2.0)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _log(message: str, *, log_path: Path) -> None:
    line = f"[{_now()}] {message}"
    print(line, flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _preflight_or_raise(
    manager: WorkflowManager,
    local_type: str,
    params: dict[str, Any],
    *,
    label: str,
    log_path: Path,
    require_dispatch_now: bool,
) -> dict[str, Any]:
    snapshot = manager._workflow_request_preflight(
        local_type,
        dict(params or {}),
        require_dispatch_now=require_dispatch_now,
    )
    if bool(snapshot.get("ok")):
        _log(
            (
                f"{label}: preflight ok "
                f"(family={snapshot.get('family')} "
                f"capacity={json.dumps(snapshot.get('capacity') or {}, ensure_ascii=False)})"
            ),
            log_path=log_path,
        )
        return snapshot
    reason = str(snapshot.get("reason") or "workflow preflight failed").strip()
    reason_code = str(snapshot.get("reason_code") or "preflight_failed").strip()
    _log(
        f"{label}: preflight blocked [{reason_code}] {reason}",
        log_path=log_path,
    )
    raise RuntimeError(f"{label} blocked before dispatch: {reason}")


def _request_block_reason(
    manager: WorkflowManager,
    request_row: dict[str, Any],
    *,
    require_dispatch_now: bool = False,
) -> str | None:
    status = str(request_row.get("status") or "").strip().lower()
    if status not in {"queued", "running"}:
        return None
    result = dict(request_row.get("result") or {})
    warning = str(result.get("active_error_summary") or result.get("active_error") or "").strip()
    if not warning and not require_dispatch_now:
        return None
    preflight = manager._workflow_request_preflight(
        str(request_row.get("type") or "").strip(),
        dict(request_row.get("params") or {}),
        require_dispatch_now=require_dispatch_now,
    )
    if bool(preflight.get("ok")):
        return None
    reason = str(preflight.get("reason") or warning or "").strip()
    return reason or None


def _get_app_control_session(base_url: str) -> str:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/app-control/status", timeout=2.0)
        response.raise_for_status()
        payload = response.json()
        return str(((payload.get("app_control") or {}).get("session_id")) or "").strip()
    except Exception:
        return ""


def _get_paygate_tier(base_url: str) -> str:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/health", timeout=2.0)
        response.raise_for_status()
        payload = response.json()
        sessions = list(payload.get("extension_sessions") or [])
        for row in sessions:
            tier = str(row.get("paygate_tier") or "").strip()
            if tier:
                return tier
    except Exception:
        pass
    return "PAYGATE_TIER_ONE"


def _write_sample_png(path: Path) -> None:
    image = np.zeros((512, 768, 3), dtype=np.uint8)
    image[:, :, 0] = 34
    image[:, :, 1] = 86
    image[:, :, 2] = 168
    cv2.putText(image, "Workflow Smoke", (55, 230), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.putText(image, "Uploaded sample image", (55, 290), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (240, 240, 240), 2, cv2.LINE_AA)
    cv2.imwrite(str(path), image)


def _write_sample_mp4(path: Path) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, 2.0, (432, 768))
    if not writer.isOpened():
        raise RuntimeError("Could not open sample mp4 writer")
    try:
        for index in range(10):
            frame = np.zeros((768, 432, 3), dtype=np.uint8)
            frame[:, :, 0] = 20 + (index * 8)
            frame[:, :, 1] = 80 + (index * 10)
            frame[:, :, 2] = 160
            cv2.putText(frame, "Workflow Smoke Video", (28, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f"Frame {index + 1}", (28, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (245, 245, 245), 2, cv2.LINE_AA)
            cv2.rectangle(frame, (28, 320), (404, 620), (255, 255, 255), 3)
            cv2.circle(frame, (216, 470), 60 + index * 3, (240, 200, 120), 8)
            writer.write(frame)
    finally:
        writer.release()


def _wait_for_request(
    manager: WorkflowManager,
    request_id: int,
    *,
    label: str,
    timeout_seconds: float,
    log_path: Path,
    fail_fast=None,
) -> dict[str, Any]:
    deadline = time.time() + float(timeout_seconds)
    last_status = None
    while time.time() < deadline:
        row = manager._sync_local_request(request_id)
        status = str(row.get("status") or "")
        if status != last_status:
            _log(f"{label}: status={status} result={json.dumps(row.get('result') or {}, ensure_ascii=False)[:400]}", log_path=log_path)
            last_status = status
        if status in {"done", "failed", "canceled"}:
            return row
        if callable(fail_fast):
            reason = fail_fast(row)
            if reason:
                raise RuntimeError(str(reason))
        time.sleep(4.0)
    raise TimeoutError(f"{label} timed out after {timeout_seconds:.0f}s")


def _first_node(detail: dict[str, Any], node_type: str, *, title_contains: str | None = None) -> dict[str, Any]:
    for row in list(detail.get("nodes") or []):
        if str(row.get("type") or "") != node_type:
            continue
        title = str((row.get("data") or {}).get("title") or "")
        if title_contains and title_contains not in title:
            continue
        return row
    raise RuntimeError(f"Could not find node type={node_type!r} title_contains={title_contains!r}")


def _update_node_media(manager: WorkflowManager, node_id: int, *, media_id: str, aspect_ratio: str | None = None) -> None:
    manager.store.update_node(
        node_id,
        {
            "status": "done",
            "data": {
                "mediaId": media_id,
                "mediaIds": [media_id],
                "variantCount": 1,
                "aspectRatio": aspect_ratio,
                "renderedAt": _now(),
            },
        },
    )


def _run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    smoke_root = Path(args.smoke_root).expanduser() if args.smoke_root else Path(tempfile.mkdtemp(prefix="workflow-live-smoke-"))
    smoke_root.mkdir(parents=True, exist_ok=True)
    log_path = smoke_root / "smoke.log"
    report_path = Path(args.report_path).expanduser() if args.report_path else smoke_root / "smoke_report.json"

    runtime_base_url = str(args.runtime_base_url or "http://127.0.0.1:8100").rstrip("/")
    session_id = str(args.session_id or "").strip() or _get_app_control_session(runtime_base_url) or secrets.token_hex(16)
    paygate_tier = str(args.paygate_tier or "").strip() or _get_paygate_tier(runtime_base_url)

    _log(f"runtime={runtime_base_url} session_id={session_id} paygate_tier={paygate_tier}", log_path=log_path)

    controller = SmokeController(runtime_base_url, session_id, ttl_seconds=20)
    manager = WorkflowManager(
        controller,
        app_data_dir=smoke_root / "appdata",
        frontend_dist_dir=REPO_ROOT / "workflow_frontend" / "dist",
    )

    success = False
    try:
        host_url = manager.start()
        _log(f"workflow host started at {host_url}", log_path=log_path)

        if args.serve_existing_root:
            synced_requests = []
            for row in manager.store.list_requests():
                synced_requests.append(manager._sync_local_request(int(row["id"])))
            report = {
                "success": True,
                "mode": "serve-existing-root",
                "runtime_base_url": runtime_base_url,
                "session_id": session_id,
                "host_url": host_url,
                "smoke_root": str(smoke_root),
                "log_path": str(log_path),
                "requests": synced_requests,
                "boards": manager.store.list_boards(),
            }
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            _log(f"existing workflow root served from {smoke_root}", log_path=log_path)
            if args.keep_host:
                _log("keep_host enabled; process will stay alive for browser smoke", log_path=log_path)
                while True:
                    time.sleep(1.0)
            return report

        input_root = smoke_root / "resource_input"
        output_root = smoke_root / "output"
        input_root.mkdir(parents=True, exist_ok=True)
        output_root.mkdir(parents=True, exist_ok=True)

        sample_png = input_root / "sample_image.png"
        sample_mp4 = input_root / "sample_video.mp4"
        _write_sample_png(sample_png)
        _write_sample_mp4(sample_mp4)
        _log(f"sample media created under {input_root}", log_path=log_path)

        manager._set_workflow_resource_input_folder(str(input_root))
        manager._set_workflow_output_folder(str(output_root), apply_existing=False)

        board_detail = manager._bootstrap_demo_board_local(str(args.board_name or "Workflow Smoke Demo"))
        board_id = int((board_detail.get("board") or {}).get("id") or 0)
        if board_id <= 0:
            raise RuntimeError("Demo board bootstrap returned no board id")
        manager.store.patch_ui_state({"active_board_id": board_id})
        _log(f"demo board bootstrapped: board_id={board_id}", log_path=log_path)

        image_node = _first_node(board_detail, "image", title_contains="Hero still")
        video_node = _first_node(board_detail, "video", title_contains="Hero motion")
        uploaded_image_node = manager.store.create_node(
            board_id=board_id,
            node_type="visual_asset",
            x=1240,
            y=40,
            data={"title": "Uploaded image", "prompt": ""},
            status="idle",
        )
        uploaded_video_node = manager.store.create_node(
            board_id=board_id,
            node_type="video",
            x=1240,
            y=280,
            data={"title": "Uploaded clip", "prompt": ""},
            status="idle",
        )

        project = manager._ensure_board_project(board_id)
        project_id = str(project.get("flow_project_id") or "").strip()
        if not project_id:
            raise RuntimeError("No board project id returned")
        _log(f"board project ready: {project_id}", log_path=log_path)

        uploaded_image = manager._upload_file_local(sample_png, project_id=project_id, file_name=sample_png.name, mime="image/png")
        _update_node_media(
            manager,
            int(uploaded_image_node["id"]),
            media_id=str(uploaded_image["media_id"]),
            aspect_ratio=str(uploaded_image.get("aspect_ratio") or ""),
        )
        _log(f"uploaded sample image: media_id={uploaded_image['media_id']}", log_path=log_path)

        uploaded_video = manager._upload_file_local(sample_mp4, project_id=project_id, file_name=sample_mp4.name, mime="video/mp4")
        _update_node_media(
            manager,
            int(uploaded_video_node["id"]),
            media_id=str(uploaded_video["media_id"]),
            aspect_ratio=str(uploaded_video.get("aspect_ratio") or ""),
        )
        _log(f"uploaded sample video: media_id={uploaded_video['media_id']}", log_path=log_path)

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
        image_request = _wait_for_request(
            manager,
            int(image_request["id"]),
            label="image_request",
            timeout_seconds=float(args.image_timeout_seconds or 900),
            log_path=log_path,
            fail_fast=lambda row: _request_block_reason(manager, row),
        )
        if str(image_request.get("status") or "") != "done":
            raise RuntimeError(f"Image request did not complete successfully: {image_request.get('error') or image_request.get('status')}")
        image_media_ids = [
            str(item)
            for item in list((image_request.get("result") or {}).get("media_ids") or [])
            if str(item or "").strip()
        ]
        if not image_media_ids:
            raise RuntimeError("Image request completed without media ids")
        _log(f"generated image media ids: {image_media_ids}", log_path=log_path)

        video_body = {
            "node_id": int(video_node["id"]),
            "type": "gen_video",
            "params": {
                "prompt": str((video_node.get("data") or {}).get("prompt") or ""),
                "project_id": project_id,
                "aspect_ratio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
                "paygate_tier": paygate_tier,
                "video_quality": str(args.video_quality or "lite_relaxed"),
                "download_quality": str(args.video_output_quality or "720p"),
                "start_media_ids": image_media_ids,
            },
        }
        _preflight_or_raise(
            manager,
            str(video_body["type"]),
            dict(video_body["params"]),
            label="video_request",
            log_path=log_path,
            require_dispatch_now=True,
        )
        video_request = manager._create_local_request(video_body)
        video_request = _wait_for_request(
            manager,
            int(video_request["id"]),
            label="video_request",
            timeout_seconds=float(args.video_timeout_seconds or 1800),
            log_path=log_path,
            fail_fast=lambda row: _request_block_reason(manager, row),
        )
        if str(video_request.get("status") or "") != "done":
            raise RuntimeError(f"Video request did not complete successfully: {video_request.get('error') or video_request.get('status')}")
        video_media_ids = [
            str(item)
            for item in list((video_request.get("result") or {}).get("media_ids") or [])
            if str(item or "").strip()
        ]
        if not video_media_ids:
            raise RuntimeError("Video request completed without media ids")
        _log(f"generated video media ids: {video_media_ids}", log_path=log_path)

        board_output_dir = manager._workflow_output_dir_for_board(board_id)
        deadline = time.time() + 30.0
        output_files: list[str] = []
        while time.time() < deadline:
            output_files = [str(path) for path in board_output_dir.rglob("*") if path.is_file()]
            if output_files:
                break
            time.sleep(2.0)
        _log(f"output files found: {len(output_files)}", log_path=log_path)

        preview_video_cache = manager._find_cached_media_path(str(uploaded_video["media_id"]))
        generated_video_cache = manager._find_cached_media_path(video_media_ids[0])
        generated_image_cache = manager._find_cached_media_path(image_media_ids[0])

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
            "uploaded_image": uploaded_image,
            "uploaded_video": uploaded_video,
            "uploaded_preview_media_id": str(uploaded_video["media_id"]),
            "uploaded_preview_cache_path": str(preview_video_cache) if preview_video_cache else None,
            "generated_image_request": image_request,
            "generated_video_request": video_request,
            "generated_image_media_id": image_media_ids[0],
            "generated_video_media_id": video_media_ids[0],
            "generated_image_cache_path": str(generated_image_cache) if generated_image_cache else None,
            "generated_video_cache_path": str(generated_video_cache) if generated_video_cache else None,
            "board_output_dir": str(board_output_dir),
            "output_files": output_files,
            "ui_targets": {
                "uploaded_video_node_id": int(uploaded_video_node["id"]),
                "uploaded_image_node_id": int(uploaded_image_node["id"]),
                "generated_video_node_id": int(video_node["id"]),
                "generated_image_node_id": int(image_node["id"]),
            },
            "preview_urls": {
                "uploaded_video": f"{host_url}/media/{uploaded_video['media_id']}",
                "generated_video": f"{host_url}/media/{video_media_ids[0]}",
                "generated_image": f"{host_url}/media/{image_media_ids[0]}",
            },
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"smoke report written to {report_path}", log_path=log_path)

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
        _log(f"smoke failed: {exc}", log_path=log_path)
        return report
    finally:
        if not args.keep_host:
            try:
                manager.stop()
            except Exception:
                pass
            controller.shutdown()
        elif not success:
            try:
                manager.stop()
            except Exception:
                pass
            controller.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real workflow live smoke against the local exact backend.")
    parser.add_argument("--runtime-base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--paygate-tier", default="")
    parser.add_argument("--smoke-root", default="")
    parser.add_argument("--report-path", default="")
    parser.add_argument("--board-name", default="Workflow Smoke Demo")
    parser.add_argument("--video-quality", default="lite_relaxed")
    parser.add_argument("--video-output-quality", default="720p")
    parser.add_argument("--image-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--video-timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--serve-existing-root", action="store_true")
    parser.add_argument("--keep-host", action="store_true")
    args = parser.parse_args()

    report = _run_smoke(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
