import logging

log = logging.getLogger(__name__)
"""
VEO Pro Max - Session Manager

Handles persistence of:
- Tab state (prompts + sidebar settings)
- Queue state (task groups + individual tasks)
- Cache management (stats, cleanup)
"""

import json
import os
import shutil
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any


SESSION_VERSION = 1


class SessionManager:
    """Manages session persistence and cache for VEO Pro Max."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        self._base_dir = base_dir or (Path.home() / ".veoauto")
        self._session_file = self._base_dir / "session.json"
        self._cache_dir = self._base_dir / "cache"
        
        # Ensure dirs exist
        self._base_dir.mkdir(parents=True, exist_ok=True)
    
    # ── Save / Load ─────────────────────────────────────────────
    
    def save_session(self, data: dict) -> bool:
        """Save full session state to disk.
        
        Args:
            data: {"tabs": {...}, "queue": {...}}
        
        Returns:
            True if saved successfully
        """
        try:
            payload = {
                "version": SESSION_VERSION,
                "saved_at": datetime.now().isoformat(),
                "tabs": data.get("tabs", {}),
                "queue": data.get("queue", {}),
            }
            
            # Atomic write: write to temp then rename
            tmp = self._session_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=self._json_default)
            
            # Replace old file
            if self._session_file.exists():
                self._session_file.unlink()
            tmp.rename(self._session_file)
            
            log.info(f"[Session] Saved to {self._session_file}")
            return True
        except Exception as e:
            log.error(f"[Session] Save failed: {e}")
            return False
    
    def load_session(self) -> dict:
        """Load session from disk.
        
        Returns:
            Session data dict, or empty dict if not found/corrupt
        """
        if not self._session_file.exists():
            log.info("[Session] No session file found")
            return {}
        
        try:
            with open(self._session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if data.get("version") != SESSION_VERSION:
                log.info(f"[Session] Version mismatch: {data.get('version')} != {SESSION_VERSION}")
                return {}
            
            saved_at = data.get("saved_at", "unknown")
            log.info(f"[Session] Loaded from {saved_at}")
            return data
        except Exception as e:
            log.error(f"[Session] Load failed: {e}")
            return {}
    
    def delete_session(self) -> bool:
        """Delete session file."""
        try:
            if self._session_file.exists():
                self._session_file.unlink()
            return True
        except Exception:
            return False
    
    # ── Path Conversion ───────────────────────────────────────────
    
    CACHE_DIR = str(Path.home() / ".veoauto" / "cache")
    
    @staticmethod
    def _to_relative(abs_path: str, base_dir: str) -> str:
        """Convert absolute path to relative for portable serialization.
        Skips HTTP URLs — only converts local file paths."""
        if not abs_path or not base_dir:
            return abs_path or ""
        if abs_path.startswith(("http://", "https://")):
            return abs_path  # URL, not a local path
        try:
            return str(Path(abs_path).relative_to(base_dir))
        except ValueError:
            return abs_path  # not under base_dir — keep absolute
    
    @staticmethod
    def _to_absolute(rel_path: str, base_dir: str) -> str:
        """Convert relative path back to absolute on load.
        Skips HTTP URLs — only converts local file paths."""
        if not rel_path or not base_dir:
            return rel_path or ""
        if rel_path.startswith(("http://", "https://")):
            return rel_path  # URL, not a local path
        p = Path(rel_path)
        if p.is_absolute():
            return rel_path
        return str(Path(base_dir) / rel_path)
    
    # ── Queue Serialization ─────────────────────────────────────
    
    def serialize_queue(self, groups: dict) -> list:
        """Serialize TaskGroup objects to JSON-safe dicts.
        
        Video paths are stored RELATIVE to output_folder/project_name.
        Cache paths (thumbnails, frames) are stored RELATIVE to CACHE_DIR.
        This makes the journal portable when folders are moved.
        
        Args:
            groups: Dict[str, TaskGroup] from dispatcher
        
        Returns:
            List of serializable group dicts
        """
        cache_dir = self.CACHE_DIR
        result = []
        for gid, group in groups.items():
            g_data = {
                "id": group.id,
                "name": group.name,
                "created_at": group.created_at.isoformat() if hasattr(group.created_at, 'isoformat') else str(group.created_at),
                "tasks": []
            }
            for task in group.tasks:
                # Video base dir: output_folder/project_name
                output_folder = getattr(task, 'output_folder', '')
                project_name = getattr(task, 'project_name', '') or "Untitled"
                video_base = str(Path(output_folder) / project_name) if output_folder else ""
                
                # Convert output_uris to relative
                rel_output_uris = [
                    self._to_relative(u, video_base) if u else ""
                    for u in task.output_uris
                ]
                
                # Convert thumbnail_paths to relative (cache-based)
                rel_thumb_paths = [
                    self._to_relative(p, cache_dir) if p else ""
                    for p in getattr(task, 'thumbnail_paths', [])
                ]
                
                # Convert continuation_frame_local_path to relative (cache-based)
                frame_local = getattr(task, 'continuation_frame_local_path', None)
                rel_frame = self._to_relative(frame_local, cache_dir) if frame_local else None
                
                t_data = {
                    "id": task.id,
                    "workflow_type": task.workflow_type,
                    "prompt": task.prompt,
                    "aspect_ratio": task.aspect_ratio,
                    "model": task.model,
                    "output_count": task.output_count,
                    "duration_seconds": task.duration_seconds,
                    "seed": task.seed,
                    "image_uris": list(task.image_uris),
                    "image_paths": list(getattr(task, 'image_paths', [])),
                    "parent_task_id": task.parent_task_id,
                    "continuation_frame_uri": getattr(task, 'continuation_frame_uri', None),
                    "continuation_frame_local_path": rel_frame,
                    "required_account": getattr(task, 'required_account', None),
                    "prompt_index": getattr(task, 'prompt_index', 0),
                    "extract_point_ms": task.extract_point_ms,
                    "download_quality": task.download_quality,
                    "stage": task.stage.value if hasattr(task.stage, 'value') else "init",
                    "state": task.state.value if hasattr(task.state, 'value') else str(task.state),
                    "progress": task.progress,
                    "error": task.error,
                    "retry_attempts": task.retry_attempts,
                    "chain_retry_count": getattr(task, 'chain_retry_count', 0),
                    "operation_name": task.operation_name,
                    "operation_names": list(getattr(task, 'operation_names', [])),
                    "scene_ids": list(getattr(task, 'scene_ids', [])),
                    "output_uris": rel_output_uris,
                    "thumbnail_paths": rel_thumb_paths,
                    "assigned_account": task.assigned_account,
                    "project_id": task.project_id,
                    "output_folder": output_folder,
                    "project_name": project_name,
                    "upscale_status": getattr(task, 'upscale_status', ''),
                    "upscale_media_ids": list(getattr(task, 'upscale_media_ids', [])),
                    "upscale_error": getattr(task, 'upscale_error', ''),
                    "created_at": task.created_at.isoformat() if hasattr(task.created_at, 'isoformat') else None,
                    "completed_at": task.completed_at.isoformat() if hasattr(task.completed_at, 'isoformat') else None,
                    "video_outputs": [
                        {
                            "index": vo.index,
                            "operation_name": vo.operation_name,
                            "scene_id": vo.scene_id,
                            "media_id": vo.media_id,
                            "file_720p": self._to_relative(vo.file_720p, video_base),
                            "file_upscaled": self._to_relative(vo.file_upscaled, video_base),
                            "thumbnail_path": self._to_relative(vo.thumbnail_path, cache_dir),
                            "quality": vo.quality,
                            "upscale_status": vo.upscale_status,
                            "upscale_error": vo.upscale_error,
                        }
                        for vo in (task.video_outputs if hasattr(task, 'video_outputs') else [])
                    ],
                    "replace_target": list(task.replace_target) if getattr(task, 'replace_target', None) else None,
                }
                g_data["tasks"].append(t_data)
            result.append(g_data)
        return result
    
    # ── Cache Management ────────────────────────────────────────
    
    @property
    def cache_dir(self) -> Path:
        return self._cache_dir
    
    def get_cache_stats(self, cache_folder: Optional[str] = None) -> dict:
        """Get cache folder statistics.
        
        Returns:
            {"size_mb": float, "file_count": int, "oldest_days": int}
        """
        folder = Path(cache_folder) if cache_folder else self._cache_dir
        if not folder.exists():
            return {"size_mb": 0.0, "file_count": 0, "oldest_days": 0}
        
        total_size = 0
        file_count = 0
        oldest_time = time.time()
        
        for root, dirs, files in os.walk(folder):
            for f in files:
                fp = Path(root) / f
                try:
                    stat = fp.stat()
                    total_size += stat.st_size
                    file_count += 1
                    if stat.st_mtime < oldest_time:
                        oldest_time = stat.st_mtime
                except OSError:
                    pass
        
        oldest_days = int((time.time() - oldest_time) / 86400) if file_count > 0 else 0
        
        return {
            "size_mb": round(total_size / (1024 * 1024), 2),
            "file_count": file_count,
            "oldest_days": oldest_days,
        }
    
    def clean_cache(self, max_age_days: int = 7, cache_folder: Optional[str] = None) -> dict:
        """Delete cache files older than max_age_days.
        
        Returns:
            {"deleted_count": int, "freed_mb": float}
        """
        folder = Path(cache_folder) if cache_folder else self._cache_dir
        if not folder.exists():
            return {"deleted_count": 0, "freed_mb": 0.0}
        
        cutoff = time.time() - (max_age_days * 86400)
        deleted = 0
        freed = 0
        
        for root, dirs, files in os.walk(folder):
            for f in files:
                fp = Path(root) / f
                try:
                    stat = fp.stat()
                    if stat.st_mtime < cutoff:
                        freed += stat.st_size
                        fp.unlink()
                        deleted += 1
                except OSError:
                    pass
        
        # Clean empty dirs
        self._clean_empty_dirs(folder)
        
        return {
            "deleted_count": deleted,
            "freed_mb": round(freed / (1024 * 1024), 2),
        }
    
    def clear_cache(self, cache_folder: Optional[str] = None) -> dict:
        """Delete cache files, preserving thumbnails.
        
        Thumbnails are lightweight and referenced by task.video_outputs.
        Deleting them would break Queue tab display with no auto-regeneration.
        
        Returns:
            {"deleted_count": int, "freed_mb": float}
        """
        folder = Path(cache_folder) if cache_folder else self._cache_dir
        if not folder.exists():
            return {"deleted_count": 0, "freed_mb": 0.0}
        
        # Count stats EXCLUDING thumbnails
        deleted_count = 0
        freed_bytes = 0
        
        try:
            for item in list(folder.iterdir()):
                # Skip thumbnails directory
                if item.is_dir() and item.name == "thumbnails":
                    continue
                
                if item.is_file():
                    freed_bytes += item.stat().st_size
                    item.unlink()
                    deleted_count += 1
                elif item.is_dir():
                    # Count files in subdirectory before deleting
                    for f in item.rglob("*"):
                        if f.is_file():
                            freed_bytes += f.stat().st_size
                            deleted_count += 1
                    shutil.rmtree(item)
        except OSError as e:
            log.error(f"[Session] Clear cache failed: {e}")
        
        return {
            "deleted_count": deleted_count,
            "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        }

    
    # ── Helpers ──────────────────────────────────────────────────
    
    def _clean_empty_dirs(self, root: Path):
        """Remove empty subdirectories."""
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            dp = Path(dirpath)
            if dp != root and not any(dp.iterdir()):
                try:
                    dp.rmdir()
                except OSError:
                    pass
    
    @staticmethod
    def _json_default(obj):
        """JSON serializer for datetime and other non-standard types."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, 'value'):  # Enum
            return obj.value
        if hasattr(obj, '__dict__'):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
