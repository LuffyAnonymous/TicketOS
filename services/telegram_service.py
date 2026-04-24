from curl_cffi import requests
from config import ORDER_BOT_TOKEN, ORDER_CHAT_ID
import extensions as context

def send_telegram(message):
    if not ORDER_BOT_TOKEN or not ORDER_CHAT_ID:
        raise RuntimeError("Order Telegram token/chat_id is missing")

    url = f"https://api.telegram.org/bot{ORDER_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ORDER_CHAT_ID, "text": message, "disable_web_page_preview": True}
    r = requests.post(url, data=payload, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram failed: {r.status_code} | {r.text}")
    context.state.log("Telegram sent successfully")


