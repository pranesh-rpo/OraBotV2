from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from typing import Optional, Dict
from config import Config
from app.utils.encryption import encryption
import asyncio

class SessionManager:
    def __init__(self):
        self.active_clients: Dict[int, TelegramClient] = {}
    
    async def create_client(self, phone: str) -> TelegramClient:
        """Create a new Telegram client for login"""
        client = TelegramClient(
            StringSession(),
            Config.API_ID,
            Config.API_HASH,
            device_model="Ora Ads System",
            system_version="1.0",
            app_version="1.0"
        )
        await client.connect()
        return client
    
    async def send_code(self, client: TelegramClient, phone: str) -> str:
        """Send OTP code to phone"""
        try:
            result = await client.send_code_request(phone)
            return result.phone_code_hash
        except Exception as e:
            raise Exception(f"Failed to send code: {str(e)}")
    
    async def sign_in(self, client: TelegramClient, phone: str, 
                      code: str, phone_code_hash: str, 
                      password: Optional[str] = None) -> tuple:
        """Sign in with code and optional 2FA"""
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                raise Exception("2FA_REQUIRED")
            await client.sign_in(password=password)
        except PhoneCodeInvalidError:
            raise Exception("Invalid OTP code")
        except Exception as e:
            raise Exception(f"Login failed: {str(e)}")
        
        # Get user info
        me = await client.get_me()
        
        # Update profile
        try:
            first_name = me.first_name.split()[0] if me.first_name else "User"
            new_name = f"{first_name} | Ora Ads"
            await client(UpdateProfileRequest(
                first_name=new_name,
                about="Powered By @OraAdbot"
            ))
        except:
            pass  # Profile update is optional
        
        # Get session string
        session_string = client.session.save()
        
        return session_string, me.first_name, me.id
    
    async def load_client(self, session_string: str, account_id: int) -> TelegramClient:
        """Load existing client from session string"""
        try:
            # Decrypt session
            decrypted_session = encryption.decrypt(session_string)
            
            client = TelegramClient(
                StringSession(decrypted_session),
                Config.API_ID,
                Config.API_HASH,
                device_model="Ora Ads System",
                system_version="1.0",
                app_version="1.0"
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                raise Exception("Session expired")
            
            self.active_clients[account_id] = client
            return client
            
        except Exception as e:
            raise Exception(f"Failed to load session: {str(e)}")
    
    async def get_dialogs(self, client: TelegramClient) -> list:
        """Get all groups the account has joined"""
        groups = []
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                groups.append({
                    'id': dialog.id,
                    'title': dialog.title,
                    'username': dialog.entity.username if hasattr(dialog.entity, 'username') else None
                })
        return groups
    
    def get_client(self, account_id: int) -> Optional[TelegramClient]:
        """Get active client by account ID"""
        return self.active_clients.get(account_id)
    
    async def disconnect_client(self, account_id: int):
        """Disconnect and remove client"""
        if account_id in self.active_clients:
            try:
                await self.active_clients[account_id].disconnect()
            except:
                pass
            del self.active_clients[account_id]
    
    async def disconnect_all(self):
        """Disconnect all active clients"""
        for account_id in list(self.active_clients.keys()):
            await self.disconnect_client(account_id)

# Import for profile update
from telethon.tl.functions.account import UpdateProfileRequest

# Global instance
session_manager = SessionManager()