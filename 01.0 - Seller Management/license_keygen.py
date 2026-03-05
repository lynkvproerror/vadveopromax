"""
License Key Generator v2.4 - With Role Support
Key looks completely random: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
Contains encoded: Machine ID + Tier + Role + Timestamp (XOR obfuscated)

Key Format: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
            All segments are hex-encoded + XOR obfuscated

Roles: 0=Trial, 1=Premium, 2=Tester
Security: SECRET_KEY loaded from environment variable VEO_LICENSE_SECRET
"""

import hashlib
import struct
import os
from datetime import datetime, timedelta
from enum import Enum, IntEnum
from typing import Optional
from dataclasses import dataclass


# =============================================================================
# USER ROLES
# =============================================================================

class UserRole(IntEnum):
    """User permission roles"""
    TRIAL = 0       # Limited: 1 cookie, 2 threads, 10 prompts
    PREMIUM = 1     # Unlimited (paid user)
    TESTER = 2      # Unlimited + Dev Console + Beta features


# =============================================================================
# SECRET KEY MANAGEMENT
# =============================================================================

def get_secret_key() -> bytes:
    """
    Get secret key from environment variable.
    
    SECURITY: Never hardcode this key in source code!
    
    Setup:
        1. Generate: python -c "import secrets; print(secrets.token_hex(16))"
        2. Set env:  set VEO_LICENSE_SECRET=<32-char-hex>
        
    Returns:
        16-byte secret key
        
    Raises:
        RuntimeError: If VEO_LICENSE_SECRET is not set
    """
    key_hex = os.environ.get("VEO_LICENSE_SECRET")
    
    if key_hex:
        try:
            key_bytes = bytes.fromhex(key_hex)
            if len(key_bytes) >= 16:
                return key_bytes[:16]
        except ValueError:
            pass
    
    # SECURITY: No fallback — MUST set env var
    raise RuntimeError(
        "VEO_LICENSE_SECRET not set! "
        "Run: python -c \"import secrets; print(secrets.token_hex(16))\" "
        "then: set VEO_LICENSE_SECRET=<result>"
    )


class LicenseTier(str, Enum):
    """VND Pricing Model - License Tiers"""
    TRIAL = "TRIA"           # 7 ngày - Miễn phí
    ONE_MONTH = "1M"         # 30 ngày - 300,000đ
    THREE_MONTHS = "3M"      # 90 ngày - 500,000đ
    SIX_MONTHS = "6M"        # 180 ngày - 800,000đ
    ONE_YEAR = "1Y"          # 365 ngày - 1,200,000đ
    LIFETIME = "LT"          # Vĩnh viễn - 3,000,000đ
    
    @classmethod
    def from_name(cls, name: str) -> "LicenseTier":
        """Get tier from name or code"""
        name_upper = name.upper().replace(" ", "_")
        for tier in cls:
            if tier.name == name_upper or tier.value == name_upper:
                return tier
        raise ValueError(f"Invalid tier name: {name}")
    
    @classmethod
    def from_code(cls, code: int) -> "LicenseTier":
        """Get tier from numeric code (1-6)"""
        codes = {
            1: cls.TRIAL, 
            2: cls.ONE_MONTH, 
            3: cls.THREE_MONTHS, 
            4: cls.SIX_MONTHS,
            5: cls.ONE_YEAR,
            6: cls.LIFETIME
        }
        return codes.get(code, cls.TRIAL)
    
    @property
    def code(self) -> int:
        """Get numeric code for tier"""
        codes = {
            "TRIA": 1, "1M": 2, "3M": 3, 
            "6M": 4, "1Y": 5, "LT": 6
        }
        return codes.get(self.value, 1)
    
    @property
    def duration_days(self) -> int:
        """Get default duration in days for this tier"""
        durations = {
            "TRIA": 7, "1M": 30, "3M": 90,
            "6M": 180, "1Y": 365, "LT": 36500  # 100 years
        }
        return durations.get(self.value, 30)
    
    @property
    def price_vnd(self) -> int:
        """Get price in VND"""
        prices = {
            "TRIA": 0, "1M": 300_000, "3M": 500_000,
            "6M": 800_000, "1Y": 1_200_000, "LT": 3_000_000
        }
        return prices.get(self.value, 0)


@dataclass
class LicenseKey:
    """Parsed license key data"""
    key: str
    machine_id: str
    tier: LicenseTier
    role: UserRole = UserRole.PREMIUM  # 🆕 User role
    created: datetime = None
    expires: datetime = None
    valid: bool = True
    error: Optional[str] = None


