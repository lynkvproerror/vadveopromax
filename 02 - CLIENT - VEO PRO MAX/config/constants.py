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
    UPLOAD = "/v1/flow/uploadImage"       # F12 verified: I2I upload endpoint
    UPLOAD_LEGACY = "/v1:uploadUserImage"  # Legacy endpoint (kept for reference)
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
    
    HAR-verified mapping: {workflow}_{speed}_{orientation}_{quality}[_relaxed]
    - Fast = default priority
    - LP (_relaxed) = Lower Priority, slower queue
    - _fl_ = first-last (dual frame I2V)
    """
    # --- T2V: Text to Video ---
    # NOTE: T2V landscape does NOT include "_landscape_" (unlike R2V)
    # HAR + n8n verified: landscape = "fast_ultra", portrait = "fast_portrait_ultra"
    T2V_LANDSCAPE = "veo_3_1_t2v_fast_ultra"
    T2V_PORTRAIT = "veo_3_1_t2v_fast_portrait_ultra"
    T2V_LANDSCAPE_LP = "veo_3_1_t2v_fast_ultra_relaxed"
    T2V_PORTRAIT_LP = "veo_3_1_t2v_fast_portrait_ultra_relaxed"
    
    # --- I2V Single: Start Image → Video ---
    I2V_SINGLE_LANDSCAPE = "veo_3_1_i2v_s_fast_ultra"
    I2V_SINGLE_LANDSCAPE_LP = "veo_3_1_i2v_s_fast_ultra_relaxed"
    # Portrait single not in HAR — infer pattern:
    I2V_SINGLE_PORTRAIT = "veo_3_1_i2v_s_fast_portrait_ultra"
    I2V_SINGLE_PORTRAIT_LP = "veo_3_1_i2v_s_fast_portrait_ultra_relaxed"
    
    # --- I2V Dual (FL): First + Last Frame → Video ---
    I2V_DUAL_LANDSCAPE = "veo_3_1_i2v_s_fast_fl_ultra"
    I2V_DUAL_LANDSCAPE_LP = "veo_3_1_i2v_s_fast_fl_ultra_relaxed"
    I2V_DUAL_PORTRAIT = "veo_3_1_i2v_s_fast_portrait_fl_ultra"
    I2V_DUAL_PORTRAIT_LP = "veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed"
    
    # --- R2V: Reference Images → Video ---
    R2V_LANDSCAPE = "veo_3_1_r2v_fast_landscape_ultra"
    R2V_PORTRAIT = "veo_3_1_r2v_fast_portrait_ultra"
    R2V_LANDSCAPE_LP = "veo_3_1_r2v_fast_landscape_ultra_relaxed"
    R2V_PORTRAIT_LP = "veo_3_1_r2v_fast_portrait_ultra_relaxed"
    
    # --- VEO 3.0 Models (legacy) ---
    VEO_30_LANDSCAPE = "veo_3_0_t2v_landscape_ultra"
    VEO_30_PORTRAIT = "veo_3_0_t2v_portrait_ultra"
    
    # --- Upscaler Models ---
    UPSCALER_1080P = "veo_3_1_upsampler_1080p"
    UPSCALER_4K = "veo_3_1_upsampler_4k"


# === IMAGE MODELS ===
class ImageModel(str, Enum):
    """Image generation model keys (HAR-verified)."""
    NARWHAL = "NARWHAL"          # 🔥 Nano Banana 2 (HAR 2026-03-07)
    GEM_PIX_2 = "GEM_PIX_2"      # 🔥 Nano Banana Pro (default)
    IMAGEN_3_5 = "IMAGEN_3_5"    # Imagen 4


def resolve_model_key(
    display_name: str,
    workflow: "WorkflowType",
    aspect_ratio: str,
    dual_frame: bool = False,
    image_model: str = "",
) -> str:
    """Auto-map (UI display name + workflow + aspect ratio) → API model key.
    
    Args:
        display_name: UI text from sidebar, e.g. "Veo 3.1 - Fast", "Veo 3.1 - Fast [LP]"
        workflow: WorkflowType enum (T2V, I2V, R2V, F2V, T2I)
        aspect_ratio: "LANDSCAPE" or "PORTRAIT"
        dual_frame: True if I2V with 2 frames (first+last)
        image_model: API key for image model (e.g. "GEM_PIX_2", "IMAGEN_3_5")
    
    Returns:
        API model key string, e.g. "veo_3_1_t2v_fast_portrait_ultra_relaxed"
    """
    is_portrait = "PORTRAIT" in aspect_ratio.upper()
    is_lp = "[LP]" in display_name or "Lower" in display_name
    
    # T2I and I2I both use ImageModel, not VideoModel
    if workflow in (WorkflowType.T2I, WorkflowType.I2I):
        if image_model and image_model in [e.value for e in ImageModel]:
            return image_model
        return ImageModel.GEM_PIX_2.value  # Sidebar default: 🔥 Nano Banana Pro
    
    # Model lookup table: (workflow_key, is_portrait, is_lp) → VideoModel
    _MAP = {
        # T2V
        ("T2V", False, False): VideoModel.T2V_LANDSCAPE,
        ("T2V", True,  False): VideoModel.T2V_PORTRAIT,
        ("T2V", False, True):  VideoModel.T2V_LANDSCAPE_LP,
        ("T2V", True,  True):  VideoModel.T2V_PORTRAIT_LP,
        # I2V Single
        ("I2V_S", False, False): VideoModel.I2V_SINGLE_LANDSCAPE,
        ("I2V_S", True,  False): VideoModel.I2V_SINGLE_PORTRAIT,
        ("I2V_S", False, True):  VideoModel.I2V_SINGLE_LANDSCAPE_LP,
        ("I2V_S", True,  True):  VideoModel.I2V_SINGLE_PORTRAIT_LP,
        # I2V Dual (First + Last frame)
        ("I2V_D", False, False): VideoModel.I2V_DUAL_LANDSCAPE,
        ("I2V_D", True,  False): VideoModel.I2V_DUAL_PORTRAIT,
        ("I2V_D", False, True):  VideoModel.I2V_DUAL_LANDSCAPE_LP,
        ("I2V_D", True,  True):  VideoModel.I2V_DUAL_PORTRAIT_LP,
        # R2V
        ("R2V", False, False): VideoModel.R2V_LANDSCAPE,
        ("R2V", True,  False): VideoModel.R2V_PORTRAIT,
        ("R2V", False, True):  VideoModel.R2V_LANDSCAPE_LP,
        ("R2V", True,  True):  VideoModel.R2V_PORTRAIT_LP,
    }
    
    # Determine workflow key
    wf_name = workflow.name if hasattr(workflow, "name") else str(workflow)
    if wf_name in ("I2V", "F2V"):
        wf_key = "I2V_D" if dual_frame else "I2V_S"
    elif wf_name == "R2V":
        wf_key = "R2V"
    else:
        wf_key = "T2V"
    
    result = _MAP.get((wf_key, is_portrait, is_lp))
    if result:
        return result.value
    
    # Fallback: T2V landscape fast
    return VideoModel.T2V_LANDSCAPE.value


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
    """Application license tiers (per LICENSE_TIERS_FEATURES.md).
    
    All paid tiers map to PREMIUM role.
    TESTER role is assigned via Firebase _role field, not via tier.
    """
    TRIAL = "TRIA"           # 3 days free (matches license_client.py)
    ONE_MONTH = "1M"         # 300,000 VND
    THREE_MONTHS = "3M"      # 500,000 VND
    SIX_MONTHS = "6M"        # 800,000 VND
    ONE_YEAR = "1Y"          # 1,200,000 VND
    LIFETIME = "LT"          # 3,000,000 VND


# === SHARED TIER DISPLAY NAMES (single source of truth) ===
TIER_DISPLAY_MAP = {
    "TRIA": "Trial (3d)", "1M": "1 Tháng", "3M": "3 Tháng",
    "6M": "6 Tháng", "1Y": "1 Năm", "LT": "Vĩnh viễn",
}

# === FIREBASE COLLECTION NAMES ===
COL_LICENSES = "_lic"
COL_TRIALS = "_trials"
COL_UPGRADE_REQUESTS = "_upgrade_requests"
COL_CUSTOMERS = "_customers"
COL_MID_TO_KEY = "_mid_to_key"
COL_CONFIG = "_config"


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


# F12 verified 2026-03-15: xcd requirements differ by task type:
# - Video (T2V/I2V/R2V/Upscale): 40+ chars — bot detection sensitive
# - T2I (text-only image gen): 8+ chars — works with stub, no reference images
# - I2I (image-to-image with refs): 40+ chars — all F12 captures show 48-char xcd
MIN_VALID_XCD = 40          # Video generation: Chrome Variations must be fully enrolled
MIN_VALID_XCD_IMAGE = 8     # T2I (text-only): 8-char stub sufficient
MIN_VALID_XCD_I2I = 40      # I2I (with reference images): full enrollment required

# After browser restart, wait this long for Variations Service to produce
# a valid x-client-data before falling back to borrow.
XCD_VARIATIONS_WAIT_TIMEOUT = 20  # seconds


# === PROGRESSIVE TIMEOUT TIERS ===
# Slow/unstable networks get escalating timeouts per retry attempt.
# Fast networks still pass quickly via early-exit logic.
TIMEOUT_TIERS = [
    # Attempt 0 (first try) — normal network
    {'xcd_poll': 20.0, 'rc_wait': 25.0, 'bridge_timeout': 35.0,
     'rc_execute_ms': 15000, 'fetch_ms': 20000,
     't2i_bridge_timeout': 105.0, 't2i_fetch_ms': 90000},
    # Attempt 1 (retry) — slow network tolerance
    {'xcd_poll': 30.0, 'rc_wait': 35.0, 'bridge_timeout': 45.0,
     'rc_execute_ms': 25000, 'fetch_ms': 30000,
     't2i_bridge_timeout': 115.0, 't2i_fetch_ms': 95000},
    # Attempt 2+ (final retries) — maximum patience
    {'xcd_poll': 40.0, 'rc_wait': 45.0, 'bridge_timeout': 55.0,
     'rc_execute_ms': 35000, 'fetch_ms': 40000,
     't2i_bridge_timeout': 125.0, 't2i_fetch_ms': 100000},
]


def get_timeout_tier(attempt: int = 0) -> dict:
    """Get timeout configuration for a given retry attempt.
    
    Progressive escalation: attempt 0 → Tier 0 (fast), 1 → Tier 1 (slow),
    2+ → Tier 2 (maximum patience). Early-exit logic in all wait loops
    means fast networks are unaffected.
    """
    tier_idx = min(attempt, len(TIMEOUT_TIERS) - 1)
    return TIMEOUT_TIERS[tier_idx]


# === APP CONSTANTS ===
class AppConstants:
    """Application-wide constants."""
    APP_NAME = "VEO Pro Max"
    APP_VERSION = "2.3.6"
    
    # Auto-update (GitHub public repo)
    GITHUB_REPO = "lynkvproerror/vadveopromax"
    VERSION_CHECK_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"
    
    # Queue limits
    MAX_QUEUE_SIZE = 1000
    MAX_PARALLEL_ACCOUNTS = 10
    MAX_SLOTS_PER_ACCOUNT = 4
    
    # Download limits
    MAX_PARALLEL_DOWNLOADS = 3
    DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB
    
    # Polling — 2-phase strategy
    # Phase 1 (0-30s): video never completes this fast → slow poll saves requests
    # Phase 2 (30s+):  video likely completing soon → faster poll for responsiveness
    POLL_PHASE1_INTERVAL = 15   # seconds (first 30s)
    POLL_PHASE1_DURATION = 30   # seconds (how long phase 1 lasts)
    POLL_PHASE2_INTERVAL = 8    # seconds (after 30s)
    POLL_INTERVAL = 8           # legacy alias (used by upscale poll)
    MAX_POLL_TIME = 600         # 10 minutes
    
    # Trial limits
    TRIAL_MAX_COOKIES = 1
    TRIAL_MAX_THREADS = 2
    TRIAL_MAX_PROMPTS_PER_DAY = 10
    
    # Prompt limits
    MAX_PROMPT_LENGTH = 1000


# === IMAGE ENHANCER CONFIG ===
class EnhanceConfig:
    """Configuration defaults for the Image Enhancer system."""
    # Toggle defaults (user can change in Settings)
    CONTEXT_MENU_ENHANCE = True    # Right-click "Enhance" on image slots
    LIBRARY_ENHANCE = True         # "Enhance" button in Image Library
    AUTO_ENHANCE_CONTINUATION = False  # Auto-enhance continuation frames
    
    # Model settings
    DEFAULT_MODE = "upscale_4x"    # Default enhance mode
    TILE_SIZE = 256                # GPU tile size (px) — lower = less VRAM
    USE_FP16 = True                # Half-precision for speed
    WORKER_TIMEOUT = 300           # Max seconds for worker subprocess
    
    # Download URLs (from original authors' GitHub Releases)
    MODEL_URLS = {
        'RealESRGAN_x4plus.pth': 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth',
        'RealESRGAN_x2plus.pth': 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth',
        'GFPGANv1.4.pth': 'https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth',
    }

