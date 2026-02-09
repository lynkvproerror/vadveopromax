"""
VEO Pro Max - Constants & Terminology

Reference: GLOSSARY.md, CHEATSHEET.md, API_MAPPING.md
"""

from enum import Enum, auto


# === WORKFLOW TYPES ===
class WorkflowType(str, Enum):
    """Video/Image generation workflow types."""
    T2V = "text_to_video"           # Text → Video
    I2V = "image_to_video"          # 1 Image → Video (Start Only)
    F2V = "frames_to_video"         # 2 Images → Video (Start + End)
    R2V = "references_to_video"     # 1-3 Images → Video (Ingredients)
    T2I = "text_to_image"           # Text → Image
    I2I = "image_to_image"          # Image → Modified Image


# === API ENDPOINTS ===
class APIEndpoints:
    """VEO API endpoint constants."""
    BASE_URL = "https://aisandbox-pa.googleapis.com"
    
    # Video Generation
    T2V = "/v1/video:batchAsyncGenerateVideoText"
    I2V_SINGLE = "/v1/video:batchAsyncGenerateVideoStartImage"
    I2V_DUAL = "/v1/video:batchAsyncGenerateVideoStartAndEndImage"
    R2V = "/v1/video:batchAsyncGenerateVideoReferenceImages"
    
    # Image Generation
    T2I = "/v1/flowMedia:batchGenerateImages"
    
    # Status & Utils
    STATUS = "/v1/video:batchCheckAsyncVideoGenerationStatus"
    UPLOAD = "/v1:uploadUserImage"
    UPSCALE_VIDEO = "/v1/video:batchAsyncGenerateVideoUpsampleVideo"
    UPSCALE_IMAGE = "/v1/flow/upsampleImage"  # Doc §3.3: correct path
    
    # Additional endpoints from HAR analysis
    GIF = "/v1/video:generatePinholeGif"
    CREDITS = "/v1/credits"
    APP_STATUS = "/v1:checkAppAvailability"
    RECOMMENDATIONS = "/v1:fetchUserRecommendations"
    IMAGE_UPSCALE_FLOW = "/v1/flow/upsampleImage"
    
    # API Keys (Doc §2.1)
    API_KEY = "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"


# === ASPECT RATIOS ===
class AspectRatio(str, Enum):
    """Video aspect ratio options."""
    LANDSCAPE = "VIDEO_ASPECT_RATIO_LANDSCAPE"  # 16:9
    PORTRAIT = "VIDEO_ASPECT_RATIO_PORTRAIT"    # 9:16


# === VIDEO QUALITY ===
class VideoQuality(str, Enum):
    """Video resolution/quality options."""
    P720 = "720p"
    P1080 = "1080p"
    P4K = "4K"


# === VIDEO MODELS ===
class VideoModel(str, Enum):
    """VEO video generation model keys.
    
    Reference: SEED_MANAGEMENT.md, HAR analysis
    """
    # VEO 3.1 Fast Models
    VEO_FAST_31 = "veo_3_1_t2v_fast_landscape_ultra"
    VEO_FAST_31_PORTRAIT = "veo_3_1_t2v_fast_portrait_ultra"
    
    # VEO 3.0 Models
    VEO_30 = "veo_3_0_t2v_landscape_ultra"
    VEO_30_PORTRAIT = "veo_3_0_t2v_portrait_ultra"
    
    # Image to Video Models
    VEO_I2V = "veo_3_1_i2v_fast_landscape_ultra"
    VEO_I2V_PORTRAIT = "veo_3_1_i2v_fast_portrait_ultra"


# === VIDEO RESOLUTION API VALUES ===
class VideoResolution(str, Enum):
    """Video resolution for upscale requests."""
    HD = "VIDEO_RESOLUTION_1080P"
    UHD = "VIDEO_RESOLUTION_4K"


# === GENERATION STATUS ===
class GenerationStatus(str, Enum):
    """Status of generation operation."""
    PENDING = "MEDIA_GENERATION_STATUS_PENDING"
    ACTIVE = "MEDIA_GENERATION_STATUS_ACTIVE"  # Doc §6.20: was IN_PROGRESS
    SUCCESSFUL = "MEDIA_GENERATION_STATUS_SUCCESSFUL"
    FAILED = "MEDIA_GENERATION_STATUS_FAILED"


# === QUEUE ITEM STATUS ===
class QueueItemStatus(str, Enum):
    """Status of a queue item."""
    WAITING = "waiting"
    QUEUED = "queued"
    PROCESSING = "processing"
    GENERATING = "generating"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# === ACCOUNT STATUS ===
class AccountStatus(str, Enum):
    """Chrome profile/account status."""
    READY = "ready"         # 🟢 Valid session
    ACTIVE = "active"       # 🔵 Currently processing
    LOGIN_REQUIRED = "login_required"  # 🟡 Need re-login
    ERROR = "error"         # 🔴 Error state
    COOLDOWN = "cooldown"   # ⏳ Rate limited


# === SUBSCRIPTION TIERS ===
# NOTE: SubscriptionType is defined in core/session.py (canonical location)
# Import from there: from core.session import SubscriptionType
# Values: WS_ULTRA, WS_PRO, WS_FREEMIUM, UNKNOWN


# === LICENSE TIERS ===
class LicenseTier(str, Enum):
    """Application license tiers."""
    TRIAL = "TRIA"
    BASIC = "BASI"
    PRO = "PROF"
    ENTERPRISE = "ENTR"
    LIFETIME = "LIFE"


# === WORKER STATES ===
# NOTE: WorkerState is defined in core/worker.py (canonical location)
# Import from there: from core.worker import WorkerState


# === ERROR CATEGORIES ===
class ErrorCategory(str, Enum):
    """Error classification categories."""
    NETWORK = "network"           # 1xxx
    AUTH = "auth"                 # 2xxx
    API = "api"                   # 3xxx
    RATE_LIMIT = "rate_limit"     # 4xxx
    VALIDATION = "validation"     # 5xxx
    PROCESSING = "processing"     # 6xxx
    FILE_SYSTEM = "file_system"   # 7xxx


# === TOKEN LIFETIMES ===
class TokenLifetime:
    """Token expiration times in seconds."""
    ACCESS_TOKEN = 3600         # 1 hour
    RECAPTCHA_TOKEN = 90        # ~90 seconds
    RECAPTCHA_REFRESH = 80      # Refresh at 80s
    SESSION_COOKIE = 604800     # 7 days


# === APP CONSTANTS ===
class AppConstants:
    """Application-wide constants."""
    APP_NAME = "VEO Pro Max"
    APP_VERSION = "1.0.0"
    
    # Queue limits
    MAX_QUEUE_SIZE = 1000
    MAX_PARALLEL_ACCOUNTS = 10
    MAX_SLOTS_PER_ACCOUNT = 4
    
    # Download limits
    MAX_PARALLEL_DOWNLOADS = 3
    DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB
    
    # Polling
    POLL_INTERVAL = 5          # seconds
    MAX_POLL_TIME = 600        # 10 minutes
    
    # Trial limits
    TRIAL_MAX_COOKIES = 1
    TRIAL_MAX_THREADS = 2
    TRIAL_MAX_PROMPTS_PER_DAY = 10
    
    # Prompt limits
    MAX_PROMPT_LENGTH = 1000
