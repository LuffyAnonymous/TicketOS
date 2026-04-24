import os
from urllib.parse import quote

# =========================================================
# PLATFORM CONFIG
# =========================================================
PLATFORM_CONFIGS = {
    "LiveTicketGroup": {
        "enabled": True,
        "username": "live@ticketsshop.co.uk",
        "password": "ClusterH105",
        "login_url": "https://www.liveticketgroup.com/login",
        "next_chunk_url": "https://www.liveticketgroup.com/_next/static/chunks/9fe30054f439dbd7.js",
        "orders_base_url": "https://my.liveticketgroup.com/pages/content/index.aspx",
    },
    "Fanpass": {
        "enabled": False,
        "username": "",
        "password": "",
        "login_url": "",
        "orders_url": "",
    },
    "Tixstock": {
        "enabled": False,
        "username": "",
        "password": "",
        "login_url": "",
        "orders_url": "",
    },
    "FootballTicketNet": {
        "enabled": False,
        "username": "",
        "password": "",
        "login_url": "https://www.footballticketnet.com/",
        "delivery_url": "https://www.footballticketnet.com/?action=delivery_info",
    },
}

ORDER_BOT_TOKEN = "8649315986:AAE4FwJGpFv4stvdPm6VxtvBEmOITYxlayU"
ORDER_CHAT_ID = "8365763849"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

APP_TITLE = "Sales & Order Notification"
JWT_SECRET = "CHANGE-THIS-TO-A-LONG-RANDOM-SECRET"
JWT_ALGORITHM = "HS256"
ACCESS_COOKIE_NAME = "orderdash_access_token"

INACTIVITY_MINUTES = 20
REMEMBER_DAYS = 30

# =========================================================
# FILES / CONSTANTS
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(BASE_DIR, "combined_alert_settings.json")
ORDER_SEEN_FILE = os.path.join(BASE_DIR, "seen_orders.json")
ORDER_STATE_FILE = os.path.join(BASE_DIR, "platform_states.json")
SENT_ORDERS_FILE = os.path.join(BASE_DIR, "sent_orders.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
ORDER_DETAILS_CACHE_FILE = os.path.join(BASE_DIR, "order_details_cache.json")

DEBUG_ORDERS_HTML = os.path.join(BASE_DIR, "debug_orders_page.html")
DEBUG_LOGIN_HTML = os.path.join(BASE_DIR, "debug_login_response.html")
DEBUG_CHUNK_JS = os.path.join(BASE_DIR, "debug_login_chunk.js")
DEBUG_ORDER_DETAILS_HTML = os.path.join(BASE_DIR, "debug_order_details.html")

LOGIN_STATE_TREE_RAW = '["",{"children":["(landing)",{"children":["login",{"children":["__PAGE__",{},null,null]},null,null]},null,null,true]},null,null]'
LOGIN_STATE_TREE_ENCODED = quote(LOGIN_STATE_TREE_RAW)

AUTO_CACHE_THREADS = 3
AUTO_CACHE_SLEEP_SECONDS = 0.8
