# 🎫 License Tiers & Features

> **Version**: 2.0  
> **Updated**: 2026-02-02  
> **Source**: Synced with `01_UI_UX/TAB_08_LICENSE.md`

---

## Pricing Tiers (VND)

| Gói | Giá (VND) | Thời hạn | Tiết kiệm |
|-----|-----------|----------|-----------|
| **🆓 Trial** | Miễn phí | 7 ngày | - |
| **📅 1 Tháng** | 300,000 | 30 ngày | 0% |
| **📅 3 Tháng** | 500,000 | 90 ngày | **44%** |
| **📅 6 Tháng** | 800,000 | 180 ngày | **56%** |
| **📅 1 Năm** | 1,200,000 | 365 ngày | **67%** |
| **♾️ Vĩnh viễn** | 3,000,000 | Không giới hạn | **92%*** |

*Tính theo 10 năm sử dụng

---

## Feature Matrix

| Feature | 🆓 Trial | 💎 Premium | 🧪 Tester |
|---------|----------|------------|-----------|
| **Số Cookies** | 1 | Unlimited | Unlimited |
| **Luồng đồng thời** | 2 | Unlimited | Unlimited |
| **Prompts/Task** | 10 | Unlimited | Unlimited |
| **Tất cả modes** | ✅ | ✅ | ✅ |
| **Image/Video quality** | ✅ | ✅ | ✅ |
| **Auto-download** | ✅ | ✅ | ✅ |
| **Queue management** | ✅ | ✅ | ✅ |
| **Dev Console** | ❌ | ❌ | ✅ |
| **Beta Features** | ❌ | ❌ | ✅ |
| **Advanced Settings** | ❌ | ❌ | ✅ |

---

## 👥 User Roles (v2.2)

| Role | Code | Description |
|------|------|-------------|
| **TRIAL** | 0 | Limited features during trial period |
| **PREMIUM** | 1 | Full features for paid users |
| **TESTER** | 2 | Full + Dev Console + Beta (trusted testers) |

```python
from enum import IntEnum

class UserRole(IntEnum):
    TRIAL = 0       # 1 cookie, 2 threads, 10 prompts
    PREMIUM = 1     # Unlimited
    TESTER = 2      # Unlimited + Dev Console + Beta
```

---

## Trial Limitations

```python
TRIAL_LIMITS = {
    "max_cookies": 1,            # Chỉ 1 tài khoản Google
    "max_concurrent_threads": 2,  # Tối đa 2 luồng tạo cùng lúc
    "max_prompts_per_task": 10,   # Tối đa 10 dòng prompt mỗi task
}

PREMIUM_LIMITS = {
    "max_cookies": -1,            # Unlimited
    "max_concurrent_threads": -1,  # Unlimited (theo capacity máy)
    "max_prompts_per_task": -1,    # Unlimited
}
```

---

## Savings Calculation

| Gói | Giá/Tháng | So với 1 tháng | Tiết kiệm |
|-----|-----------|----------------|-----------|
| 1 Tháng | 300,000 | 100% | 0% |
| 3 Tháng | 167,000 | 56% | **44%** |
| 6 Tháng | 133,000 | 44% | **56%** |
| 1 Năm | 100,000 | 33% | **67%** |
| Vĩnh viễn | ~25,000* | 8%* | **92%*** |

*Tính theo 10 năm sử dụng

---

## License Types Code

```python
class LicenseType(Enum):
    """License types matching pricing tiers"""
    TRIAL = "trial"           # 7 days free
    ONE_MONTH = "1_month"     # 300,000 VND
    THREE_MONTHS = "3_months" # 500,000 VND
    SIX_MONTHS = "6_months"   # 800,000 VND
    ONE_YEAR = "1_year"       # 1,200,000 VND
    LIFETIME = "lifetime"     # 3,000,000 VND

LICENSE_PRICES = {
    "1_month": 300_000,
    "3_months": 500_000,
    "6_months": 800_000,
    "1_year": 1_200_000,
    "lifetime": 3_000_000,
}

LICENSE_DURATIONS = {
    "trial": 7,
    "1_month": 30,
    "3_months": 90,
    "6_months": 180,
    "1_year": 365,
    "lifetime": -1,  # No expiry
}
```

