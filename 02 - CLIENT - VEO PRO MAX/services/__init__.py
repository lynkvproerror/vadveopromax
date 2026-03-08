"""VEO Pro Max - Services Package

External service integrations.
"""

from security.license_client import LicenseClient, LicenseInfo, UsageStats
from .firebase_rest_client import FirebaseRESTClient, FirebaseConfig, LicenseData
from .permissions import PermissionsSystem, Role, Feature, RoleLimits
from .image_library import ImageLibrary, LibraryImage, get_image_library
from .gemini_client import GeminiClient, GeminiAPIError, RateLimitError, InvalidKeyError
from .gemini_key_manager import GeminiKeyManager

__all__ = [
    # License (from security/)
    "LicenseClient",
    "LicenseInfo",
    "UsageStats",
    
    # Firebase
    "FirebaseRESTClient",
    "FirebaseConfig",
    "LicenseData",
    
    # Permissions
    "PermissionsSystem",
    "Role",
    "Feature",
    "RoleLimits",
    
    # Image Library
    "ImageLibrary",
    "LibraryImage",
    "get_image_library",
    
    # Gemini AI
    "GeminiClient",
    "GeminiAPIError",
    "RateLimitError",
    "InvalidKeyError",
    "GeminiKeyManager",
]

