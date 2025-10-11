# config/security.py
from cryptography.fernet import Fernet
import os
import base64
from typing import Optional, Dict

class SecureConfigManager:
    def __init__(self):
        master_key = os.getenv('MASTER_ENCRYPTION_KEY')
        if not master_key:
            raise ValueError("MASTER_ENCRYPTION_KEY required")
        
        self.cipher = Fernet(master_key.encode())
    
    def encrypt_config(self, config: dict) -> dict:
        """Encrypt sensitive configuration values"""
        encrypted_config = config.copy()
        
        sensitive_fields = ['password', 'api_key', 'smtp_password', 'webhook_secret']
        
        for field in sensitive_fields:
            if field in config and config[field]:
                encrypted_config[field] = self.cipher.encrypt(
                    config[field].encode()
                ).decode()
                encrypted_config[f"{field}_encrypted"] = True
        
        return encrypted_config
    
    def decrypt_config(self, config: dict) -> dict:
        """Decrypt configuration for use"""
        decrypted_config = config.copy()
        
        for key, value in config.items():
            if key.endswith('_encrypted') and value:
                field_name = key.replace('_encrypted', '')
                if field_name in config:
                    try:
                        decrypted_config[field_name] = self.cipher.decrypt(
                            config[field_name].encode()
                        ).decode()
                    except:
                        decrypted_config[field_name] = ""
        
        return decrypted_config

def encrypt_password(password: str) -> str:
    """Utility function to encrypt password"""
    if not password:
        return ""
    
    manager = SecureConfigManager()
    return manager.cipher.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password: str) -> str:
    """Utility function to decrypt password"""
    if not encrypted_password:
        return ""
    
    manager = SecureConfigManager()
    try:
        return manager.cipher.decrypt(encrypted_password.encode()).decode()
    except:
        return ""

