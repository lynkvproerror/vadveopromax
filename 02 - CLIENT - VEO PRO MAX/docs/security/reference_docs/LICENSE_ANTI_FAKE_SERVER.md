# 🔒 Anti-Fake-Server Protection

> Split from LICENSE_PROTECTION_SYSTEM.md

---

## Purpose

Prevent crackers from bypassing license by:
1. Spoofing the API server
2. Man-in-the-middle attacks
3. Replay attacks

---

## Protection Methods

| Method | Purpose |
|--------|---------|
| Certificate Pinning | Reject fake certificates |
| Response Signing (RSA) | Verify server identity |
| Challenge-Response | Prove server has private key |
| Time-Based Tokens | Prevent replay attacks |

---

## 1. Certificate Pinning

```python
class CertificatePinningAdapter(HTTPAdapter):
    # SHA256 fingerprint of Firebase/Google certificate
    PINNED_CERT_HASH = "GOOGLE_ROOT_CA_FINGERPRINT"
    
    def send(self, request, *args, **kwargs):
        response = super().send(request, *args, **kwargs)
        
        # Verify certificate after connection
        sock = response.raw._connection.sock
        cert_der = sock.getpeercert(binary_form=True)
        cert_hash = hashlib.sha256(cert_der).hexdigest()
        
        if cert_hash != self.PINNED_CERT_HASH:
            raise ssl.SSLError("Certificate pinning failed!")
        
        return response
```

---

## 2. Response Signing (RSA)

```python
class ResponseVerifier:
    # Public key embedded in app (server has private key)
    SERVER_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----..."""
    
    def verify_response(self, response_data: dict, signature: str) -> bool:
        payload = json.dumps(response_data, sort_keys=True)
        
        self.public_key.verify(
            base64.b64decode(signature),
            payload.encode(),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True  # If no exception, signature valid
```

**Flow:**
```
Server: response + signature = rsa_sign(response, private_key)
Client: verify(response, signature, public_key)
Fake server: Cannot sign without private key → FAIL
```

---

## 3. Challenge-Response

```python
class ChallengeResponseAuth:
    def generate_challenge(self) -> str:
        """Generate random challenge for server"""
        challenge = secrets.token_hex(32)
        self.pending[challenge] = time.time()
        return challenge
    
    def verify_solution(self, challenge: str, solution: str) -> bool:
        """Only real server can sign the challenge"""
        if challenge not in self.pending:
            return False
        if time.time() - self.pending[challenge] > 30:  # 30s timeout
            return False
        
        return self.verifier.verify_response({"challenge": challenge}, solution)
```

---

## 4. Time-Based Tokens (Anti-Replay)

```python
class TokenValidator:
    used_nonces = set()
    MAX_TOKEN_AGE = 60  # seconds
    
    @classmethod
    def validate_token(cls, token: str) -> dict:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"])
        
        # Check token age
        if time.time() - payload['iat'] > cls.MAX_TOKEN_AGE:
            return {"valid": False, "error": "Token too old"}
        
        # Check nonce not reused
        if payload['nonce'] in cls.used_nonces:
            return {"valid": False, "error": "Replay attack"}
        
        cls.used_nonces.add(payload['nonce'])
        return {"valid": True, ...}
```

---

## Complete Secure Activation

```python
class SecureActivation:
    def activate_secure(self, license_key: str, machine_id: str) -> dict:
        # 1. Generate challenge
        challenge = self.challenger.generate_challenge()
        
        # 2. Send request with challenge
        response = self.client.post(url, json={
            "key": license_key,
            "machine_id": machine_id,
            "challenge": challenge
        })
        
        # 3. Verify challenge solution (server identity)
        if not self.challenger.verify_solution(challenge, response['solution']):
            return {"error": "Server identity failed!"}
        
        # 4. Verify response signature (data integrity)
        if not self.verifier.verify_response(response['data'], response['sig']):
            return {"error": "Signature invalid!"}
        
        # 5. All passed!
        return {"success": True, "tier": response['data']['tier']}
```

---

## 5. Domain Pinning (Anti-DNS Hijack)

> [!WARNING]
> Prevents attackers from redirecting API requests to a fake server via DNS hijacking.

```python
import socket
import ssl

class DomainPinner:
    """
    Pin expected IP addresses for our domain.
    Detects DNS hijacking attempts.
    """
    
    # Expected IPs for api.veoauto.com (update if server changes)
    PINNED_IPS = [
        "35.190.27.1",
        "35.190.27.2",
        # Add backup IPs
    ]
    
    PINNED_DOMAIN = "api.veoauto.com"
    
    @classmethod
    def verify_domain(cls) -> bool:
        """Verify domain resolves to expected IP"""
        try:
            resolved_ips = socket.gethostbyname_ex(cls.PINNED_DOMAIN)[2]
            
            # Check if any resolved IP is in our pinned list
            for ip in resolved_ips:
                if ip in cls.PINNED_IPS:
                    return True
            
            # None of resolved IPs match → possible DNS hijack!
            return False
            
        except socket.gaierror:
            # DNS resolution failed - network issue
            return False
    
    @classmethod
    def get_secure_url(cls) -> str:
        """Get API URL, falling back to direct IP if DNS suspicious"""
        if cls.verify_domain():
            return f"https://{cls.PINNED_DOMAIN}"
        else:
            # Use direct IP with SNI
            return f"https://{cls.PINNED_IPS[0]}"
```

### Protection Summary

| Method | Purpose | Status |
|--------|---------|--------|
| Certificate Pinning | Reject fake certificates | ✅ |
| Response Signing (RSA) | Verify server identity | ✅ |
| Challenge-Response | Prove server has private key | ✅ |
| Time-Based Tokens | Prevent replay attacks | ✅ |
| **Domain Pinning** | **Detect DNS hijacking** | ✅ 🆕 |
