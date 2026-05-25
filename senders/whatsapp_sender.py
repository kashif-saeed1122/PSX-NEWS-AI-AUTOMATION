"""
whatsapp_sender.py
------------------
Sends WhatsApp messages via Twilio.

One-time setup:
  1. Create account at https://www.twilio.com (free trial included)
  2. From console dashboard copy your Account SID and Auth Token
  3. Go to Messaging > Try it out > Send a WhatsApp message
  4. From your phone WhatsApp, send "join <sandbox-code>" to +1 415 523 8886
     (the exact code is shown in the Twilio console page above)
  5. Add to .env:
       TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
       TWILIO_AUTH_TOKEN=your_auth_token
       TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
       WHATSAPP_TO=+923001234567

# ── PROVIDER 2: WhatsApp Business API / Meta (commented out) ──────
# When you want to switch to official Meta API (requires business verification):
#   1. Go to developers.facebook.com, create a WhatsApp Business App
#   2. Get your Phone Number ID and a temporary access token
#   3. Add to .env:
#        META_WA_TOKEN=your_meta_token
#        META_WA_PHONE_ID=your_phone_number_id
#   4. Uncomment _send_via_meta() below and set ACTIVE_PROVIDER = "meta"
"""

import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

ACTIVE_PROVIDER = "twilio"   # "twilio" | "meta"

# ── TWILIO CONFIG ────────────────────────────────────────────────
TWILIO_SID    = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM   = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
WHATSAPP_TO   = os.getenv("WHATSAPP_TO", "")

# ── META / WHATSAPP BUSINESS CONFIG ──────────────────────────────
META_WA_TOKEN    = os.getenv("META_WA_TOKEN", "")
META_WA_PHONE_ID = os.getenv("META_WA_PHONE_ID", "")


# ── HELPER ───────────────────────────────────────────────────────

def _split_message(text: str, max_len: int = 1500) -> list:
    """Split long messages at newline boundaries to fit within limits."""
    if len(text) <= max_len:
        return [text]
    chunks, current, current_len = [], [], 0
    for line in text.split("\n"):
        if current_len + len(line) + 1 > max_len and current:
            chunks.append("\n".join(current))
            current, current_len = [line], len(line)
        else:
            current.append(line)
            current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


# ── PROVIDER: TWILIO ─────────────────────────────────────────────

def _send_via_twilio(message: str, phone: str) -> dict:
    if not TWILIO_SID or not TWILIO_TOKEN:
        return {
            "success": False,
            "error": "TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN missing in .env",
        }
    try:
        import time
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        chunks = _split_message(message)
        sids = []
        to_number = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
        for i, chunk in enumerate(chunks, 1):
            msg = client.messages.create(
                from_=TWILIO_FROM,
                to=to_number,
                body=chunk,
            )
            sids.append(msg.sid)
            logger.info(
                f"Twilio part {i}/{len(chunks)} -> SID: {msg.sid} | "
                f"Status: {msg.status} | To: {to_number}"
            )
            print(f"  Part {i}/{len(chunks)} sent. SID: {msg.sid}  Status: {msg.status}")
            # Wait between parts so Twilio sandbox doesn't throttle
            if i < len(chunks):
                time.sleep(2)
        return {"success": True, "error": None, "parts_sent": len(sids), "sids": sids}
    except ImportError:
        return {"success": False, "error": "Run: pip install twilio"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── PROVIDER: META WHATSAPP BUSINESS ─────────────────────────────

def _send_via_meta(message: str, phone: str) -> dict:
    if not META_WA_TOKEN or not META_WA_PHONE_ID:
        return {"success": False, "error": "META_WA_TOKEN or META_WA_PHONE_ID missing in .env"}
    try:
        import time
        endpoint = f"https://graph.facebook.com/v19.0/{META_WA_PHONE_ID}/messages"
        headers = {
            "Authorization": f"Bearer {META_WA_TOKEN}",
            "Content-Type": "application/json",
        }
        to_number = phone.lstrip("+")
        chunks = _split_message(message)
        sids = []
        for i, chunk in enumerate(chunks, 1):
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "text",
                "text": {"body": chunk},
            }
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            if resp.status_code not in (200, 201):
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
            msg_id = resp.json().get("messages", [{}])[0].get("id", "N/A")
            sids.append(msg_id)
            logger.info(f"Meta part {i}/{len(chunks)} -> ID: {msg_id}")
            print(f"  Part {i}/{len(chunks)} sent. ID: {msg_id}")
            if i < len(chunks):
                time.sleep(1)
        return {"success": True, "error": None, "parts_sent": len(chunks), "sids": sids}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── PUBLIC API ───────────────────────────────────────────────────