---

## License Validation

```python
class LicenseManager:
    def is_trial(self) -> bool:
        """Check if current license is trial"""
        return self.license_data.get("type") == "trial" or \
               self.license_data.get("key") is None
    
    def is_premium(self) -> bool:
        """Check if current license is premium (any paid tier)"""
        return self.license_data.get("type") in [
            "1_month", "3_months", "6_months", "1_year", "lifetime"
        ]
    
    def get_limits(self) -> dict:
        """Get current limits based on license type"""
        if self.is_trial() or self.is_expired():
            return TRIAL_LIMITS
        return PREMIUM_LIMITS
```

---

## 🆕 Usage Quotas (UsageTracker)

> [!IMPORTANT]
> Tracks daily feature usage per license tier. Trial users have hard limits; Premium users are unlimited.
> `UsageTracker` enforces these limits at runtime and resets counters daily.

### How It Works

```
App Start → Load license tier → Initialize UsageTracker
User Action → check_quota("feature") → allowed? → record_usage("feature")
Daily Reset → usage counters reset at midnight
```

### Tier Limits

| Feature | 🆓 Trial | 💎 Premium |
|---------|----------|------------|
| `max_cookies` | 1 | Unlimited (∞) |
| `parallel_workers` | 2 | Unlimited (∞) |
| `max_prompts_per_task` | 10 | Unlimited (∞) |

### Implementation

```python
from pathlib import Path
from datetime import datetime
import json

TIER_LIMITS = {
    "trial": {
        "max_cookies": 1,
        "parallel_workers": 2,
        "max_prompts_per_task": 10,
    },
    "premium": {
        "max_cookies": float('inf'),
        "parallel_workers": float('inf'),
        "max_prompts_per_task": float('inf'),
    }
}

class UsageTracker:
    """Track and enforce per-tier feature usage with daily reset."""
    
    def __init__(self, tier: str):
        self.tier = tier
        self.limits = TIER_LIMITS[tier]
        self.usage_file = Path.home() / ".veoauto" / "usage.json"
    
    def check_quota(self, feature: str) -> dict:
        """Check if user can use feature"""
        today = datetime.now().date().isoformat()
        usage = self._load_usage()
        
        if today not in usage:
            usage[today] = {}
        
        current = usage[today].get(feature, 0)
        limit = self.limits.get(feature, float('inf'))
        
        return {
            "allowed": current < limit,
            "used": current,
            "limit": limit,
            "remaining": max(0, limit - current)
        }
    
    def record_usage(self, feature: str):
        """Record feature usage"""
        today = datetime.now().date().isoformat()
        usage = self._load_usage()
        
        if today not in usage:
            usage[today] = {}
        
        usage[today][feature] = usage[today].get(feature, 0) + 1
        self._save_usage(usage)
    
    def _load_usage(self) -> dict:
        if not self.usage_file.exists():
            return {}
        try:
            return json.loads(self.usage_file.read_text())
        except:
            return {}
    
    def _save_usage(self, usage: dict):
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        self.usage_file.write_text(json.dumps(usage))
```

### Integration Example

```python
# In generation workflow:
tracker = UsageTracker(license_manager.get_tier())

quota = tracker.check_quota("max_prompts_per_task")
if not quota["allowed"]:
    show_upgrade_dialog(f"Bạn đã dùng hết {quota['limit']} prompts hôm nay")
    return

# Proceed with generation...
tracker.record_usage("max_prompts_per_task")
```

---

## 📞 Thông Tin Hỗ Trợ

| Kênh | Liên hệ |
|------|---------|
| **Zalo/SĐT** | `0865 819 458` |
| **Zalo/SĐT (Backup)** | `0865 679 288` |
| **Techcombank** | `4584 5866 88` - LE VAN LINH |

---

*Synced from TAB_08_LICENSE.md on 2026-02-07*

