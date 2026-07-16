import base64
import os
from Crypto.Cipher import AES
from Crypto.Util import Counter

class CryptoProvider:
    """
    AES-256 encryption provider for Synthesus/Ghostkey.
    Uses Counter (CTR) mode for efficient streaming encryption without padding.
    """
    def __init__(self, key_str: str = "GhostkeySovereignVaultKey2026!!!"):
        # Ensure the key is exactly 32 bytes for AES-256
        self.key = key_str.encode('utf-8')[:32].ljust(32, b'\0')

    def encrypt(self, data: str) -> str:
        """Encrypts a string and returns a base64 encoded string with IV."""
        if not data:
            return ""
        # Generate a random 8-byte nonce
        nonce = os.urandom(8)
        ctr = Counter.new(64, prefix=nonce)
        cipher = AES.new(self.key, AES.MODE_CTR, counter=ctr)
        encrypted = cipher.encrypt(data.encode('utf-8'))
        # Result is nonce + encrypted_data
        combined = nonce + encrypted
        return base64.b64encode(combined).decode('utf-8')

    def decrypt(self, encrypted_base64: str) -> str:
        """Decrypts a base64 encoded string."""
        if not encrypted_base64:
            return ""
        try:
            combined = base64.b64decode(encrypted_base64)
            nonce = combined[:8]
            encrypted_data = combined[8:]
            ctr = Counter.new(64, prefix=nonce)
            cipher = AES.new(self.key, AES.MODE_CTR, counter=ctr)
            decrypted = cipher.decrypt(encrypted_data)
            return decrypted.decode('utf-8')
        except Exception:
            # Fallback for unencrypted data if needed during transition
            return encrypted_base64
