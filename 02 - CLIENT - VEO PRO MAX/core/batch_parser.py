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
import logging
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("core.batch_parser")

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
        - Text with embedded JSON: strips non-JSON lines before/after array
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
            except Exception as e:
                log.debug(f"[BatchParser] JSON parse attempt 1 failed: {e}")
        
        # Embedded JSON detection: look for real JSON starts in the text
        # Skip non-JSON [tag] patterns like [tấm], [CONT] — look for [{ or {" 
        json_start = -1
        for m in re.finditer(r'\[\s*\{|\{\s*"', stripped):
            json_start = m.start()
            break
        
        if json_start > 0:  # JSON found but NOT at start (already tried above)
            json_candidate = stripped[json_start:]
            try:
                result = self.parse_json_text(json_candidate)
                if result:
                    return result
            except Exception as e:
                log.debug(f"[BatchParser] JSON parse attempt 2 (embedded) failed: {e}")
        
        # ── Fallback safety: detect multi-line JSON that may have been
        # split into lines but still looks like a JSON array ──
        # Heuristic: if many lines start with JSON structural chars and
        # the text has balanced braces, re-join and try JSON one more time.
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) >= 3:
            json_structural = sum(
                1 for ln in lines
                if ln and ln[0] in '{[}]"' or ln.startswith('"')
            )
            # If >60% of lines look like JSON fragments, try re-joining
            if json_structural / len(lines) > 0.6:
                rejoined = '\n'.join(lines)
                try:
                    result = self.parse_json_text(rejoined)
                    if result:
                        log.info(
                            f"[BatchParser] JSON recovered via re-join: "
                            f"{len(result)} scenes from {len(lines)} lines"
                        )
                        return result
                except Exception as e:
                    log.debug(f"[BatchParser] JSON re-join attempt failed: {e}")
        
        # Default: line-by-line plain text
        prompts = []
        for line_num, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            prompt = self._parse_line(line, line_num)
            prompts.append(prompt)
        
        return prompts
    
    @staticmethod
    def _sanitize_json_text(text: str) -> str:
        """Clean raw text so json.loads() can parse it.
        
        Handles edge cases:
        1. Markdown fences: ```json ... ``` → strip fences
        2. Non-JSON prefix: '[tấm] [{...}]' → strip before first [{ or {"
        3. Concatenated arrays: '[{...}][{...}]' → merge into single array
        4. Labeled concat: 'Label:\n[{...}]\nLabel:\n[{...}]' → extract & merge all arrays
        5. Bare objects: '{...}, {...}' without [] → wrap in []
        6. Trailing comma: [{...},] → remove comma before ]
        """
        text = text.strip()
        
        # ── Case 0: Strip markdown code fences ──
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'```\s*$', '', text)
            text = text.strip()
        
        # ── Case 0.3: Auto-repair unclosed JSON string values ──
        # Common AI copy-paste defect: closing " missing at end of value.
        # Pattern: `: "some text<NEWLINE>    },` → `: "some text"<NEWLINE>    },`
        # Matches a line that has `: "...` (key-value pair), ends with a non-"
        # character, and is followed by a line that starts with }, or }]
        text = re.sub(
            r'(:\s*"[^"\n]{10,})(\n\s*\}[,\]\s])',
            r'\1"\2',
            text,
        )

        
        # ── Case 0.5: Auto-close truncated JSON ──
        # Common with AI copy-paste: missing ] or } at end.
        # Count unbalanced brackets OUTSIDE of strings, then append closers.
        _in_str = False
        _esc = False
        _brk = 0   # [ / ] balance
        _brc = 0   # { / } balance
        for _ch in text:
            if _esc:
                _esc = False
                continue
            if _ch == '\\' and _in_str:
                _esc = True
                continue
            if _ch == '"':
                _in_str = not _in_str
                continue
            if _in_str:
                continue
            if _ch == '[':
                _brk += 1
            elif _ch == ']':
                _brk -= 1
            elif _ch == '{':
                _brc += 1
            elif _ch == '}':
                _brc -= 1
        
        if _brc > 0 or _brk > 0:
            # Remove trailing comma before auto-closing (common: }, ← missing next obj)
            text = text.rstrip()
            if text.endswith(','):
                text = text[:-1]
            text += '}' * _brc + ']' * _brk
            log.debug(
                f"[BatchParser] Auto-closed truncated JSON: "
                f"+{_brc}x'}}' +{_brk}x']'"
            )

        
        # ── Case 1: Strip non-JSON prefix (e.g. "[tấm] ", "Tình huống 2:\n")
        # Find the first real JSON start: [{ or {" 
        m = re.search(r'\[\s*\{|\{\s*"', text)
        if m and m.start() > 0:
            text = text[m.start():]
        
        # ── Case 1.5: Strip [tag] patterns inside JSON objects ──
        # Handles: {[tấm] "scene_number": 1} → {"scene_number": 1}
        # Pattern: [word] where word contains no quotes/colons/braces
        # Avoids stripping actual JSON array values like [1, 2, 3]
        text = re.sub(r'\[([^\[\]":{}\d][^\[\]":{}]{0,49})\](?=\s*["{,}\]])', '', text)
        
        # ── Case 2+3: Concatenated arrays → merge
        # First try simple whitespace-only concat: "]  ["
        if re.search(r'\]\s*\[', text):
            text = re.sub(r'\]\s*\[', ', ', text, count=0)
            text = text.strip()
            if not text.startswith('['):
                text = '[' + text
            if not text.endswith(']'):
                text = text + ']'
        
        # ── Case 4: Labeled concat — text between arrays
        # "Label:\n[{...}]\nLabel:\n[{...}]" → extract all [...] fragments and merge
        # Only triggers if json.loads would fail on current text
        try:
            json.loads(text)
        except (json.JSONDecodeError, ValueError):
            # Extract all JSON array fragments [...] from the text
            array_fragments = re.findall(r'\[([^\[\]]*(?:\{[^}]*\}[^\[\]]*)*)\]', text)
            if len(array_fragments) >= 2:
                # Merge all fragments into one array
                merged = ', '.join(f.strip().strip(',') for f in array_fragments if f.strip())
                if merged:
                    text = '[' + merged + ']'
        
        # ── Case 5: Bare objects "{...}, {...}" without [] wrapper
        text_stripped = text.strip()
        if text_stripped.startswith('{') and not text_stripped.startswith('['):
            if re.search(r'\}\s*,\s*\{', text_stripped):
                text = '[' + text_stripped + ']'
        
        # ── Case 5.5: Stray non-JSON characters between structural tokens ──
        # Handles AI copy-paste artifacts:
        #   {2"key" → {"key"       (stray digit after {)
        #   ,4"key" → ,"key"       (stray digit after ,)
        #   ,;"key" → ,"key"       (stray semicolon)
        #   : 5,"key" → :,"key"    (stray before ,)
        # Safe: only removes non-whitespace chars between {, and the next "
        text = re.sub(r'(?<=[{,])\s*[^"\s{}\[\]:,]+\s*(?=")', ' ', text)
        # Replace semicolons ONLY between structural JSON tokens (not inside strings)
        # Pattern: after a value-end (", digit, }, ]) + ; + before next key (")
        text = re.sub(r'(?<=["\d}\]])\s*;\s*(?=")', ', ', text)
        # Also handle ;{ patterns (between objects)
        text = re.sub(r'(?<=[}\]])\s*;\s*(?=[{\[])', ', ', text)
        # Clean up double commas that might result from above
        text = re.sub(r',\s*,', ',', text)
        
        # ── Case 6: Trailing comma before ] or } → remove
        text = re.sub(r',\s*\]', ']', text)
        text = re.sub(r',\s*\}', '}', text)
        
        # ── Case 7: Last resort — extract individual {...} objects by brace depth ──
        # Handles malformed AI output: broken arrays, duplicate [, stray text between objects.
        # Only triggers if json.loads still fails after all above sanitization.
        try:
            json.loads(text)
        except (json.JSONDecodeError, ValueError):
            objects = []
            depth = 0
            start = -1
            in_string = False
            escape_next = False
            for idx, ch in enumerate(text):
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == '{':
                    if depth == 0:
                        start = idx
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0 and start >= 0:
                        fragment = text[start:idx + 1]
                        try:
                            json.loads(fragment)  # validate
                            objects.append(fragment)
                        except (json.JSONDecodeError, ValueError):
                            # Try deeper sanitization on this fragment
                            frag = re.sub(r'(?<=[{,])\s*[^"\s{}\[\]:,]+\s*(?=")', ' ', fragment)
                            frag = re.sub(r'(?<=["\d}\]])\s*;\s*(?=")', ', ', frag)
                            frag = re.sub(r',\s*,', ',', frag)
                            frag = re.sub(r',\s*([}\]])', r'\1', frag)
                            try:
                                json.loads(frag)
                                objects.append(frag)
                            except (json.JSONDecodeError, ValueError):
                                pass
                        start = -1
            if objects:
                text = '[' + ', '.join(objects) + ']'
        
        return text
    
    def parse_json_text(self, text: str) -> List[ParsedPrompt]:
        """Parse JSON scene(s) into ParsedPrompt(s).
        
        Supports:
        - Single object: {...} → 1 prompt
        - Array: [{...}, {...}, ...] → N prompts (each scene = 1 prompt)
        - Concatenated arrays: [{...}][{...}] → merged
        - Bare objects: {...}, {...} → wrapped in []
        - Non-JSON prefix: [tag] [{...}] → prefix stripped
        
        Required field per scene: prompt_en (the actual VEO prompt)
        Optional fields: duration ("5s" or "8s" or int), scene_number,
                        description_vi, narration_vi, and any extra metadata.
        """
        text = self._sanitize_json_text(text)
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
            # Support common key names: prompt_en, prompt, prompt_text, text
            prompt_text = (
                scene.get('prompt_en', '')
                or scene.get('prompt', '')
                or scene.get('prompt_text', '')
                or scene.get('text', '')
            )
            if not prompt_text:
                continue
            
            # Parse duration: "8s" → 8, "5s" → 5, or plain int
            duration = self._parse_duration(scene.get('duration'))
            
            # Collect metadata (all non-prompt, non-duration fields)
            metadata = {}
            for key in ('description_vi', 'narration_vi', 'style', 'negative',
                        'setting_chosen', 'type', 'instruments'):
                if key in scene and scene[key]:
                    val = scene[key]
                    metadata[key] = str(val) if not isinstance(val, list) else ', '.join(str(v) for v in val)
            
            # ── Extract image references ──
            # Supports: "image": "path" (single) or "images": ["p1", "p2"] (array)
            image_tags = []
            raw_images = []
            
            # Collect from both "image" and "images" fields
            single_img = scene.get('image', '') or ''
            if isinstance(single_img, str) and single_img.strip():
                raw_images.append(single_img.strip())
            
            multi_imgs = scene.get('images', [])
            if isinstance(multi_imgs, list):
                for img_val in multi_imgs:
                    if isinstance(img_val, str) and img_val.strip():
                        raw_images.append(img_val.strip())
            elif isinstance(multi_imgs, str) and multi_imgs.strip():
                raw_images.append(multi_imgs.strip())
            
            # Process each image: auto-import to ImageLibrary if valid file path
            for img_path_str in raw_images:
                img_path = Path(img_path_str)
                if img_path.is_file():
                    # Valid file → import to ImageLibrary
                    tag_name = img_path.stem.lower()  # filename without ext as tag
                    try:
                        from services.image_library import get_image_library
                        lib = get_image_library()
                        lib.update_or_add_image(
                            str(img_path), tags=[tag_name],
                            category="All", copy_to_library=True,
                        )
                        image_tags.append(tag_name)
                        log.info(
                            f"[BatchParser] Auto-imported [{tag_name}] "
                            f"← {img_path.name}"
                        )
                    except Exception as e:
                        log.warning(f"[BatchParser] ImageLibrary import failed: {e}")
                        image_tags.append(tag_name)
                else:
                    # Not a file → treat as tag name (might resolve later)
                    image_tags.append(img_path_str.strip().strip('[]'))
            
            prompts.append(ParsedPrompt(
                text=json.dumps(scene, ensure_ascii=False),  # Full JSON for display
                line_number=i + 1,
                images=image_tags,
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
