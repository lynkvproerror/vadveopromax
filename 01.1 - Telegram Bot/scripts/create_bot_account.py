"""
One-time Setup: Create Bot Firebase Auth Account
=================================================
Run this script ONCE on admin machine (where Admin SDK is available).

Usage:
    cd "01 - ADMIN - License Security"
    python "001 - Telegram Bot/scripts/create_bot_account.py"

This creates a Firebase Auth user for the bot with custom claims.
Save the output email/password for Vercel environment variables.
"""

import secrets
import string
import sys
import os

# Ensure parent dir is in path for firebase imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

BOT_EMAIL = "veo-bot@system.local"


def generate_password(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main():
    print("=" * 60)
    print("  VEO License Bot — Firebase Auth Account Setup")
    print("=" * 60)

    try:
        import firebase_admin
        from firebase_admin import auth, credentials as fb_credentials
    except ImportError:
        print("❌ firebase-admin not installed. Run: pip install firebase-admin")
        return

    # Connect to Firebase using discovered credentials
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from firebase_config import _discover_credentials

        creds = _discover_credentials()
        if not creds:
            print("❌ No Firebase credentials found")
            return

        # Initialize default app with primary credentials
        cred_path = str(creds[0]["path"])
        project_id = creds[0]["project_id"]

        try:
            firebase_admin.get_app()
        except ValueError:
            cred = fb_credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)

        print(f"✅ Connected to Firebase ({project_id})")
    except Exception as e:
        print(f"❌ Firebase connection failed: {e}")
        return

    password = generate_password()

    # Check if user already exists
    try:
        existing = auth.get_user_by_email(BOT_EMAIL)
        print(f"⚠️  User already exists: {existing.uid}")
        print(f"   Updating password...")
        auth.update_user(existing.uid, password=password)
        uid = existing.uid
    except auth.UserNotFoundError:
        # Create new user
        user = auth.create_user(
            email=BOT_EMAIL,
            password=password,
            display_name="VEO License Bot",
            disabled=False,
        )
        uid = user.uid
        print(f"✅ Created user: {uid}")

    # Set custom claims
    auth.set_custom_user_claims(uid, {"role": "bot", "level": 3})
    print(f"✅ Custom claims set: role=bot, level=3")

    # Generate webhook secret
    webhook_secret = secrets.token_hex(16)
    cron_secret = secrets.token_hex(16)

    print()
    print("=" * 60)
    print("  📋 SAVE THESE VALUES → Vercel Environment Variables")
    print("=" * 60)
    print()
    print(f"  FIREBASE_BOT_EMAIL     = {BOT_EMAIL}")
    print(f"  FIREBASE_BOT_PASSWORD  = {password}")
    print(f"  BOT_UID (for rules)    = {uid}")
    print(f"  WEBHOOK_SECRET         = {webhook_secret}")
    print(f"  CRON_SECRET            = {cron_secret}")
    print()
    print("⚠️  Lưu lại ngay! Password không thể xem lại sau này.")
    print()

    # Also write to local .env file for reference
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env.generated")
    try:
        with open(env_path, "w") as f:
            f.write(f"# Generated at {__import__('datetime').datetime.now().isoformat()}\n")
            f.write(f"# DO NOT COMMIT THIS FILE!\n\n")
            f.write(f"FIREBASE_BOT_EMAIL={BOT_EMAIL}\n")
            f.write(f"FIREBASE_BOT_PASSWORD={password}\n")
            f.write(f"BOT_UID={uid}\n")
            f.write(f"WEBHOOK_SECRET={webhook_secret}\n")
            f.write(f"CRON_SECRET={cron_secret}\n")
        print(f"📁 Saved to: {os.path.abspath(env_path)}")
    except Exception as e:
        print(f"⚠️  Could not save .env file: {e}")

    print()
    print("📌 Next steps:")
    print("   1. Add these values to Vercel Environment Variables")
    print("   2. Update Firebase Security Rules with BOT_UID")
    print("   3. Deploy: vercel deploy")
    print("   4. Set Telegram webhook:")
    print(f"      curl 'https://api.telegram.org/bot<TOKEN>/setWebhook?")
    print(f"           url=https://<app>.vercel.app/api/webhook/{webhook_secret}&")
    print(f"           secret_token={webhook_secret}'")


if __name__ == "__main__":
    main()
