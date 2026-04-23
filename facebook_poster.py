"""
facebook_poster.py
------------------
Posts content to your Facebook Page using the Graph API.

Setup steps (do these ONCE):
1. Go to https://developers.facebook.com
2. Create an App → Business type
3. Add "Pages" product
4. Generate a Page Access Token with pages_manage_posts permission
5. Put your PAGE_ID and ACCESS_TOKEN in the .env file

Token refresh:
  - Short-lived tokens expire in 1 hour
  - Exchange for a long-lived token (60 days) using the steps in README
"""

import os
import requests
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

PAGE_ID      = os.getenv("FACEBOOK_PAGE_ID")
ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
GRAPH_URL    = "https://graph.facebook.com/v19.0"


def post_to_facebook(message: str, link: str = None) -> dict:
    """
    Post a text message to your Facebook Page.
    Optionally attach a link preview.
    Returns the API response dict.
    """
    if not PAGE_ID or not ACCESS_TOKEN:
        raise EnvironmentError("FACEBOOK_PAGE_ID and FACEBOOK_ACCESS_TOKEN must be set in .env")

    url     = f"{GRAPH_URL}/{PAGE_ID}/feed"
    payload = {
        "message":      message,
        "access_token": ACCESS_TOKEN,
    }
    if link:
        payload["link"] = link

    logger.info(f"📤 Posting to Facebook page (ID: {PAGE_ID})...")

    response = requests.post(url, data=payload, timeout=30)
    data     = response.json()

    if "id" in data:
        post_id = data["id"]
        logger.info(f"✅ Posted successfully! Post ID: {post_id}")
        logger.info(f"   View at: https://facebook.com/{post_id.replace('_', '/posts/')}")
        return {"success": True, "post_id": post_id, "timestamp": datetime.now().isoformat()}
    else:
        error = data.get("error", {})
        logger.error(f"❌ Facebook post failed: {error.get('message', 'Unknown error')}")
        return {"success": False, "error": error, "timestamp": datetime.now().isoformat()}


def verify_page_access() -> bool:
    """Test that your credentials work before posting."""
    if not PAGE_ID or not ACCESS_TOKEN:
        logger.error("Missing PAGE_ID or ACCESS_TOKEN in .env")
        return False

    url = f"{GRAPH_URL}/{PAGE_ID}"
    params = {
        "fields":       "name,fan_count,followers_count",
        "access_token": ACCESS_TOKEN,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if "name" in data:
            logger.info(f"✅ Connected to page: {data['name']}")
            logger.info(f"   Followers: {data.get('followers_count', 'N/A')}")
            return True
        else:
            logger.error(f"❌ Page verification failed: {data.get('error', {}).get('message')}")
            return False
    except Exception as e:
        logger.error(f"❌ Could not reach Facebook API: {e}")
        return False


def get_long_lived_token(app_id: str, app_secret: str, short_token: str) -> str:
    """
    Exchange a short-lived token for a long-lived token (60 days).
    Run this once to get your long-lived token and save it in .env
    """
    url = f"{GRAPH_URL}/oauth/access_token"
    params = {
        "grant_type":        "fb_exchange_token",
        "client_id":         app_id,
        "client_secret":     app_secret,
        "fb_exchange_token": short_token,
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    if "access_token" in data:
        token = data["access_token"]
        print(f"\n✅ Long-lived token (save this in .env):\n{token}\n")
        return token
    else:
        print(f"❌ Error: {data}")
        return ""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Facebook connection...")
    verify_page_access()