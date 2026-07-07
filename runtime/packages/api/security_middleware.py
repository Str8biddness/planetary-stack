# api/security_middleware.py
# Security middleware and input validation for Synthesus API
# Provides rate limiting, input sanitization, and validation

import re
import base64
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
import time


@dataclass
class SecurityConfig:
    """Security configuration for API validation."""
    max_image_size_bytes: int = 10 * 1024 * 1024  # 10MB
    max_audio_size_bytes: int = 50 * 1024 * 1024  # 50MB
    max_text_length: int = 10000
    allowed_image_types: List[str] = None
    allowed_audio_types: List[str] = None
    max_requests_per_minute: int = 60
    max_concurrent_uploads: int = 5
    
    def __post_init__(self):
        if self.allowed_image_types is None:
            self.allowed_image_types = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
        if self.allowed_audio_types is None:
            self.allowed_audio_types = ['audio/wav', 'audio/mp3', 'audio/ogg', 'audio/webm']


class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = {}
    
    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed under rate limit."""
        now = time.time()
        
        # Clean old entries
        if key in self.requests:
            self.requests[key] = [
                ts for ts in self.requests[key]
                if now - ts < self.window_seconds
            ]
        else:
            self.requests[key] = []
        
        # Check limit
        if len(self.requests[key]) >= self.max_requests:
            return False
        
        # Record request
        self.requests[key].append(now)
        return True
    
    def get_remaining(self, key: str) -> int:
        """Get remaining requests in current window."""
        now = time.time()
        
        if key not in self.requests:
            return self.max_requests
        
        # Clean old entries
        self.requests[key] = [
            ts for ts in self.requests[key]
            if now - ts < self.window_seconds
        ]
        
        return max(0, self.max_requests - len(self.requests[key]))


class SecurityValidator:
    """Input validation and sanitization for API endpoints."""
    
    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or SecurityConfig()
        self.rate_limiter = RateLimiter(
            max_requests=self.config.max_requests_per_minute,
            window_seconds=60
        )
        self.upload_tracker: Dict[str, int] = {}
    
    def validate_base64(self, data: str) -> tuple[bool, Optional[str], Optional[int]]:
        """
        Validate base64 string.
        Returns: (is_valid, sanitized_data, estimated_size_bytes)
        """
        if not data:
            return False, None, None
        
        # Remove data URI prefix if present
        if ',' in data:
            parts = data.split(',')
            if len(parts) != 2:
                return False, None, None
            data = parts[1]
        
        # Check base64 format
        if not re.match(r'^[A-Za-z0-9+/]*={0,2}$', data):
            return False, None, None
        
        # Check padding
        if len(data) % 4 != 0:
            return False, None, None
        
        # Try to decode
        try:
            decoded = base64.b64decode(data)
            return True, data, len(decoded)
        except Exception:
            return False, None, None
    
    def validate_image(self, image_data: str, mime_type: Optional[str] = None) -> Dict[str, Any]:
        """Validate image input."""
        errors = []
        
        is_valid, sanitized, size = self.validate_base64(image_data)
        
        if not is_valid:
            errors.append("Invalid base64 image data")
            return {"valid": False, "errors": errors}
        
        # Check size
        if size > self.config.max_image_size_bytes:
            errors.append(
                f"Image too large: {size / 1024 / 1024:.2f}MB exceeds "
                f"{self.config.max_image_size_bytes / 1024 / 1024}MB limit"
            )
        
        # Check MIME type
        if mime_type and mime_type not in self.config.allowed_image_types:
            errors.append(
                f"Unsupported image type: {mime_type}. "
                f"Allowed: {', '.join(self.config.allowed_image_types)}"
            )
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "sanitized": sanitized,
            "size_bytes": size
        }
    
    def validate_audio(self, audio_data: str, mime_type: Optional[str] = None) -> Dict[str, Any]:
        """Validate audio input."""
        errors = []
        
        is_valid, sanitized, size = self.validate_base64(audio_data)
        
        if not is_valid:
            errors.append("Invalid base64 audio data")
            return {"valid": False, "errors": errors}
        
        # Check size
        if size > self.config.max_audio_size_bytes:
            errors.append(
                f"Audio too large: {size / 1024 / 1024:.2f}MB exceeds "
                f"{self.config.max_audio_size_bytes / 1024 / 1024}MB limit"
            )
        
        # Check MIME type
        if mime_type and mime_type not in self.config.allowed_audio_types:
            errors.append(
                f"Unsupported audio type: {mime_type}. "
                f"Allowed: {', '.join(self.config.allowed_audio_types)}"
            )
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "sanitized": sanitized,
            "size_bytes": size
        }
    
    def validate_text(self, text: str) -> Dict[str, Any]:
        """Validate text input."""
        errors = []
        
        if not text or not isinstance(text, str):
            errors.append("Text must be a non-empty string")
            return {"valid": False, "errors": errors}
        
        # Check length
        if len(text) > self.config.max_text_length:
            errors.append(
                f"Text too long: {len(text)} chars exceeds "
                f"{self.config.max_text_length} limit"
            )
        
        # Check for suspicious patterns (basic XSS prevention)
        suspicious = [
            (r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', "Script tags"),
            (r'javascript:', "JavaScript protocol"),
            (r'on\w+\s*=', "Event handlers"),
            (r'<iframe', "Iframes"),
            (r'<object', "Objects"),
            (r'<embed', "Embeds"),
        ]
        
        for pattern, name in suspicious:
            if re.search(pattern, text, re.IGNORECASE):
                errors.append(f"Potentially dangerous content detected: {name}")
                break
        
        # Sanitize - remove control characters except newlines
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text).strip()
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "sanitized": sanitized
        }
    
    def validate_url(self, url: str, allowed_schemes: List[str] = None) -> Dict[str, Any]:
        """Validate external URL."""
        errors = []
        
        if allowed_schemes is None:
            allowed_schemes = ['https']
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            
            # Check scheme
            scheme = parsed.scheme
            if scheme not in allowed_schemes:
                errors.append(
                    f"URL scheme not allowed: {scheme}. "
                    f"Allowed: {', '.join(allowed_schemes)}"
                )
            
            # Block private IPs
            hostname = parsed.hostname
            if hostname:
                if hostname in ['localhost', '127.0.0.1']:
                    errors.append("Private network URLs not allowed")
                elif hostname.startswith(('192.168.', '10.', '172.16.', '172.17.', 
                                          '172.18.', '172.19.', '172.20.', '172.21.',
                                          '172.22.', '172.23.', '172.24.', '172.25.',
                                          '172.26.', '172.27.', '172.28.', '172.29.',
                                          '172.30.', '172.31.')):
                    errors.append("Private network URLs not allowed")
        
        except Exception as e:
            errors.append(f"Invalid URL: {str(e)}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    def check_rate_limit(self, client_key: str) -> Dict[str, Any]:
        """Check rate limit for client."""
        allowed = self.rate_limiter.is_allowed(client_key)
        remaining = self.rate_limiter.get_remaining(client_key)
        
        return {
            "allowed": allowed,
            "remaining": remaining,
            "reset_in_seconds": 60
        }
    
    def track_upload_start(self, session_id: str) -> bool:
        """Track upload start, returns False if over limit."""
        current = self.upload_tracker.get(session_id, 0)
        if current >= self.config.max_concurrent_uploads:
            return False
        
        self.upload_tracker[session_id] = current + 1
        return True
    
    def track_upload_end(self, session_id: str):
        """Track upload completion."""
        current = self.upload_tracker.get(session_id, 0)
        if current > 0:
            self.upload_tracker[session_id] = current - 1
    
    def validate_multimodal_query(self, query: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Validate complete multimodal query."""
        errors = []
        sanitized = {}
        
        # Check concurrent uploads
        if not self.track_upload_start(session_id):
            errors.append(
                f"Too many concurrent uploads: "
                f"{self.config.max_concurrent_uploads} allowed"
            )
            return {"valid": False, "errors": errors}
        
        try:
            # Validate text
            if query.get("text"):
                result = self.validate_text(query["text"])
                if not result["valid"]:
                    errors.extend(result["errors"])
                else:
                    sanitized["text"] = result["sanitized"]
            
            # Validate image
            if query.get("base64Image"):
                result = self.validate_image(
                    query["base64Image"],
                    query.get("imageMimeType")
                )
                if not result["valid"]:
                    errors.extend(result["errors"])
                else:
                    sanitized["base64Image"] = result["sanitized"]
            
            if query.get("imageUrl"):
                result = self.validate_url(query["imageUrl"])
                if not result["valid"]:
                    errors.extend(result["errors"])
            
            # Validate audio
            if query.get("base64Audio"):
                result = self.validate_audio(
                    query["base64Audio"],
                    query.get("audioMimeType")
                )
                if not result["valid"]:
                    errors.extend(result["errors"])
                else:
                    sanitized["base64Audio"] = result["sanitized"]
            
            if query.get("audioUrl"):
                result = self.validate_url(query["audioUrl"])
                if not result["valid"]:
                    errors.extend(result["errors"])
        
        finally:
            # Always decrement upload tracker
            self.track_upload_end(session_id)
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "sanitized": sanitized if sanitized else None
        }


# Global validator instance
_validator: Optional[SecurityValidator] = None


def get_validator(config: Optional[SecurityConfig] = None) -> SecurityValidator:
    """Get or create global security validator."""
    global _validator
    if _validator is None:
        _validator = SecurityValidator(config)
    return _validator


def reset_validator():
    """Reset global validator (useful for testing)."""
    global _validator
    _validator = None
