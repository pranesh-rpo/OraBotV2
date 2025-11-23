from cryptography.fernet import Fernet
from config import Config
import base64
import hashlib

class Encryption:
    def __init__(self):
        # Ensure key is proper Fernet key format
        key = Config.ENCRYPTION_KEY
        if not key:
            raise ValueError("ENCRYPTION_KEY is required")
        
        # Convert key to bytes if it's a string
        if isinstance(key, str):
            key = key.encode()
        
        # Ensure key is exactly 32 bytes for Fernet
        if len(key) != 32:
            # Hash the key to get 32 bytes
            key = hashlib.sha256(key).digest()
        
        self.cipher = Fernet(base64.urlsafe_b64encode(key))
    
    def encrypt(self, data: str) -> str:
        """Encrypt string data"""
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt encrypted string"""
        return self.cipher.decrypt(encrypted_data.encode()).decode()

# Global instance
encryption = Encryption()