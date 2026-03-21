"""
VEO Pro Max - Manifest Manager

Writes/reads `.veo_manifest.json` alongside output videos.
Enables portable project data: move folder → IDs travel with files.

Architecture ref: ENGINE_PIPELINE_ARCHITECTURE.md
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

log = logging.getLogger(__name__)

MANIFEST_FILENAME = ".veo_manifest.json"
MANIFEST_VERSION = 1


class ManifestManager:
    """Manage per-project .veo_manifest.json files.
    
    Manifest lives in: output_folder/project_name/.veo_manifest.json
    All paths inside manifest are RELATIVE to manifest's parent dir.
    
    Usage:
        mm = ManifestManager()
        mm.save_task_to_manifest(task)       # after download/upscale
        data = mm.load_manifest(path)         # for import
    """
    
    # ── Path Helpers ──────────────────────────────────────────────
    
    @staticmethod
    def to_relative(abs_path: str, base_dir: str) -> str:
        """Convert absolute path to relative (for serialization).
        
        Skips HTTP URLs. Returns original string if not under base_dir.
        """
        if not abs_path or not base_dir:
            return abs_path or ""
        if abs_path.startswith(("http://", "https://")):
            return abs_path
        try:
            rel = Path(abs_path).relative_to(base_dir)
            return str(rel)
        except ValueError:
            return abs_path
    
    @staticmethod
    def to_absolute(rel_path: str, base_dir: str) -> str:
        """Convert relative path to absolute (for deserialization).
        
        Skips HTTP URLs. If rel_path is already absolute, returns as-is.
        """
        if not rel_path or not base_dir:
            return rel_path or ""
        if rel_path.startswith(("http://", "https://")):
            return rel_path
        p = Path(rel_path)
        if p.is_absolute():
            return rel_path
        return str(Path(base_dir) / rel_path)
    
    # ── Manifest Dir ──────────────────────────────────────────────
    
    @staticmethod
    def _get_manifest_dir(task) -> Optional[Path]:
        """Get the manifest directory for a task: output_folder/project_name."""
        output_folder = getattr(task, 'output_folder', '')
        if not output_folder:
            return None
        project_name = getattr(task, 'project_name', '') or "Untitled"
        return Path(output_folder) / project_name
    
    # ── Save ──────────────────────────────────────────────────────
    
    def save_task_to_manifest(self, task) -> bool:
        """Save/update a task's data in the project manifest.
        
        Creates manifest if it doesn't exist, or updates existing entry
        for this task_id (append or replace).
        
        Args:
            task: Task dataclass instance (must have output_folder set)
            
        Returns:
            True if saved successfully
        """
        manifest_dir = self._get_manifest_dir(task)
        if not manifest_dir:
            log.debug("[Manifest] No output_folder on task, skipping")
            return False
        
        manifest_path = manifest_dir / MANIFEST_FILENAME
        base_dir = str(manifest_dir)
        
        # Load existing manifest or create new
        manifest = self._load_or_create(manifest_path, task)
        
        # Build entry for this task
        entry = self._task_to_entry(task, base_dir)
        
        # Replace existing entry for same task_id, or append
        prompts = manifest.get("prompts", [])
        replaced = False
        for i, p in enumerate(prompts):
            if p.get("task_id") == task.id:
                prompts[i] = entry
                replaced = True
                break
        if not replaced:
            prompts.append(entry)
        manifest["prompts"] = prompts
        manifest["updated_at"] = datetime.now().isoformat()
        
        # Atomic write
        try:
            manifest_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = manifest_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(manifest, indent=2, default=str, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(manifest_path)
            log.info(f"[Manifest] Saved → {manifest_path}")
            return True
        except Exception as e:
            log.error(f"[Manifest] Save failed: {e}")
            return False
    
    def _load_or_create(self, manifest_path: Path, task) -> dict:
        """Load existing manifest or create skeleton."""
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if data.get("version") == MANIFEST_VERSION:
                    return data
            except Exception:
                log.warning(f"[Manifest] Corrupt file, creating new: {manifest_path}")
        
        return {
            "version": MANIFEST_VERSION,
            "project_name": getattr(task, 'project_name', '') or "Untitled",
            "project_id": getattr(task, 'project_id', ''),
            "account": getattr(task, 'assigned_account', ''),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "prompts": [],
        }
    
    def _task_to_entry(self, task, base_dir: str) -> dict:
        """Convert Task + VideoOutputInfo to manifest entry.
        
        All file paths stored RELATIVE to base_dir (manifest's parent).
        """
        videos = []
        for vo in getattr(task, 'video_outputs', []):
            videos.append({
                "index": vo.index,
                "operation_name": vo.operation_name,
                "scene_id": vo.scene_id,
                "media_id": vo.media_id,
                "file_720p": self.to_relative(vo.file_720p, base_dir),
                "file_upscaled": self.to_relative(vo.file_upscaled, base_dir),
                "quality": vo.quality,
                "upscale_status": vo.upscale_status,
                "upscale_error": vo.upscale_error,
            })
        
        return {
            "task_id": task.id,
            "prompt": task.prompt,
            "workflow_type": task.workflow_type,
            "model": task.model,
            "aspect_ratio": task.aspect_ratio,
            "duration_seconds": task.duration_seconds,
            "output_count": task.output_count,
            "seed": task.seed,
            "download_quality": task.download_quality,
            "operation_name": task.operation_name,
            "operation_names": list(getattr(task, 'operation_names', [])),
            "scene_ids": list(getattr(task, 'scene_ids', [])),
            "upscale_media_ids": list(getattr(task, 'upscale_media_ids', [])),
            "output_uris": list(task.output_uris),
            "state": task.state.value if hasattr(task.state, 'value') else str(task.state),
            "videos": videos,
        }
    
    # ── Load ──────────────────────────────────────────────────────
    
    def load_manifest(self, manifest_path: Path) -> Optional[dict]:
        """Load a manifest from disk.
        
        Returns:
            Parsed manifest dict with paths resolved to ABSOLUTE
            (relative to manifest's parent dir), or None on failure.
        """
        if not manifest_path.exists():
            return None
        
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if data.get("version") != MANIFEST_VERSION:
                log.warning(f"[Manifest] Version mismatch: {data.get('version')}")
                return None
            
            base_dir = str(manifest_path.parent)
            
            # Resolve relative paths → absolute
            for prompt_entry in data.get("prompts", []):
                for v in prompt_entry.get("videos", []):
                    v["file_720p"] = self.to_absolute(v.get("file_720p", ""), base_dir)
                    v["file_upscaled"] = self.to_absolute(v.get("file_upscaled", ""), base_dir)
            
            log.info(f"[Manifest] Loaded: {manifest_path} ({len(data.get('prompts', []))} prompts)")
            return data
        except Exception as e:
            log.error(f"[Manifest] Load failed: {e}")
            return None
    
    def find_manifest(self, folder: Path) -> Optional[Path]:
        """Find .veo_manifest.json in a folder (non-recursive)."""
        candidate = folder / MANIFEST_FILENAME
        return candidate if candidate.exists() else None
