"""
VEO Pro Max - Image Library Service

Reference: 02_IMAGE_LIBRARY_SYSTEM.md
Manages image library with tags for use in I2V, I2I, and R2V workflows.
"""

import json
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
import uuid


@dataclass
class LibraryImage:
    """Represents an image in the library."""
    id: str
    filename: str
    path: str
    tags: List[str]
    category: str = "All"
    notes: str = ""
    
    @classmethod
    def create(cls, path: str, tags: List[str], category: str = "All") -> "LibraryImage":
        """Create a new LibraryImage from a file path."""
        return cls(
            id=str(uuid.uuid4()),
            filename=Path(path).name,
            path=path,
            tags=tags,
            category=category,
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
        
        # Normalize tags
        normalized_tags = [t.lower().strip() for t in tags]
        
        image = LibraryImage.create(final_path, normalized_tags, category)
        self._images.append(image)
        self._save_index()
        self._notify_change()
        
        return image
    
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
    
    def resolve_tag(self, tag: str) -> Optional[LibraryImage]:
        """
        Resolve a tag to an image.
        
        Args:
            tag: The tag to resolve (without brackets)
        
        Returns:
            LibraryImage if found, None otherwise
        """
        normalized = tag.lower().strip()
        for image in self._images:
            if normalized in image.tags:
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
            image.tags = [t.lower().strip() for t in tags]
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


# Singleton instance
_library_instance: Optional[ImageLibrary] = None


def get_image_library() -> ImageLibrary:
    """Get the singleton ImageLibrary instance."""
    global _library_instance
    if _library_instance is None:
        _library_instance = ImageLibrary()
    return _library_instance
