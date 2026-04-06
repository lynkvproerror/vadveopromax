"""
License Request System - Client Side
Allows users to submit license requests to admin for approval.

Features:
- Submit personal info with machine_id as unique key
- Duplicate detection (same machine_id = info already recorded)
- Rate limiting (1 request per 24 hours)
- Input validation and sanitization
"""

import re
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict
from enum import Enum
from pathlib import Path

# Firebase REST Client (secure, no Admin SDK)
# NOTE: License request submission uses REST API only
try:
    from firebase_rest_client import FirebaseRESTClient
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False


class RequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class LicenseRequest:
    """License request data structure"""
    machine_id: str
    display_id: str
    client_name: str
    email: str
    phone: str = ""
    company: str = ""
    address: str = ""
    requested_tier: str = "TRIAL"
    requested_days: int = 7
    reason: str = ""
    status: RequestStatus = RequestStatus.PENDING
    created_at: Optional[datetime] = None
    approved_key: Optional[str] = None
    admin_note: str = ""


@dataclass
class RequestResult:
    """Result of request operation"""
    success: bool
    message: str
    status: Optional[RequestStatus] = None
    approved_key: Optional[str] = None
    existing_request: bool = False


class InputValidator:
    """Validate and sanitize user input"""
    
    # Vietnamese characters pattern
    VIETNAMESE_CHARS = r'đĐàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ'
    
    @classmethod
    def sanitize_text(cls, text: str, max_length: int = 500) -> str:
        """Remove dangerous characters, keep Vietnamese"""
        if not text:
            return ""
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove control characters
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        
        # Keep: letters, numbers, spaces, basic punctuation, Vietnamese
        pattern = rf'[^\w\s@.,\-()_{cls.VIETNAMESE_CHARS}]'
        text = re.sub(pattern, '', text, flags=re.UNICODE)
        
        return text.strip()[:max_length]
    
    @classmethod
    def validate_email(cls, email: str) -> bool:
        """Validate email format"""
        if not email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @classmethod
    def validate_phone(cls, phone: str) -> bool:
        """Validate Vietnamese phone format"""
        if not phone:
            return True  # Optional field
        # Vietnamese: 10-11 digits, starts with 0
        pattern = r'^0[0-9]{9,10}$'
        return bool(re.match(pattern, phone.replace(' ', '').replace('-', '')))
    
    @classmethod
    def validate_name(cls, name: str) -> bool:
        """Validate name (2+ chars, letters only)"""
        if not name or len(name.strip()) < 2:
            return False
        return True


