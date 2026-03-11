"""
VEO Pro Max - Batch Parser

Reference: SESSION_05_BACKEND_FEATURES.md
Role: Parse prompts from TXT/CSV/JSON files

Supported formats:
- TXT: One prompt per line
- CSV: Column-based (prompt, image, continuation)
- JSON: Array of scene objects or single scene object
  Each scene: {prompt_en, duration, scene_number, description_vi, narration_vi}
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import json
from pathlib import Path
import re
import csv
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class ParsedPrompt:
    """A parsed prompt with metadata."""
    text: str
    line_number: int
    images: List[str] = field(default_factory=list)      # Image tags found
    is_continuation: bool = False                        # Is this a continuation?
    continuation_source: Optional[str] = None            # Tag for continuation source
    raw_line: str = ""                                   # Original line
    duration: Optional[int] = None                       # Per-scene duration (seconds)
    scene_number: Optional[int] = None                   # Scene ordering
    metadata: Dict[str, str] = field(default_factory=dict)  # Extra fields (description_vi, narration_vi, etc.)
    
    @property
    def has_images(self) -> bool:
        return len(self.images) > 0
    
    @property
    def has_duration(self) -> bool:
        return self.duration is not None


class BatchParser:
    """Parse prompts from batch files (TXT, CSV).
    
    Features:
    - Parse TXT files (one prompt per line)
    - Parse CSV files (column-based)
    - Image tag extraction: [tag], {tag}, @tag
    - Continuation detection: >>, →, CONT:, [CONT]
    """
    
    # Image tag patterns
    IMAGE_TAG_PATTERNS = [
        r'\[([^\]]+)\]',      # [tag]
        r'\{([^}]+)\}',       # {tag}
        r'@(\S+)',            # @tag
    ]
    
    # Continuation markers
    CONTINUATION_MARKERS = [
        '>>',
        '→',
        'CONT:',
        '[CONT]',
        '-->',
        '==>',
    ]
    
    def __init__(self):
        # Compile regex patterns
        self._image_patterns = [re.compile(p) for p in self.IMAGE_TAG_PATTERNS]
    
    def parse_txt(self, file_path: str) -> List[ParsedPrompt]:
        """Parse a TXT file.
        
        Format: One prompt per line
        Empty lines are skipped
        Lines starting with # are comments
        
        Args:
            file_path: Path to TXT file
        
        Returns:
            List of ParsedPrompt
        """
        path = Path(file_path)
        if not path.exists():
            return []
        
        prompts = []
        
        with open(path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                prompt = self._parse_line(line, line_num)
                prompts.append(prompt)
        
        return prompts
    
    def parse_csv(
        self,
        file_path: str,
        prompt_column: str = "prompt",
        image_column: Optional[str] = "image",
        continuation_column: Optional[str] = "continuation",
    ) -> List[ParsedPrompt]:
        """Parse a CSV file.
        
        Args:
            file_path: Path to CSV file
            prompt_column: Column name for prompts
            image_column: Optional column for image paths/tags
            continuation_column: Optional column for continuation flag
        
        Returns:
            List of ParsedPrompt
        """
        path = Path(file_path)
        if not path.exists():
            return []
        
        prompts = []
        
        with open(path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            
            for line_num, row in enumerate(reader, 2):  # Start at 2 (header is 1)
                text = row.get(prompt_column, "").strip()
                if not text:
                    continue
                
                prompt = self._parse_line(text, line_num)
                
                # Override with CSV columns if present
                if image_column and image_column in row:
                    image_val = row[image_column].strip()
                    if image_val:
                        prompt.images = [img.strip() for img in image_val.split(',')]
                
                if continuation_column and continuation_column in row:
                    cont_val = row[continuation_column].strip().lower()
                    prompt.is_continuation = cont_val in ('true', '1', 'yes', 'cont')
                
                prompts.append(prompt)
        
        return prompts
    
    def _parse_line(self, line: str, line_number: int) -> ParsedPrompt:
        """Parse a single line into a ParsedPrompt."""
        text = line
        images = []
        is_continuation = False
        continuation_source = None
        
        # Check for continuation markers
        for marker in self.CONTINUATION_MARKERS:
            if text.startswith(marker):
                is_continuation = True
                text = text[len(marker):].strip()
                break
            elif marker in text:
                # Format: "marker tag: prompt" or "prompt marker tag"
                parts = text.split(marker, 1)
                if len(parts) == 2:
                    # Check which side has the prompt
                    left, right = parts[0].strip(), parts[1].strip()
                    if left and right:
                        # "prev_tag >> prompt" format
                        is_continuation = True
                        continuation_source = left
                        text = right
                        break
        
        # Extract image tags
        for pattern in self._image_patterns:
            matches = pattern.findall(text)
            images.extend(matches)
            # Remove tags from text
            text = pattern.sub('', text)
        
        # Clean up text
        text = ' '.join(text.split())  # Normalize whitespace
        
        return ParsedPrompt(
            text=text,
            line_number=line_number,
            images=images,
            is_continuation=is_continuation,
            continuation_source=continuation_source,
            raw_line=line,
        )
    
    def parse_text(self, text: str) -> List[ParsedPrompt]:
        """Parse prompts from a string.
        
        Auto-detects format:
        - JSON array: [{...}, {...}] → N prompts with metadata
        - Single JSON object: {...} → one prompt with metadata
        - Plain text: one prompt per line
        
        Args:
            text: Multi-line text with prompts
        
        Returns:
            List of ParsedPrompt
        """
        stripped = text.strip()
        
        # Auto-detect JSON: starts with { or [
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                result = self.parse_json_text(stripped)
                if result:
                    return result
            except Exception:
                pass  # Fall through to line-by-line parsing
        
        # Default: line-by-line plain text
        prompts = []
        for line_num, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            prompt = self._parse_line(line, line_num)
            prompts.append(prompt)
        
        return prompts
    
    def parse_json_text(self, text: str) -> List[ParsedPrompt]:
        """Parse JSON scene(s) into ParsedPrompt(s).
        
        Supports:
        - Single object: {...} → 1 prompt
        - Array: [{...}, {...}, ...] → N prompts (each scene = 1 prompt)
        
        Required field per scene: prompt_en (the actual VEO prompt)
        Optional fields: duration ("5s" or "8s" or int), scene_number,
                        description_vi, narration_vi, and any extra metadata.
        """
        data = json.loads(text)
        
        # Normalize: single object → list of one
        if isinstance(data, dict):
            data = [data]
        
        if not isinstance(data, list):
            return []
        
        prompts = []
        for i, scene in enumerate(data):
            if not isinstance(scene, dict):
                continue
            
            # Extract prompt text (required)
            prompt_text = scene.get('prompt_en', '') or scene.get('prompt', '')
            if not prompt_text:
                continue
            
            # Parse duration: "8s" → 8, "5s" → 5, or plain int
            duration = self._parse_duration(scene.get('duration'))
            
            # Collect metadata (all non-prompt, non-duration fields)
            metadata = {}
            for key in ('description_vi', 'narration_vi', 'style', 'negative'):
                if key in scene and scene[key]:
                    metadata[key] = str(scene[key])
            
            prompts.append(ParsedPrompt(
                text=json.dumps(scene, ensure_ascii=False),  # Full JSON for display
                line_number=i + 1,
                duration=duration,
                scene_number=scene.get('scene_number', i + 1),
                metadata=metadata,
                raw_line=prompt_text,  # prompt_en for API submission
            ))
        
        return prompts
    
    @staticmethod
    def _parse_duration(raw) -> Optional[int]:
        """Parse duration value: '8s' → 8, '5s' → 5, int → int."""
        if raw is None:
            return None
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            try:
                return int(raw.strip().rstrip('sS'))
            except ValueError:
                return None
        return None
    
    def parse_json_file(self, file_path: str) -> List[ParsedPrompt]:
        """Parse a JSON file with scene prompts."""
        path = Path(file_path)
        if not path.exists():
            return []
        text = path.read_text(encoding='utf-8')
        return self.parse_json_text(text)
    
    @staticmethod
    def detect_file_format(file_path: str) -> str:
        """Detect file format from extension.
        
        Returns: 'txt', 'csv', 'json', or 'unknown'
        """
        ext = Path(file_path).suffix.lower()
        if ext == '.txt':
            return 'txt'
        elif ext == '.csv':
            return 'csv'
        elif ext == '.json':
            return 'json'
        else:
            return 'unknown'
    
    def parse_file(self, file_path: str) -> List[ParsedPrompt]:
        """Auto-detect format and parse file."""
        fmt = self.detect_file_format(file_path)
        
        if fmt == 'txt':
            return self.parse_txt(file_path)
        elif fmt == 'csv':
            return self.parse_csv(file_path)
        elif fmt == 'json':
            return self.parse_json_file(file_path)
        else:
            # Try as txt
            return self.parse_txt(file_path)
