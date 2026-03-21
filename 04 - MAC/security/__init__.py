# VEO License Client Module
# Client-side license validation, request submission, and trial protection

from .license_client import LicenseClient, LicenseInfo, LicenseTier
from .trial_protection import TrialMarkerManager, TimeVerifier

__all__ = [
    'LicenseClient',
    'LicenseInfo', 
    'LicenseTier',
    'TrialMarkerManager',
    'TimeVerifier'
]