def send_whatsapp(message: str, to: str = None) -> dict:
    """
    Send a WhatsApp message using the active provider.

    Args:
        message: Text to send. Supports WhatsApp markdown (*bold*, _italic_).
        to:      Recipient number e.g. +923001234567. Defaults to WHATSAPP_TO in .env.

    Returns:
        dict: { success: bool, error: str or None, parts_sent: int }
    """
    phone = (to or WHATSAPP_TO).strip()
    if not phone:
        return {"success": False, "error": "WHATSAPP_TO not set in .env"}

    if ACTIVE_PROVIDER == "twilio":
        return _send_via_twilio(message, phone)

    elif ACTIVE_PROVIDER == "meta":
        return _send_via_meta(message, phone)

    return {"success": False, "error": f"Unknown ACTIVE_PROVIDER: '{ACTIVE_PROVIDER}'"}


def send_analysis_to_whatsapp(formatted_message: str, to: str = None) -> bool:
    """Send a pre-formatted analysis message. Returns True on success."""
    logger.info(
        f"Sending to WhatsApp via [{ACTIVE_PROVIDER}] "
        f"({len(formatted_message)} chars) -> {to or WHATSAPP_TO}"
    )
    result = send_whatsapp(formatted_message, to=to)
    if result["success"]:
        print(f"[OK] WhatsApp sent ({result.get('parts_sent', 1)} part(s))")
        return True
    print(f"[ERROR] WhatsApp failed: {result['error']}")
    logger.error(f"WhatsApp send failed: {result['error']}")
    return False


def check_last_message_status():
    """
    Check the delivery status of the last sent Twilio message.
    Helps diagnose why a message wasn't received.
    """
    if ACTIVE_PROVIDER != "twilio":
        print("Status check only available for Twilio provider.")
        return
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        messages = client.messages.list(limit=5)
        if not messages:
            print("No messages found in Twilio account.")
            return
        print("\nLast 5 Twilio messages:")
        print("-" * 70)
        for m in messages:
            print(f"  SID    : {m.sid}")
            print(f"  To     : {m.to}")
            print(f"  From   : {m.from_}")
            print(f"  Status : {m.status}")   # queued / sent / delivered / failed / undelivered
            print(f"  Error  : {m.error_message or 'None'}")
            print(f"  Date   : {m.date_sent}")
            print()
    except Exception as e:
        print(f"Could not fetch status: {e}")


# ── CLI TEST ─────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 50)
    print(f"WhatsApp Sender — {ACTIVE_PROVIDER.upper()} Test")
    print("=" * 50)

    if ACTIVE_PROVIDER == "meta":
        print(f"Phone ID    : {META_WA_PHONE_ID or '(NOT SET)'}")
        print(f"Token       : {'(set)' if META_WA_TOKEN else '(NOT SET)'}")
        print(f"To          : {WHATSAPP_TO or '(NOT SET)'}")
        print()
        missing = []
        if not META_WA_TOKEN:    missing.append("META_WA_TOKEN")
        if not META_WA_PHONE_ID: missing.append("META_WA_PHONE_ID")
        if not WHATSAPP_TO:      missing.append("WHATSAPP_TO")
    else:
        print(f"Account SID : {TWILIO_SID[:10] + '...' if TWILIO_SID else '(NOT SET)'}")
        print(f"Auth Token  : {'(set)' if TWILIO_TOKEN else '(NOT SET)'}")
        print(f"From        : {TWILIO_FROM}")
        print(f"To          : {WHATSAPP_TO or '(NOT SET)'}")
        print()
        missing = []
        if not TWILIO_SID:    missing.append("TWILIO_ACCOUNT_SID")
        if not TWILIO_TOKEN:  missing.append("TWILIO_AUTH_TOKEN")
        if not WHATSAPP_TO:   missing.append("WHATSAPP_TO")

    if missing:
        print(f"Missing in .env: {', '.join(missing)}")
        print()
        print("Steps:")
        print("  1. Go to https://www.twilio.com and create an account")
        print("  2. From the console dashboard copy Account SID and Auth Token")
        print("  3. Go to Messaging > Try it out > Send a WhatsApp message")
        print("  4. Send 'join <sandbox-code>' from your WhatsApp to +1 415 523 8886")
        print("  5. Fill in .env and re-run this file")
    else:
        import sys
        if "--status" in sys.argv:
            check_last_message_status()
        else:
            print("Sending test message...")
            ok = send_analysis_to_whatsapp(
                "PSX Analysis Bot — Twilio test.\n"
                "If you received this, WhatsApp integration is working!"
            )
            print("Test passed!" if ok else "Test failed.")
            print()
            print("Checking delivery status...")
            check_last_message_status()
