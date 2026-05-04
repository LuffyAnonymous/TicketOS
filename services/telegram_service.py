import os
from curl_cffi import requests
from config import ORDER_BOT_TOKEN, ORDER_CHAT_ID
import extensions as context

def send_telegram(message):
    if not ORDER_BOT_TOKEN or not ORDER_CHAT_ID:
        # Just log instead of crashing the whole thread if token is missing
        if context.state: context.state.log("Telegram Error: Token or Chat ID missing")
        return

    url = f"https://api.telegram.org/bot{ORDER_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ORDER_CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, data=payload, timeout=20)
        if r.status_code != 200:
            if context.state: context.state.log(f"Telegram failed: {r.status_code} | {r.text}")
        else:
            if context.state: context.state.log("Telegram alert sent successfully")
    except Exception as e:
        if context.state: context.state.log(f"Telegram Exception: {e}")
