"""
VEO Pro Max - Import Validator

Reference: SESSION_05_BACKEND_FEATURES.md
Role: Validate imported prompts and images
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set
from enum import Enum
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.batch_parser import ParsedPrompt, BatchParser


class IssueSeverity(str, Enum):
    """Severity levels for validation issues."""
    ERROR = "error"      # Blocks import
    WARNING = "warning"  # User should review
    INFO = "info"        # Informational only


@dataclass
class ValidationIssue:
    """A single validation issue."""
    line_number: int
    message: str
    severity: IssueSeverity
    field: str = "prompt"        # What field has the issue
    suggestion: Optional[str] = None
    
    def __str__(self):
        return f"[{self.severity.value.upper()}] Line {self.line_number}: {self.message}"


@dataclass
class ValidationResult:
    """Result of validation."""
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    prompts: List[ParsedPrompt] = field(default_factory=list)
    
    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)
    
    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)


class ImportValidator:
    """Validate imported prompts before processing.
    
    Features:
    - Prompt length validation (max 1000 chars)
    - Image tag existence check
    - Continuation logic validation
    - Duplicate detection
    """
    
    MAX_PROMPT_LENGTH = 1000
    MIN_PROMPT_LENGTH = 3
    
    def __init__(self, image_library: Optional[Dict[str, str]] = None):
        """
        Args:
            image_library: Dict mapping tag names to file paths
        """
        self._image_library = image_library or {}
    
    def set_image_library(self, library: Dict[str, str]):
        """Set image library for tag validation."""
        self._image_library = library
    
    def validate_prompts(self, prompts: List[ParsedPrompt]) -> ValidationResult:
        """Validate a list of parsed prompts.
        
        Args:
            prompts: List of ParsedPrompt to validate
        
        Returns:
            ValidationResult
        """
        issues = []
        valid_prompts = []
        seen_texts: Set[str] = set()
        
        for i, prompt in enumerate(prompts):
            prompt_issues = self._validate_single(prompt, i, prompts, seen_texts)
            issues.extend(prompt_issues)
            
            # Track for duplicate detection
            seen_texts.add(prompt.text.lower()[:50])
            
            # Add to valid list if no errors
            has_error = any(
                issue.severity == IssueSeverity.ERROR
                for issue in prompt_issues
            )
            if not has_error:
                valid_prompts.append(prompt)
        
        has_blocking_errors = any(
            i.severity == IssueSeverity.ERROR for i in issues
        )
        
        return ValidationResult(
            valid=not has_blocking_errors,
            issues=issues,
            prompts=valid_prompts,
        )
    
    def _validate_single(
        self,
        prompt: ParsedPrompt,
        index: int,
        all_prompts: List[ParsedPrompt],
        seen_texts: Set[str],
    ) -> List[ValidationIssue]:
        """Validate a single prompt."""
        issues = []
        
        # 1. Length validations
        if len(prompt.text) > self.MAX_PROMPT_LENGTH:
            issues.append(ValidationIssue(
                line_number=prompt.line_number,
                message=f"Prompt exceeds maximum length ({len(prompt.text)}/{self.MAX_PROMPT_LENGTH} chars)",
                severity=IssueSeverity.ERROR,
                suggestion=f"Truncate to {self.MAX_PROMPT_LENGTH} characters",
            ))
        
        if len(prompt.text) < self.MIN_PROMPT_LENGTH:
            issues.append(ValidationIssue(
                line_number=prompt.line_number,
                message=f"Prompt is too short ({len(prompt.text)} chars)",
                severity=IssueSeverity.WARNING,
                suggestion="Add more descriptive text",
            ))
        
        # 2. Continuation logic
        if prompt.is_continuation and index == 0:
            issues.append(ValidationIssue(
                line_number=prompt.line_number,
                message="First prompt cannot be a continuation",
                severity=IssueSeverity.ERROR,
                suggestion="Remove continuation marker from first line",
            ))
        
        if prompt.is_continuation and prompt.continuation_source:
            # Check if source exists
            source_exists = any(
                p.text.lower().startswith(prompt.continuation_source.lower())
                or prompt.continuation_source in p.images
                for p in all_prompts[:index]
            )
            if not source_exists:
                issues.append(ValidationIssue(
                    line_number=prompt.line_number,
                    message=f"Continuation source '{prompt.continuation_source}' not found",
                    severity=IssueSeverity.WARNING,
                    suggestion="Check that the referenced source exists earlier in the list",
                ))
        
        # 3. Image tag validation
        for tag in prompt.images:
            if self._image_library and tag not in self._image_library:
                issues.append(ValidationIssue(
                    line_number=prompt.line_number,
                    message=f"Image tag '{tag}' not found in library",
                    severity=IssueSeverity.ERROR,
                    field="image",
                    suggestion="Add image to library or remove tag",
                ))
        
        # 4. Duplicate detection
        normalized = prompt.text.lower()[:50]
        if normalized in seen_texts:
            issues.append(ValidationIssue(
                line_number=prompt.line_number,
                message="Duplicate or very similar prompt detected",
                severity=IssueSeverity.WARNING,
                suggestion="Review for duplicates",
            ))
        
        # 5. Character validation (optional warnings)
        if '\n' in prompt.raw_line:
            issues.append(ValidationIssue(
                line_number=prompt.line_number,
                message="Prompt contains line breaks",
                severity=IssueSeverity.INFO,
                suggestion="Line breaks will be converted to spaces",
            ))
        
        return issues
    
    def validate_file(self, file_path: str) -> ValidationResult:
        """Validate prompts from a file.
        
        Args:
            file_path: Path to TXT or CSV file
        
        Returns:
            ValidationResult
        """
        parser = BatchParser()
        prompts = parser.parse_file(file_path)
        
        if not prompts:
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue(
                    line_number=0,
                    message="No valid prompts found in file",
                    severity=IssueSeverity.ERROR,
                )],
            )
        
        return self.validate_prompts(prompts)
    
    def quick_validate(self, text: str) -> List[str]:
        """Quick validation of a single prompt text.
        
        Returns list of error/warning messages.
        """
        messages = []
        
        if len(text) > self.MAX_PROMPT_LENGTH:
            messages.append(f"Too long ({len(text)}/{self.MAX_PROMPT_LENGTH})")
        
        if len(text) < self.MIN_PROMPT_LENGTH:
            messages.append("Too short")
        
        return messages