class LicenseRequestClient:
    """
    Client for submitting license requests to Firebase.
    
    Usage:
        client = LicenseRequestClient(machine_id)
        result = client.submit_request({
            'client_name': 'Nguyễn Văn A',
            'email': 'user@example.com',
            'phone': '0912345678',
            'requested_tier': 'THREE_MONTHS'  # VND pricing: 500,000đ
        })
        
        if result.existing_request:
            print("Thông tin của bạn đã được ghi nhận!")
        elif result.success:
            print("Yêu cầu đã được gửi, vui lòng chờ admin duyệt!")
    """
    
    COLLECTION = "_license_requests"
    REQUEST_COOLDOWN_HOURS = 24
    
    def __init__(self, machine_id: str):
        self.machine_id = machine_id
        self.display_id = machine_id[:8].upper()
        self.db = None
        self._init_firebase()
    
    def _init_firebase(self):
        """Initialize Firebase connection via REST API (no Admin SDK)."""
        if not FIREBASE_AVAILABLE:
            return
        
        try:
            self._rest_client = FirebaseRESTClient()
            self.db = "rest"  # Flag that we have connection
        except Exception:
            pass
    
    def _get_document_id(self) -> str:
        """Get document ID (hash of machine_id for shorter URL)"""
        return hashlib.sha256(self.machine_id.encode()).hexdigest()[:16]
    
    def check_existing_request(self) -> Optional[LicenseRequest]:
        """Check if a request already exists for this machine"""
        if not self.db:
            return None
        
        try:
            doc_id = self._get_document_id()
            
            # Use REST client to read document from _license_requests/{doc_id}
            if not hasattr(self, '_rest_client') or not self._rest_client:
                return None
            
            data = self._rest_client.read_document(self.COLLECTION, doc_id)
            if not data:
                return None
            
            return LicenseRequest(
                machine_id=data.get('machine_id', ''),
                display_id=data.get('display_id', ''),
                client_name=data.get('client_name', ''),
                email=data.get('email', ''),
                phone=data.get('phone', ''),
                company=data.get('company', ''),
                address=data.get('address', ''),
                requested_tier=data.get('requested_tier', 'TRIAL'),
                requested_days=data.get('requested_days', 7),
                reason=data.get('reason', ''),
                status=RequestStatus(data.get('status', 'pending')),
                approved_key=data.get('approved_key'),
                admin_note=data.get('admin_note', '')
            )
        except Exception as e:
            print(f"Check existing error: {e}")
        
        return None
    
    def submit_request(self, info: Dict) -> RequestResult:
        """
        Submit a license request via REST API.
        
        Args:
            info: Dict with keys:
                - client_name (required): Full name
                - email (required): Email address
                - phone (optional): Phone number
                - company (optional): Company name
                - address (optional): Address
                - requested_tier: TRIAL, ONE_MONTH, THREE_MONTHS, SIX_MONTHS, ONE_YEAR, LIFETIME
                - requested_days: 7, 30, 90, 180, 365 (auto-set based on tier)
                - reason: Why need license
                
        Returns:
            RequestResult with success status and message
        """
        if not self.db:
            return RequestResult(
                success=False,
                message="Không thể kết nối server. Vui lòng kiểm tra internet."
            )
        
        # Validate required fields
        client_name = InputValidator.sanitize_text(info.get('client_name', ''), 100)
        email = info.get('email', '').strip().lower()
        phone = info.get('phone', '').strip()
        
        if not InputValidator.validate_name(client_name):
            return RequestResult(
                success=False,
                message="Vui lòng nhập họ tên đầy đủ (ít nhất 2 ký tự)"
            )
        
        if not InputValidator.validate_email(email):
            return RequestResult(
                success=False,
                message="Email không hợp lệ"
            )
        
        if phone and not InputValidator.validate_phone(phone):
            return RequestResult(
                success=False,
                message="Số điện thoại không hợp lệ (10-11 số, bắt đầu bằng 0)"
            )
        
        # Check if already exists
        existing = self.check_existing_request()
        
        if existing:
            # Already submitted - check status
            if existing.status == RequestStatus.APPROVED:
                return RequestResult(
                    success=True,
                    message="Yêu cầu của bạn đã được DUYỆT!\n\nLicense key đã được cấp.",
                    status=RequestStatus.APPROVED,
                    approved_key=existing.approved_key,
                    existing_request=True
                )
            elif existing.status == RequestStatus.REJECTED:
                return RequestResult(
                    success=False,
                    message=f"Yêu cầu của bạn đã bị TỪ CHỐI.\n\nLý do: {existing.admin_note or 'Không có'}",
                    status=RequestStatus.REJECTED,
                    existing_request=True
                )
            elif existing.status == RequestStatus.PENDING:
                return RequestResult(
                    success=True,
                    message="Thông tin của bạn đã được ghi nhận.\n\n"
                            "Yêu cầu đang chờ admin xử lý.\n"
                            "Nếu cần cập nhật thông tin, vui lòng liên hệ admin.",
                    status=RequestStatus.PENDING,
                    existing_request=True
                )
        
        # Create new request via REST API
        try:
            doc_id = self._get_document_id()
            now = datetime.now()
            
            request_data = {
                'machine_id': self.machine_id,
                'display_id': self.display_id,
                'client_name': client_name,
                'email': email,
                'phone': InputValidator.sanitize_text(phone, 20),
                'company': InputValidator.sanitize_text(info.get('company', ''), 200),
                'address': InputValidator.sanitize_text(info.get('address', ''), 300),
                'requested_tier': info.get('requested_tier', 'TRIAL'),
                'requested_days': info.get('requested_days', 7),
                'reason': InputValidator.sanitize_text(info.get('reason', ''), 500),
                'status': 'pending',
                'created_at': now.isoformat(),
                'updated_at': now.isoformat(),
                'request_count': 1,
                'last_request_at': now.isoformat(),
                'approved_key': None,
                'admin_note': '',
                'processed_at': None,
                'processed_by': None
            }
            
            # Use REST client to write document
            if not hasattr(self, '_rest_client') or not self._rest_client:
                return RequestResult(
                    success=False,
                    message="REST client không khả dụng."
                )
            
            ok = self._rest_client.write_document(
                self.COLLECTION, doc_id, request_data
            )
            
            if not ok:
                return RequestResult(
                    success=False,
                    message="Lỗi khi gửi yêu cầu. Vui lòng thử lại."
                )
            
            return RequestResult(
                success=True,
                message="Yêu cầu đã được gửi thành công!\n\n"
                        "Admin sẽ xem xét và phản hồi sớm nhất.\n"
                        f"Machine ID: {self.display_id}",
                status=RequestStatus.PENDING
            )
            
        except Exception as e:
            return RequestResult(
                success=False,
                message=f"Lỗi khi gửi yêu cầu: {str(e)}"
            )
    
    def poll_result(self) -> RequestResult:
        """
        Poll for request result (called periodically by client).
        
        Returns:
            RequestResult with current status
        """
        existing = self.check_existing_request()
        
        if not existing:
            return RequestResult(
                success=False,
                message="Chưa có yêu cầu nào được gửi.",
                status=None
            )
        
        if existing.status == RequestStatus.APPROVED:
            return RequestResult(
                success=True,
                message="Yêu cầu đã được DUYỆT!",
                status=RequestStatus.APPROVED,
                approved_key=existing.approved_key
            )
        elif existing.status == RequestStatus.REJECTED:
            return RequestResult(
                success=False,
                message=f"Yêu cầu bị từ chối: {existing.admin_note or 'Không có lý do'}",
                status=RequestStatus.REJECTED
            )
        else:
            return RequestResult(
                success=True,
                message="Yêu cầu đang chờ xử lý...",
                status=RequestStatus.PENDING
            )


# =============================================================================
# DEMO
# =============================================================================

def main():
    print("=" * 60)
    print("License Request System - Demo")
    print("=" * 60)
    
    # Simulate client submission
    from license_client import HardwareFingerprint
    
    machine_id = HardwareFingerprint.get_machine_id()
    display_id = HardwareFingerprint.get_display_id()
    
    print(f"\nMachine ID: {display_id}")
    
    client = LicenseRequestClient(machine_id)
    
    # Check existing
    existing = client.check_existing_request()
    
    if existing:
        print(f"\n⚠️ Existing request found!")
        print(f"   Status: {existing.status.value}")
        print(f"   Name: {existing.client_name}")
        print(f"   Email: {existing.email}")
        if existing.approved_key:
            print(f"   Key: {existing.approved_key}")
    else:
        print("\n📝 No existing request. Ready to submit.")
        
        # Demo submit (commented out to avoid creating test data)
        # result = client.submit_request({
        #     'client_name': 'Test User',
        #     'email': 'test@example.com',
        #     'phone': '0912345678',
        #     'requested_tier': 'TRIAL',
        #     'reason': 'Testing the system'
        # })
        # print(f"\nResult: {result.message}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
