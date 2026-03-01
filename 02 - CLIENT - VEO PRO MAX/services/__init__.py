"""VEO Pro Max - Services Package

External service integrations.
"""

from security.license_client import LicenseClient, LicenseInfo, UsageStats
from .firebase_rest_client import FirebaseRESTClient, FirebaseConfig, LicenseData
from .permissions import PermissionsSystem, Role, Feature, RoleLimits
from .image_library import ImageLibrary, LibraryImage, get_image_library

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
]

