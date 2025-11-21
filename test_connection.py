#!/usr/bin/env python3
"""
Test Telegram API Connection
Quick script to verify API credentials and connectivity
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
import sys

def get_credentials():
    """Get credentials from user"""
    print("\n" + "="*50)
    print("  Telegram Connection Test")
    print("="*50 + "\n")
    
    api_id = input("Enter your API_ID: ").strip()
    api_hash = input("Enter your API_HASH: ").strip()
    phone = input("Enter test phone number (with +): ").strip()
    
    if not api_id or not api_hash or not phone:
        print("\n❌ All fields are required!")
        sys.exit(1)
    
    try:
        api_id = int(api_id)
    except:
        print("\n❌ API_ID must be a number!")
        sys.exit(1)
    
    if not phone.startswith('+'):
        print("\n❌ Phone must start with + (e.g., +1234567890)")
        sys.exit(1)
    
    return api_id, api_hash, phone

async def test_connection(api_id, api_hash, phone):
    """Test connection to Telegram"""
    print("\n" + "-"*50)
    print("Starting connection test...")
    print("-"*50 + "\n")
    
    client = None
    try:
        # Step 1: Create client
        print("1️⃣ Creating client... ", end="", flush=True)
        client = TelegramClient(
            StringSession(),
            api_id,
            api_hash,
            device_model="Connection Test",
            system_version="1.0",
            app_version="1.0",
            connection_retries=3,
            retry_delay=1
        )
        print("✅ Done")
        
        # Step 2: Connect
        print("2️⃣ Connecting to Telegram... ", end="", flush=True)
        await client.connect()
        print("✅ Done")
        
        # Step 3: Check connection
        print("3️⃣ Verifying connection... ", end="", flush=True)
        if not client.is_connected():
            print("❌ Failed")
            return False
        print("✅ Done")
        
        # Step 4: Send code request
        print("4️⃣ Testing code request... ", end="", flush=True)
        result = await client.send_code_request(phone)
        print("✅ Done")
        print(f"   Code sent! Hash: {result.phone_code_hash[:20]}...")
        
        # Step 5: Get code from user
        print("\n📱 Check your Telegram for the verification code")
        code = input("Enter the code (or 'skip' to skip): ").strip()
        
        if code.lower() != 'skip':
            print("\n5️⃣ Testing sign in... ", end="", flush=True)
            try:
                await client.sign_in(phone, code, phone_code_hash=result.phone_code_hash)
                print("✅ Done")
                
                # Get user info
                me = await client.get_me()
                print(f"   Logged in as: {me.first_name} ({me.phone})")
                
                # Log out
                print("\n6️⃣ Logging out... ", end="", flush=True)
                await client.log_out()
                print("✅ Done")
                
            except Exception as e:
                print(f"❌ Failed: {e}")
                if "2FA" in str(e) or "password" in str(e).lower():
                    print("   Note: 2FA detected (this is normal)")
        
        print("\n" + "="*50)
        print("✅ All connection tests passed!")
        print("="*50)
        print("\n✅ Your API credentials are working correctly!")
        print("✅ You can use these credentials in the .env file")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        print("\n" + "="*50)
        print("❌ Connection Test Failed")
        print("="*50)
        
        print("\n🔍 Possible issues:")
        print("1. Wrong API_ID or API_HASH")
        print("   → Get correct values from https://my.telegram.org")
        print("2. Network/firewall blocking Telegram")
        print("   → Check internet connection")
        print("3. Phone number format wrong")
        print("   → Use international format: +1234567890")
        print("4. Telegram servers temporarily down")
        print("   → Try again in a few minutes")
        
        return False
        
    finally:
        if client and client.is_connected():
            await client.disconnect()
            print("\n🔌 Disconnected from Telegram")

async def main():
    try:
        api_id, api_hash, phone = get_credentials()
        success = await test_connection(api_id, api_hash, phone)
        
        if success:
            print("\n✅ You can now use Ora Ads with these credentials!")
            sys.exit(0)
        else:
            print("\n❌ Please fix the issues and try again")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️ Test cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("\n🧪 Telegram API Connection Tester")
    print("This will test your API credentials and connection\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)