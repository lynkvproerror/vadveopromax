"""
VEO Pro Max - Image Library Service

Reference: 02_IMAGE_LIBRARY_SYSTEM.md
Manages image library with tags for use in I2V, I2I, and R2V workflows.
Includes per-account upload cache to avoid redundant API uploads.
"""

import json
import shutil
import hashlib
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
import uuid

log = logging.getLogger(__name__)


@dataclass
class LibraryImage:
    """Represents an image in the library.
    
    Fields:
        media_ids: Per-account upload cache {email: mediaGenerationId}
        content_hash: MD5 hash for dedup across paths
    """
    id: str
    filename: str
    path: str
    tags: List[str]
    category: str = "All"
    notes: str = ""
    content_hash: str = ""
    media_ids: Dict[str, str] = field(default_factory=dict)  # email → mediaId
    
    @classmethod
    def create(cls, path: str, tags: List[str], category: str = "All",
               content_hash: str = "") -> "LibraryImage":
        """Create a new LibraryImage from a file path."""
        return cls(
            id=str(uuid.uuid4()),
            filename=Path(path).name,
            path=path,
            tags=tags,
            category=category,
            content_hash=content_hash,
        )


class ImageLibrary:
    """
    Manages image library with tag-based retrieval.
    
    Features:
    - Add/Remove images with tags
    - Resolve [tag] references from prompts
    - Category organization
    - Persistence to JSON
    
    Usage:
        library = ImageLibrary()
        library.add_image("path/to/hero.png", tags=["hero", "character"])
        image = library.resolve_tag("hero")  # Returns LibraryImage or None
    """
    
    DEFAULT_CATEGORIES = ["All", "Characters", "Backgrounds", "Objects", "Styles"]
    
    def __init__(self, library_path: Optional[str] = None):
        """
        Initialize image library.
        
        Args:
            library_path: Path to library directory. Defaults to user's Documents/VEO Pro Max/Library
        """
        if library_path:
            self._library_path = Path(library_path)
        else:
            # Default to user's Documents
            self._library_path = Path.home() / "Documents" / "VEO Pro Max" / "Library"
        
        self._library_path.mkdir(parents=True, exist_ok=True)
        self._index_file = self._library_path / "index.json"
        self._images: List[LibraryImage] = []
        self._categories: List[str] = self.DEFAULT_CATEGORIES.copy()
        self._on_change_callbacks: List[Callable] = []
        
        self._load_index()
    
    def on_change(self, callback: Callable):
        """Register a callback to be notified when library changes.
        
        Callbacks are called with no arguments after add/remove/update.
        Used by PromptTable to auto-refresh unresolved image tags.
        """
        if callback not in self._on_change_callbacks:
            self._on_change_callbacks.append(callback)
    
    def _notify_change(self):
        """Notify all registered callbacks that library contents changed."""
        for cb in self._on_change_callbacks:
            try:
                cb()
            except Exception:
                pass
    
    def _load_index(self):
        """Load library index from JSON."""
        if self._index_file.exists():
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._images = [
                        LibraryImage(**img) for img in data.get("images", [])
                    ]
                    self._categories = data.get("categories", self.DEFAULT_CATEGORIES)
            except Exception as e:
                print(f"[ImageLibrary] Error loading index: {e}")
                self._images = []
    
    def _save_index(self):
        """Save library index to JSON."""
        data = {
            "images": [asdict(img) for img in self._images],
            "categories": self._categories,
        }
        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ImageLibrary] Error saving index: {e}")
    
    # === Public API ===
    
    # Formats Google API supports natively (no conversion needed)
    _SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp'}
    
    def add_image(
        self,
        source_path: str,
        tags: List[str],
        category: str = "All",
        copy_to_library: bool = True,
    ) -> LibraryImage:
        """
        Add an image to the library.
        
        Unsupported formats (BMP, TIFF, GIF, etc.) are auto-converted
        to PNG at import time for Google API compatibility.
        
        Args:
            source_path: Path to the source image file
            tags: List of tags for this image
            category: Category to organize the image
            copy_to_library: If True, copy the image to library folder
        
        Returns:
            The created LibraryImage
        """
        source = Path(source_path)
        needs_conversion = source.suffix.lower() not in self._SUPPORTED_FORMATS
        
        if copy_to_library:
            # Copy to library folder
            dest_folder = self._library_path / category
            dest_folder.mkdir(parents=True, exist_ok=True)
            
            if needs_conversion:
                # Convert unsupported format → PNG (lossless)
                dest_path = dest_folder / f"{source.stem}.png"
            else:
                dest_path = dest_folder / source.name
            
            # Handle duplicate names
            counter = 1
            while dest_path.exists():
                dest_path = dest_folder / f"{source.stem}_{counter}{dest_path.suffix}"
                counter += 1
            
            if needs_conversion:
                self._convert_to_png(str(source), str(dest_path))
            else:
                shutil.copy2(source, dest_path)
            final_path = str(dest_path)
        else:
            final_path = str(source)
        
        # Normalize tags — strip brackets if user named file like [tag].jpg
        normalized_tags = [t.lower().strip().strip('[]') for t in tags]
        
        # Compute content hash for dedup
        c_hash = self._compute_hash(final_path)
        
        image = LibraryImage.create(final_path, normalized_tags, category,
                                    content_hash=c_hash)
        self._images.append(image)
        self._save_index()
        self._notify_change()
        
        return image
    
    def update_or_add_image(
        self,
        source_path: str,
        tags: List[str],
        category: str = "All",
        copy_to_library: bool = True,
    ) -> tuple:
        """Add image, or UPDATE existing if tag already exists.
        
        When a tag collision is detected:
        - Updates the existing image's path to the new file
        - Clears all cached media_ids (old UUIDs are invalid for new image)
        - Updates content_hash
        - Triggers re-upload on next pre-upload cycle
        
        Returns:
            (LibraryImage, was_updated: bool)
        """
        normalized_tags = [t.lower().strip().strip('[]') for t in tags]
        
        # Check for tag collision
        for tag in normalized_tags:
            existing = self.resolve_tag(tag)
            if existing:
                old_path = existing.path
                new_path = str(Path(source_path))
                
                # Update path
                existing.path = new_path
                existing.filename = Path(new_path).name
                
                # Clear stale media_ids — image content changed, old UUIDs invalid
                if existing.media_ids:
                    log.info(
                        f"[ImageLibrary] Tag [{tag}] updated: "
                        f"cleared {len(existing.media_ids)} cached mediaId(s) "
                        f"(old={Path(old_path).name} → new={Path(new_path).name})"
                    )
                    existing.media_ids.clear()
                else:
                    log.info(
                        f"[ImageLibrary] Tag [{tag}] path updated: "
                        f"{Path(old_path).name} → {Path(new_path).name}"
                    )
                
                # Update content hash
                existing.content_hash = self._compute_hash(new_path)
                
                # Merge any new tags not already present
                for t in normalized_tags:
                    if t not in existing.tags:
                        existing.tags.append(t)
                
                self._save_index()
                self._notify_change()
                return (existing, True)
        
        # No collision — normal add
        image = self.add_image(source_path, tags, category, copy_to_library)
        return (image, False)
    
    @staticmethod
    def _convert_to_png(source_path: str, dest_path: str):
        """Convert any image format to PNG (lossless) via PIL."""
        try:
            from PIL import Image
            with Image.open(source_path) as img:
                # Handle animated GIFs: take first frame
                if hasattr(img, 'n_frames') and img.n_frames > 1:
                    img.seek(0)
                # Convert palette/RGBA modes
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGBA')
                img.save(dest_path, 'PNG')
        except ImportError:
            # PIL not available — fallback to raw copy
            shutil.copy2(source_path, dest_path)
    
    def remove_image(self, image_id: str, delete_file: bool = False):
        """
        Remove an image from the library.
        
        Args:
            image_id: The image ID to remove
            delete_file: If True, also delete the file
        """
        image = next((img for img in self._images if img.id == image_id), None)
        if image:
            if delete_file:
                try:
                    Path(image.path).unlink()
                except Exception as e:
                    print(f"[ImageLibrary] Error deleting file: {e}")
            
            self._images.remove(image)
            self._save_index()
            self._notify_change()
    
    def remove_all(self, delete_files: bool = False) -> int:
        """
        Remove ALL images from the library.
        
        Args:
            delete_files: If True, also delete image files from disk
            
        Returns:
            Number of images removed
        """
        count = len(self._images)
        if delete_files:
            for img in self._images:
                try:
                    Path(img.path).unlink()
                except Exception:
                    pass
        self._images.clear()
        self._save_index()
        self._notify_change()
        return count
    
    def remove_by_tags(self, tags: list, delete_files: bool = False) -> int:
        """
        Remove images that match ANY of the given tags.
        
        Args:
            tags: List of tag names to match (case-insensitive)
            delete_files: If True, also delete image files from disk
            
        Returns:
            Number of images removed
        """
        normalized = {t.lower().strip().strip('[]') for t in tags}
        to_remove = []
        for img in self._images:
            if any(t.strip('[]') in normalized for t in img.tags):
                to_remove.append(img)
        
        for img in to_remove:
            if delete_files:
                try:
                    Path(img.path).unlink()
                except Exception:
                    pass
            self._images.remove(img)
        
        if to_remove:
            self._save_index()
            self._notify_change()
        return len(to_remove)
    
    def resolve_tag(self, tag: str) -> Optional[LibraryImage]:
        """
        Resolve a tag to an image.
        
        Args:
            tag: The tag to resolve (without brackets)
        
        Returns:
            LibraryImage if found, None otherwise
        """
        normalized = tag.lower().strip().strip('[]')
        for image in self._images:
            # Match against stored tags, also stripping brackets for backward compat
            for stored_tag in image.tags:
                if stored_tag.strip('[]') == normalized:
                    return image
        return None
    
    def resolve_tags_in_prompt(self, prompt: str) -> Dict[str, Optional[LibraryImage]]:
        """
        Extract and resolve all [tag] references in a prompt.
        
        Args:
            prompt: The prompt text with [tag] references
        
        Returns:
            Dict mapping tag to LibraryImage (or None if not found)
        """
        import re
        tags = re.findall(r'\[([^\]]+)\]', prompt)
        return {tag: self.resolve_tag(tag) for tag in tags}
    
    def get_images(self, category: Optional[str] = None) -> List[LibraryImage]:
        """
        Get all images, optionally filtered by category.
        
        Args:
            category: Filter by category (None = all images)
        """
        if category is None or category == "All":
            return self._images.copy()
        return [img for img in self._images if img.category == category]
    
    def get_images_by_tag(self, tag: str) -> List[LibraryImage]:
        """Get all images with a specific tag."""
        normalized = tag.lower().strip()
        return [img for img in self._images if normalized in img.tags]
    
    def add_category(self, category: str):
        """Add a new category."""
        if category not in self._categories:
            self._categories.append(category)
            self._save_index()
    
    def get_categories(self) -> List[str]:
        """Get all categories."""
        return self._categories.copy()
    
    def update_image_tags(self, image_id: str, tags: List[str]):
        """Update tags for an image."""
        image = next((img for img in self._images if img.id == image_id), None)
        if image:
            image.tags = [t.lower().strip().strip('[]') for t in tags]
            self._save_index()
            self._notify_change()
    
    def update_image_category(self, image_id: str, category: str):
        """Update category for an image."""
        image = next((img for img in self._images if img.id == image_id), None)
        if image:
            image.category = category
            self._save_index()
    
    def get_all_tags(self) -> List[str]:
        """Get all unique tags in the library."""
        all_tags = set()
        for image in self._images:
            all_tags.update(image.tags)
        return sorted(list(all_tags))
    
    def search(self, query: str) -> List[LibraryImage]:
        """
        Search images by tag or filename.
        
        Args:
            query: Search query
        
        Returns:
            List of matching images
        """
        query = query.lower().strip()
        results = []
        for image in self._images:
            if query in image.filename.lower():
                results.append(image)
            elif any(query in tag for tag in image.tags):
                results.append(image)
        return results
    
    @property
    def library_path(self) -> Path:
        """Get the library path."""
        return self._library_path
    
    @property
    def image_count(self) -> int:
        """Get total image count."""
        return len(self._images)
    
    # === Upload Cache API ===
    
    @staticmethod
    def _compute_hash(path: str) -> str:
        """Compute MD5 hash of file for content dedup."""
        try:
            h = hashlib.md5()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""
    
    def get_media_id(self, path: str, account_email: str) -> Optional[str]:
        """Get cached mediaId for a specific image + account.
        
        Lookup strategy:
          1. Exact path match
          2. Content hash match (same image, different path)
        
        Returns:
            mediaGenerationId if cached, None otherwise
        """
        # 1. Exact path match
        for img in self._images:
            if img.path == path and account_email in img.media_ids:
                return img.media_ids[account_email]
        
        # 2. Content hash match
        target_hash = self._compute_hash(path)
        if target_hash:
            for img in self._images:
                if img.content_hash == target_hash and account_email in img.media_ids:
                    return img.media_ids[account_email]
        
        return None
    
    def set_media_id(self, path: str, account_email: str, media_id: str):
        """Store uploaded mediaId for a specific image + account.
        
        Also matches by content hash so the same image under different
        paths shares the upload result.
        """
        matched = False
        target_hash = self._compute_hash(path)
        
        for img in self._images:
            if img.path == path or (target_hash and img.content_hash == target_hash):
                img.media_ids[account_email] = media_id
                matched = True
        
        if matched:
            self._save_index()
    
    def get_pending_uploads(self, account_email: str) -> List[LibraryImage]:
        """Get library images that haven't been uploaded for this account."""
        return [
            img for img in self._images
            if account_email not in img.media_ids
            and Path(img.path).exists()
        ]
    
    def get_all_pending_accounts(self, account_emails: List[str]) -> Dict[str, List[LibraryImage]]:
        """Get pending uploads grouped by account.
        
        Returns:
            {email: [LibraryImage, ...]} for accounts with pending uploads
        """
        result = {}
        for email in account_emails:
            pending = self.get_pending_uploads(email)
            if pending:
                result[email] = pending
        return result
    
    async def trigger_pre_upload(
        self,
        accounts: list,
        api_client,
    ) -> Dict[str, int]:
        """Pre-upload all library images to all accounts in parallel.
        
        Multi-account: each account uploads concurrently.
        Within each account: images upload sequentially (rate limit safety).
        
        Args:
            accounts: List of AccountManager instances
            api_client: VeoAPIClient instance
        
        Returns:
            {email: count_uploaded} summary
        """
        from core.media_handler import MediaHandler
        
        results = {}
        
        async def _upload_for_account(account):
            """Upload all pending images for one account."""
            email = account.email
            pending = self.get_pending_uploads(email)
            if not pending:
                return
            
            log.info(f"[ImageLibrary] Pre-uploading {len(pending)} image(s) for {email}")
            uploaded = 0
            
            for img in pending:
                try:
                    result = MediaHandler.image_to_base64(img.path)
                    if not result:
                        log.warning(f"[ImageLibrary] Failed to encode: {img.filename}")
                        continue
                    
                    img_b64, mime_type = result
                    # Fix 401: always use ensure_valid_token for fresh token
                    token = await account.ensure_valid_token()
                    if not token:
                        log.warning(f"[ImageLibrary] No token for {email}, stopping pre-upload")
                        break
                    
                    resp = await api_client.upload_image(
                        access_token=token,
                        recaptcha_token="",
                        image_base64=img_b64,
                        mime_type=mime_type,
                        file_name=img.filename,
                        account_headers=account.get_api_headers(),
                    )
                    
                    if resp.success:
                        # Multi-format mediaId extraction (API changed 2026-03)
                        media_id = ""
                        # Format 1: Old {mediaGenerationId: {mediaGenerationId: "..."}}
                        mgid = resp.data.get("mediaGenerationId")
                        if mgid:
                            if isinstance(mgid, dict):
                                media_id = mgid.get("mediaGenerationId", "")
                            elif isinstance(mgid, str):
                                media_id = mgid
                        # Format 2: New {media: {name: "uuid", ...}, workflow: ...}
                        if not media_id:
                            media = resp.data.get("media")
                            if isinstance(media, dict):
                                media_id = media.get("name", "") or media.get("mediaGenerationId", "") or media.get("mediaId", "")
                            elif isinstance(media, list) and media:
                                first = media[0]
                                if isinstance(first, dict):
                                    media_id = first.get("name", "") or first.get("mediaGenerationId", "") or first.get("mediaId", "")
                        
                        if media_id:
                            self.set_media_id(img.path, email, media_id)
                            uploaded += 1
                            log.info(f"[ImageLibrary] ✅ {img.filename} → {media_id[:30]}... ({email})")
                        else:
                            import json as _json
                            try:
                                dump = _json.dumps(resp.data, default=str, ensure_ascii=False)[:500]
                            except Exception:
                                dump = str(list(resp.data.keys()))
                            log.warning(f"[ImageLibrary] Upload OK but no mediaId: {img.filename} ({email}): {dump}")
                    else:
                        log.warning(f"[ImageLibrary] Upload failed: {img.filename} ({email}): {resp.error}")
                    
                    # Small delay between uploads for rate limiting
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    log.warning(f"[ImageLibrary] Pre-upload error: {img.filename} ({email}): {e}")
            
            results[email] = uploaded
            log.info(f"[ImageLibrary] Pre-upload done for {email}: {uploaded}/{len(pending)}")
        
        # Launch all accounts in parallel
        if accounts:
            await asyncio.gather(
                *[_upload_for_account(acc) for acc in accounts],
                return_exceptions=True,
            )
        
        return results
    
    def clear_media_ids(self, account_email: Optional[str] = None):
        """Clear cached mediaIds.
        
        Args:
            account_email: If provided, clear only for this account.
                          If None, clear ALL cached mediaIds.
        """
        for img in self._images:
            if account_email:
                img.media_ids.pop(account_email, None)
            else:
                img.media_ids.clear()
        self._save_index()


# Singleton instance
_library_instance: Optional[ImageLibrary] = None


def get_image_library() -> ImageLibrary:
    """Get the singleton ImageLibrary instance."""
    global _library_instance
    if _library_instance is None:
        _library_instance = ImageLibrary()
    return _library_instance
