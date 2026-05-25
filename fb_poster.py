"""
fb_poster.py  —  Facebook Page Post via Graph API
--------------------------------------------------
Posts the teaser content to your Facebook Page.

Setup (one-time):
  1. Go to developers.facebook.com -> Your App -> Tools -> Graph API Explorer
  2. Select your App, select your Page from the dropdown
  3. Add permission: pages_manage_posts + pages_read_engagement
  4. Click "Generate Access Token" — copy it
  5. Add to .env:
       FACEBOOK_PAGE_ID=your_page_id
       FACEBOOK_ACCESS_TOKEN=your_page_access_token

Note: User tokens expire in 60 days. For permanent posting, generate a
Long-Lived Page Token (never expires) via:
  GET /oauth/access_token?grant_type=fb_exchange_token&...
"""

import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

FB_PAGE_ID    = os.getenv("FACEBOOK_PAGE_ID", "")
FB_PAGE_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
GRAPH_VERSION = "v19.0"


def post_to_facebook(message: str) -> dict:
    """
    Post a text message to the Facebook Page feed.

    Returns:
        dict: { success: bool, post_id: str or None, error: str or None }
    """
    if not FB_PAGE_ID or not FB_PAGE_TOKEN:
        return {
            "success": False,
            "post_id": None,
            "error": "FACEBOOK_PAGE_ID or FACEBOOK_ACCESS_TOKEN missing in .env",
        }

    if FB_PAGE_ID == "your-page-id" or FB_PAGE_TOKEN == "your-token":
        return {
            "success": False,
            "post_id": None,
            "error": "Placeholder credentials in .env — replace with real values",
        }

    endpoint = f"https://graph.facebook.com/{GRAPH_VERSION}/{FB_PAGE_ID}/feed"
    payload  = {
        "message":      message,
        "access_token": FB_PAGE_TOKEN,
    }

    try:
        resp = requests.post(endpoint, data=payload, timeout=15)
        data = resp.json()

        if resp.status_code == 200 and "id" in data:
            post_id = data["id"]
            logger.info(f"Facebook post published: {post_id}")
            print(f"  Facebook post ID: {post_id}")
            return {"success": True, "post_id": post_id, "error": None}
        else:
            error_msg = data.get("error", {}).get("message", resp.text[:300])
            logger.error(f"Facebook post failed: {error_msg}")
            return {"success": False, "post_id": None, "error": error_msg}

    except Exception as e:
        logger.error(f"Facebook post exception: {e}")
        return {"success": False, "post_id": None, "error": str(e)}


def check_page_token() -> bool:
    """Verify the page token is valid by fetching page name."""
    if not FB_PAGE_ID or not FB_PAGE_TOKEN:
        print("FACEBOOK_PAGE_ID or FACEBOOK_ACCESS_TOKEN not set in .env")
        return False

    endpoint = f"https://graph.facebook.com/{GRAPH_VERSION}/{FB_PAGE_ID}"
    try:
        resp = requests.get(endpoint, params={"access_token": FB_PAGE_TOKEN,
                                               "fields": "name,id"}, timeout=10)
        data = resp.json()
        if "name" in data:
            print(f"Page token OK — Page: {data['name']} (ID: {data['id']})")
            return True
        else:
            err = data.get("error", {}).get("message", "Unknown error")
            print(f"Token invalid: {err}")
            return False
    except Exception as e:
        print(f"Token check failed: {e}")
        return False


# ── CLI TEST ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("=" * 50)
    print("Facebook Poster — Token Check")
    print("=" * 50)
    print(f"Page ID : {FB_PAGE_ID or '(NOT SET)'}")
    print(f"Token   : {'(set)' if FB_PAGE_TOKEN and FB_PAGE_TOKEN != 'your-token' else '(NOT SET)'}")
    print()

    if "--post" in sys.argv:
        print("Posting test message...")
        result = post_to_facebook(
            "PSX Bot test post — if you see this, Facebook integration is working!\n"
            "#PSX #Test"
        )
        if result["success"]:
            print(f"Posted successfully. ID: {result['post_id']}")
        else:
            print(f"Failed: {result['error']}")
    else:
        check_page_token()
        print("\nRun with --post to publish a test post.")
