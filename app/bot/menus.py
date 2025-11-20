from config import Config

def welcome_message(user_name: str) -> str:
    return f"""
👋 <b>Welcome to Ora Ads, {user_name}!</b>

🚀 The most advanced Telegram Auto-Broadcast System

<b>What can I do?</b>
✅ Link multiple Telegram accounts
✅ Auto-broadcast to all joined groups
✅ Smart scheduling & randomization
✅ Anti-spam protection
✅ Full activity logs

<i>Please choose an option below to get started!</i>
"""

def verification_message() -> str:
    return f"""
🔒 <b>Verification Required</b>

To use Ora Ads, you must join our official channel:

👉 {Config.VERIFICATION_CHANNEL}

<b>Why?</b>
• Stay updated with new features
• Get important announcements
• Access premium support

Click the button below to join!
"""

def about_message() -> str:
    return """
<b>📢 About Ora Ads</b>

Ora Ads is a next-generation Telegram automation tool designed for responsible advertising and intelligent broadcasting.

<b>🎯 What We Provide:</b>
• Safe automation using real accounts
• Randomized & human-like messaging
• Clean UI with Dashboard controls
• Strong compliance with Telegram limitations
• Zero data sharing to third parties

<b>💡 Why Ora Ads?</b>
• Built for performance
• Designed for long-term account safety
• Fully modular architecture
• Scales from single user → 100+ accounts

<b>🔧 Technology Stack:</b>
• Python 3.11+
• Telethon (Account automation)
• Advanced Anti-Spam System
• Secure Database Storage

<i>Ora Ads - Broadcast Smarter, Not Harder</i>
"""

def privacy_message() -> str:
    return """
<b>🔒 Privacy Policy</b>

Your privacy and security are our top priorities.

<b>What We Store:</b>
✅ Encrypted session data (required for operation)
✅ Broadcast activity logs
✅ Account settings & preferences

<b>What We DON'T Store:</b>
❌ Plaintext Telegram passwords
❌ Your private messages
❌ Contact lists or personal chats

<b>Your Rights:</b>
• Delete your data anytime
• Full control over linked accounts
• No third-party data sharing
• Secure encrypted storage

<b>Security Measures:</b>
• End-to-end encryption for sessions
• Secure database with access controls
• Regular security audits
• GDPR compliant

<i>We only store what's necessary to make Ora Ads work for you.</i>
"""

def account_info_message(account: dict) -> str:
    status = "🟢 Active - Broadcasting" if account['is_broadcasting'] else "🔴 Inactive"
    return f"""
<b>📱 Account Dashboard</b>

<b>Phone:</b> <code>{account['phone_number']}</code>
<b>Status:</b> {status}
<b>Name:</b> {account.get('first_name', 'N/A')}
<b>Added:</b> {account['created_at'][:10]}

<b>Choose an action:</b>
"""

def link_account_start() -> str:
    return """
<b>🔗 Link New Account</b>

To link a new Telegram account, I'll need:
1️⃣ Your phone number (with country code)
2️⃣ OTP code from Telegram
3️⃣ 2FA password (if enabled)

<b>⚠️ Important:</b>
• Use format: +1234567890
• Your account will be renamed to: "FirstName | Ora Ads"
• Bio will be set to: "Powered By @OraAdbot"
• We'll fetch all your joined groups

<i>Send your phone number now (e.g., +919876543210)</i>
"""

def logs_message(logs: list) -> str:
    if not logs:
        return "<b>📊 Activity Logs</b>\n\n<i>No logs yet.</i>"
    
    log_text = "<b>📊 Activity Logs</b>\n\n"
    for log in logs[:20]:  # Show last 20 logs
        emoji = {
            "info": "ℹ️",
            "success": "✅",
            "error": "❌",
            "broadcast": "📢"
        }.get(log['status'], "📝")
        
        log_text += f"{emoji} <b>{log['log_type']}</b>\n"
        log_text += f"   {log['message']}\n"
        log_text += f"   <i>{log['timestamp'][:19]}</i>\n\n"
    
    return log_text