class ObfuscatedKeyGenerator:
    """
    Generate obfuscated license keys v2.4 (with role).
    
    Data structure (16 bytes):
    - bytes 0-7: Machine ID hash (8 bytes)
    - byte 8: Tier code (1 byte)
    - byte 9: Role code (1 byte) 🆕
    - bytes 10-13: Expiry timestamp (4 bytes, Unix)
    - bytes 14-15: Checksum (2 bytes)
    
    Total: 16 bytes → XOR → HEX → 32 chars → format 8 segments of 4
    """
    
    # No prefix - completely random looking
    # SECRET_KEY loaded dynamically from environment
    
    @classmethod
    def _get_secret(cls) -> bytes:
        """Get secret key (cached for performance)."""
        if not hasattr(cls, '_cached_secret'):
            cls._cached_secret = get_secret_key()
        return cls._cached_secret
    
    # ── Public checksum salt (shared with client) ──
    _CHECKSUM_SALT = b"V3O_PUB_CK_2026"
    
    @classmethod
    def _compute_public_checksum(cls, core_key: str) -> str:
        """Compute 4-char hex checksum from the 8 core segments.
        
        This is PUBLIC (visible in key) — used for quick local rejection
        of random/fake keys before hitting Firebase.
        """
        payload = core_key.upper().replace("-", "").encode() + cls._CHECKSUM_SALT
        return hashlib.sha256(payload).hexdigest()[:4].upper()
    
    @classmethod
    def generate(
        cls,
        machine_id: str,
        tier: LicenseTier,
        duration_days: int = 30,
        role: UserRole = UserRole.PREMIUM  # 🆕 Role parameter
    ) -> tuple[str, dict]:
        """Generate an obfuscated pre-bound license key with role + public checksum."""
        now = datetime.now()
        expires = now + timedelta(days=duration_days)
        
        # Build raw data (14 bytes)
        mid_hash = cls._hash_machine_id(machine_id)[:8]  # 8 bytes
        tier_byte = tier.code.to_bytes(1, 'big')          # 1 byte
        role_byte = int(role).to_bytes(1, 'big')          # 1 byte 🆕
        # Cap to uint32 max (4,294,967,295 = year 2106) to fit in 4 bytes.
        # LIFETIME tier (36500 days → year 2126) would overflow without this cap.
        # Actual expiry is tracked in Firestore — this is only a local hint.
        expires_ts_int = min(int(expires.timestamp()), 0xFFFFFFFF)
        expires_ts = expires_ts_int.to_bytes(4, 'big')  # 4 bytes
        
        raw_data = mid_hash + tier_byte + role_byte + expires_ts  # 14 bytes
        
        # Add checksum (2 bytes) → total 16 bytes
        checksum = hashlib.sha256(raw_data + machine_id.encode() + cls._get_secret()).digest()[:2]
        raw_data += checksum
        
        # XOR obfuscate
        obfuscated = cls._xor_with_key(raw_data)
        
        # Convert to hex (32 chars)
        hex_str = obfuscated.hex().upper()
        
        # Format: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX (8 core segments)
        segments = [hex_str[i:i+4] for i in range(0, 32, 4)]
        core_key = "-".join(segments)
        
        # Append 9th segment: public checksum (SHA256-based, 4 hex chars)
        pub_checksum = cls._compute_public_checksum(core_key)
        key = f"{core_key}-{pub_checksum}"
        
        metadata = {
            "key": key,
            "machine_id": machine_id,
            "tier": tier.value,
            "tier_name": tier.name,
            "role": int(role),  # 🆕
            "role_name": role.name,  # 🆕
            "created": now.isoformat(),
            "expires": expires.isoformat(),
            "duration_days": duration_days,
        }
        
        return key, metadata
    
    @classmethod
    def decode(cls, key: str, machine_id: str) -> LicenseKey:
        """Decode and validate a license key with role."""
        try:
            # Strip public checksum (9th segment) if present
            parts = key.upper().replace(" ", "").split("-")
            if len(parts) == 9:
                # New format: 8 core + 1 checksum → strip checksum for decode
                core_key = "-".join(parts[:8])
                clean_key = "".join(parts[:8])
            elif len(parts) == 8:
                # Legacy format: 8 segments only
                clean_key = "".join(parts)
            else:
                raise ValueError("Invalid key length")
            
            if len(clean_key) != 32:
                raise ValueError("Invalid key length")
            
            # Hex to bytes
            obfuscated = bytes.fromhex(clean_key)
            
            # De-obfuscate (XOR is symmetric)
            raw_data = cls._xor_with_key(obfuscated)
            
            # Extract components (v2.4 structure)
            mid_hash = raw_data[:8]           # bytes 0-7
            tier_code = raw_data[8]           # byte 8
            role_code = raw_data[9]           # byte 9 🆕
            expires_ts = struct.unpack('>I', raw_data[10:14])[0]  # bytes 10-13
            stored_checksum = raw_data[14:16]  # bytes 14-15
            
            # Verify machine ID hash
            expected_mid_hash = cls._hash_machine_id(machine_id)[:8]
            if mid_hash != expected_mid_hash:
                return LicenseKey(
                    key=key, machine_id="", tier=LicenseTier.TRIAL,
                    role=UserRole.TRIAL,
                    created=datetime.now(), expires=datetime.now(),
                    valid=False, error="Key không dành cho máy này"
                )
            
            # Verify checksum (against first 14 bytes)
            expected_checksum = hashlib.sha256(
                raw_data[:14] + machine_id.encode() + cls._get_secret()
            ).digest()[:2]
            
            if stored_checksum != expected_checksum:
                return LicenseKey(
                    key=key, machine_id="", tier=LicenseTier.TRIAL,
                    role=UserRole.TRIAL,
                    created=datetime.now(), expires=datetime.now(),
                    valid=False, error="Key không hợp lệ"
                )
            
            # Parse expiry
            expires = datetime.fromtimestamp(expires_ts)
            
            # Parse role
            try:
                role = UserRole(role_code)
            except ValueError:
                role = UserRole.TRIAL
            
            # Check expiry
            if datetime.now() > expires:
                return LicenseKey(
                    key=key, machine_id=machine_id,
                    tier=LicenseTier.from_code(tier_code),
                    role=role,
                    created=datetime.now(), expires=expires,
                    valid=False, error="Key đã hết hạn"
                )
            
            return LicenseKey(
                key=key,
                machine_id=machine_id,
                tier=LicenseTier.from_code(tier_code),
                role=role,  # 🆕
                created=datetime.now(),
                expires=expires,
                valid=True
            )
            
        except Exception as e:
            return LicenseKey(
                key=key, machine_id="", tier=LicenseTier.TRIAL,
                role=UserRole.TRIAL,
                created=datetime.now(), expires=datetime.now(),
                valid=False, error="Key không hợp lệ"
            )
    
    @classmethod
    def _hash_machine_id(cls, machine_id: str) -> bytes:
        """Hash machine ID to fixed length"""
        secret = cls._get_secret()
        salted = f"{machine_id}:{secret.decode(errors='ignore')}"
        return hashlib.sha256(salted.encode()).digest()
    
    @classmethod
    def _xor_with_key(cls, data: bytes) -> bytes:
        """XOR with secret key for obfuscation"""
        secret = cls._get_secret()
        return bytes(b ^ secret[i % len(secret)] for i, b in enumerate(data))


