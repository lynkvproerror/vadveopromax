"""VEO Pro Max - Core Package

Core engine modules for VEO automation.
"""

# Session & Auth
from .session import AccountSession, SubscriptionType, PaygateTier
from .auth_manager import AuthManager

# Account Management
from .account_manager import AccountManager
from .multi_account import MultiAccountManager

# Task Management
from .dispatcher import Dispatcher, Task, TaskGroup, TaskState
from .worker import PromptExecutor, Worker, WorkerResult, WorkerState  # Worker = alias
from .project_manager import ProjectManager
from .engine import Engine

# API
from .api_client import VEOApiClient, APIResponse

# Media Processing
from .media_handler import MediaHandler, ImageFormat
from .frame_extractor import FrameExtractor

# Error Handling
from .error_handler import ErrorHandler, ErrorCategory, VEOError, retry_on_error

# Downloads & Upscale
from .download_manager import DownloadManager, DownloadProgress, DownloadResult
from .upscale_handler import UpscaleHandler, UpscaleResult

# Parsing & Validation
from .batch_parser import BatchParser, ParsedPrompt
from .import_validator import ImportValidator, ValidationIssue, ValidationResult, IssueSeverity

# Security
from .security import (
    SecurityManager,
    IntegrityChecker,
    AntiDebug,
    TimeTamperDetector,
    TrialProtection,
    EnvironmentChecker,
    SecurityStatus,
    SecurityCheckResult,
)

# Session Management
from .session_monitor import SessionMonitor, SessionEvent, SessionError
from .refresh_manager import CookieRefreshManager, RefreshRequest, RefreshStatus

# Controllers
from .app_controller import AppController, AppState
from .event_manager import EventManager, EventType, Event, get_event_manager, emit_event
from .queue_controller import QueueController, QueueItemView
from .settings_controller import SettingsController, LicenseController

# Browser Automation (still referenced — pending refactor)
from .browser_manager import BrowserManager, BrowserSession, BrowserConfig, BrowserState
from .token_extractor import TokenExtractor, ExtractedTokens, extract_tokens, extract_tokens_sync

__all__ = [
    # Session
    "AccountSession",
    "SubscriptionType",
    "PaygateTier",
    
    # Auth
    "AuthManager",
    
    # Account Management
    "AccountManager",
    "MultiAccountManager",
    
    # Task Management
    "Dispatcher",
    "Task",
    "TaskGroup",
    "TaskState",
    "PromptExecutor",
    "Worker",  # backward compat alias
    "WorkerResult",
    "WorkerState",
    "ProjectManager",
    "Engine",
    
    # API
    "VEOApiClient",
    "APIResponse",
    
    # Media
    "MediaHandler",
    "ImageFormat",
    "FrameExtractor",
    
    # Error Handling
    "ErrorHandler",
    "ErrorCategory",
    "VEOError",
    "retry_on_error",
    
    # Downloads
    "DownloadManager",
    "DownloadProgress",
    "DownloadResult",
    "UpscaleHandler",
    "UpscaleResult",
    
    # Parsing
    "BatchParser",
    "ParsedPrompt",
    "ImportValidator",
    "ValidationIssue",
    "ValidationResult",
    "IssueSeverity",
    
    # Security
    "SecurityManager",
    "IntegrityChecker",
    "AntiDebug",
    "TimeTamperDetector",
    "TrialProtection",
    "EnvironmentChecker",
    "SecurityStatus",
    "SecurityCheckResult",
    
    # Session Management
    "SessionMonitor",
    "SessionEvent",
    "SessionError",
    "CookieRefreshManager",
    "RefreshRequest",
    "RefreshStatus",
    
    # Controllers
    "AppController",
    "AppState",
    "EventManager",
    "EventType",
    "Event",
    "get_event_manager",
    "emit_event",
    "QueueController",
    "QueueItemView",
    "SettingsController",
    "LicenseController",
    
    # Browser Automation
    "BrowserManager",
    "BrowserSession",
    "BrowserConfig",
    "BrowserState",
    
    # Token Extraction
    "TokenExtractor",
    "ExtractedTokens",
    "extract_tokens",
    "extract_tokens_sync",
]
