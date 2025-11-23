from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.functions.account import UpdateProfileRequest
from typing import Optional, Dict
from config import Config
from app.utils.encryption import encryption
import asyncio

class SessionManager:
    def __init__(self):
        self.active_clients: Dict[int, TelegramClient] = {}
    
    async def create_client(self, phone: str) -> TelegramClient:
        """Create a new Telegram client for login"""
        # Generate unique session name to avoid conflicts
        import uuid
        session_id = str(uuid.uuid4())[:8]
        
        # Use unique device info to avoid conflicts with existing Telegram sessions
        client = TelegramClient(
            StringSession(),
            Config.API_ID,
            Config.API_HASH,
            device_model=f"Ora Ads {session_id}",
            system_version="1.0",
            app_version="1.0"
        )
        
        # Connect and ensure connection is established
        await client.connect()
        
        # Verify connection
        if not client.is_connected():
            raise Exception("Failed to establish connection to Telegram")
        
        return client
    
    async def send_code(self, client: TelegramClient, phone: str, retry_count: int = 0) -> str:
        """Send OTP code to phone"""
        try:
            # Try to send code normally first
            result = await client.send_code_request(phone)
            return result.phone_code_hash
            
        except Exception as e:
            error_msg = str(e)
            
            # Specific error handling
            if "PHONE_NUMBER_INVALID" in error_msg:
                raise Exception("Invalid phone number format. Please use international format: +1234567890")
            
            elif "PHONE_NUMBER_BANNED" in error_msg:
                raise Exception("This phone number is banned from Telegram. Please use a different number.")
            
            elif "PHONE_NUMBER_FLOOD" in error_msg or "FLOOD" in error_msg:
                raise Exception("Too many attempts detected. Please wait 1-2 hours before trying again.")
            
            elif "PHONE_CODE_EXPIRED" in error_msg:
                raise Exception("Previous code expired. Please try again.")
            
            elif "SEND_CODE_UNAVAILABLE" in error_msg:
                raise Exception("Telegram code service temporarily unavailable. Please try again in 5-10 minutes.")
            
            elif "TIMEOUT" in error_msg.upper() or "TIMED OUT" in error_msg.upper():
                # Retry once on timeout
                if retry_count < 1:
                    await asyncio.sleep(3)
                    return await self.send_code(client, phone, retry_count + 1)
                raise Exception("Connection timeout. Please check your internet and try again.")
            
            elif "A wait of" in error_msg:
                # Extract wait time if present
                try:
                    wait_seconds = int(error_msg.split('A wait of ')[1].split(' seconds')[0])
                    wait_minutes = wait_seconds // 60
                    if wait_minutes > 0:
                        raise Exception(f"Rate limited. Please wait {wait_minutes} minutes and try again.")
                    else:
                        raise Exception(f"Rate limited. Please wait {wait_seconds} seconds and try again.")
                except:
                    raise Exception("Rate limited by Telegram. Please wait 5-10 minutes and try again.")
            
            elif "AUTH_KEY_PERM_EMPTY" in error_msg or "AUTH_KEY_DUPLICATED" in error_msg:
                # Session conflict errors
                raise Exception("Session conflict detected. This might happen if you're using the same account in multiple apps. Please wait 2-3 minutes and try again.")
            
            elif "SESSION_PASSWORD_NEEDED" in error_msg:
                raise Exception("2FA password required. Please provide your 2FA password.")
            
            elif "PHONE_CODE_INVALID" in error_msg or "CODE_INVALID" in error_msg:
                raise Exception("Invalid verification code. Please check and try again.")
            
            else:
                # Generic error with helpful message
                raise Exception(f"Unable to send verification code. This could be due to:\n"
                              f"• Telegram server issues\n"
                              f"• Rate limiting (wait 5-10 minutes)\n"
                              f"• Network connectivity\n"
                              f"• Session conflicts (using same account in multiple apps)\n\n"
                              f"Please try again shortly.")
    
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
            error_msg = str(e)
            
            # Handle specific authentication errors
            if "PHONE_CODE_EXPIRED" in error_msg or "confirmation code has expired" in error_msg.lower():
                raise Exception("The confirmation code has expired. Please request a new code.")
            elif "PHONE_CODE_INVALID" in error_msg or "invalid code" in error_msg.lower():
                raise Exception("Invalid verification code. Please check and try again.")
            elif "SESSION_PASSWORD_NEEDED" in error_msg:
                raise Exception("2FA password required. Please provide your 2FA password.")
            elif "AUTH_KEY_PERM_EMPTY" in error_msg or "AUTH_KEY_DUPLICATED" in error_msg:
                raise Exception("Session conflict detected. Please wait 2-3 minutes and try again.")
            elif "FLOOD_WAIT" in error_msg or "flood" in error_msg.lower():
                raise Exception("Too many attempts. Please wait 5-10 minutes before trying again.")
            else:
                raise Exception(f"Login failed: {error_msg}")
        
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
            
            # Create client with unique session parameters to avoid conflicts
            import uuid
            session_suffix = str(uuid.uuid4())[:8]
            
            client = TelegramClient(
                StringSession(decrypted_session),
                Config.API_ID,
                Config.API_HASH,
                device_model=f"Ora Ads {session_suffix}",
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

# Global instance
session_manager = SessionManager()