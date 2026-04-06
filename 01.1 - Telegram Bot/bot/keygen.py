"""
License Key Generator (Portable)
=================================
Ported from license_keygen.py v2.4 for serverless deployment.
Generates XOR-obfuscated keys with public checksum.
"""

import hashlib
import os
import struct
from datetime import datetime, timedelta
from enum import Enum, IntEnum
from typing import Tuple


class UserRole(IntEnum):
    TRIAL = 0
    PREMIUM = 1
    TESTER = 2


class LicenseTier(str, Enum):
    TRIAL = "TRIA"
    ONE_MONTH = "1M"
    THREE_MONTHS = "3M"
    SIX_MONTHS = "6M"
    ONE_YEAR = "1Y"
    LIFETIME = "LT"

    @classmethod
    def from_code(cls, code: str) -> "LicenseTier":
        for tier in cls:
            if tier.value == code:
                return tier
        return cls.TRIAL

    @property
    def code(self) -> int:
        codes = {"TRIA": 1, "1M": 2, "3M": 3, "6M": 4, "1Y": 5, "LT": 6}
        return codes.get(self.value, 1)

    @property
    def duration_days(self) -> int:
        durations = {"TRIA": 3, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "LT": 36500}
        return durations.get(self.value, 30)


def _get_secret() -> bytes:
    """Get 16-byte secret key from environment variable."""
    key_hex = os.environ.get("VEO_LICENSE_SECRET", "")
    if key_hex:
        try:
            key_bytes = bytes.fromhex(key_hex)
            if len(key_bytes) >= 16:
                return key_bytes[:16]
        except ValueError:
            pass
    raise RuntimeError("VEO_LICENSE_SECRET not set or invalid")


_CHECKSUM_SALT = b"V3O_PUB_CK_2026"


def _hash_machine_id(machine_id: str) -> bytes:
    secret = _get_secret()
    salted = f"{machine_id}:{secret.decode(errors='ignore')}"
    return hashlib.sha256(salted.encode()).digest()


def _xor_with_key(data: bytes) -> bytes:
    secret = _get_secret()
    return bytes(b ^ secret[i % len(secret)] for i, b in enumerate(data))


def _compute_public_checksum(core_key: str) -> str:
    payload = core_key.upper().replace("-", "").encode() + _CHECKSUM_SALT
    return hashlib.sha256(payload).hexdigest()[:4].upper()


def generate_key(
    machine_id: str,
    tier: LicenseTier,
    duration_days: int,
    role: UserRole = UserRole.PREMIUM,
) -> Tuple[str, dict]:
    """Generate an obfuscated license key.

    Returns:
        (key_string, metadata_dict)
    """
    now = datetime.now()
    expires = now + timedelta(days=duration_days)

    # Build raw data (14 bytes)
    mid_hash = _hash_machine_id(machine_id)[:8]
    tier_byte = tier.code.to_bytes(1, "big")
    role_byte = int(role).to_bytes(1, "big")
    expires_ts_int = min(int(expires.timestamp()), 0xFFFFFFFF)
    expires_ts = expires_ts_int.to_bytes(4, "big")

    raw_data = mid_hash + tier_byte + role_byte + expires_ts  # 14 bytes

    # Checksum (2 bytes) → total 16 bytes
    checksum = hashlib.sha256(
        raw_data + machine_id.encode() + _get_secret()
    ).digest()[:2]
    raw_data += checksum

    # XOR obfuscate → hex → format
    obfuscated = _xor_with_key(raw_data)
    hex_str = obfuscated.hex().upper()
    segments = [hex_str[i : i + 4] for i in range(0, 32, 4)]
    core_key = "-".join(segments)

    # Public checksum (9th segment)
    pub_checksum = _compute_public_checksum(core_key)
    key = f"{core_key}-{pub_checksum}"

    metadata = {
        "key": key,
        "machine_id": machine_id,
        "tier": tier.value,
        "role": int(role),
        "role_name": role.name,
        "created": now.isoformat(),
        "expires": expires.isoformat(),
        "duration_days": duration_days,
    }

    return key, metadata