# Alias for compatibility
LicenseKeyGenerator = ObfuscatedKeyGenerator


def main():
    """Demo: Generate and validate obfuscated keys with role"""
    print("=" * 60)
    print("VEO License Key Generator v2.4 - With Role Support")
    print("=" * 60)
    print()
    
    machine_id = "3946C15B"
    tier = LicenseTier.THREE_MONTHS  # 90 ngày - 500,000đ
    
    print(f"Machine ID: {machine_id}")
    print(f"Tier: {tier.name} ({tier.value})")
    print(f"Duration: {tier.duration_days} days")
    print(f"Price: {tier.price_vnd:,}đ")
    print()
    
    # Demo all 3 roles
    for role in UserRole:
        print(f"--- Role: {role.name} ({role.value}) ---")
        key, metadata = ObfuscatedKeyGenerator.generate(
            machine_id, tier, 
            duration_days=365, 
            role=role  # 🆕
        )
        
        print(f"Key: {key}")
        print(f"Role: {metadata['role_name']}")
        
        # Decode
        result = ObfuscatedKeyGenerator.decode(key, machine_id)
        print(f"Decoded Role: {result.role.name}")
        print(f"Valid: {'✅' if result.valid else '❌'}")
        print()
    
    # Show role descriptions
    print("Role Permissions:")
    print("  TRIAL (0): 1 cookie, 2 threads, 10 prompts")
    print("  PREMIUM (1): Unlimited")
    print("  TESTER (2): Unlimited + Dev Console + Beta")
    
    print("=" * 60)


if __name__ == "__main__":
    main()

