import os
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

# =========================================================
# PLATFORM CONFIG
# =========================================================
PLATFORM_CONFIGS = {
    "LiveTicketGroup": {
        "enabled": True,
        "username": os.environ.get("LIVE_USERNAME", ""),
        "password": os.environ.get("LIVE_PASSWORD", ""),
        "login_url": "https://www.liveticketgroup.com/login",
        "next_chunk_url": "https://www.liveticketgroup.com/_next/static/chunks/9fe30054f439dbd7.js",
        "orders_base_url": "https://my.liveticketgroup.com/pages/content/index.aspx",
    },
    "Fanpass": {
        "enabled": False,
        "username": os.environ.get("FANPASS_USERNAME", ""),
        "password": os.environ.get("FANPASS_PASSWORD", ""),
        "login_url": "",
        "orders_url": "",
    },
    "Tixstock": {
        "enabled": False,
        "username": os.environ.get("TIXSTOCK_USERNAME", ""),
        "password": os.environ.get("TIXSTOCK_PASSWORD", ""),
        "login_url": "",
        "orders_url": "",
    },
    "FootballTicketNet": {
        "enabled": True,
        "username": os.environ.get("FOOTBALLTICKETNET_USERNAME", ""),
        "password": os.environ.get("FOOTBALLTICKETNET_PASSWORD", ""),
        "login_url": "https://www.footballticketnet.com/",
        "delivery_url": "https://www.footballticketnet.com/?action=delivery_info",
    },
}

ORDER_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ORDER_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

TICKETSHOP_USERNAME = os.environ.get("TICKETSHOP_USERNAME", "")
TICKETSHOP_PASSWORD = os.environ.get("TICKETSHOP_PASSWORD", "")

APP_TITLE = "TicketOS"
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
ACCESS_COOKIE_NAME = "ticketos_access_token"

# =========================================================
# CONFIGURATION VALIDATION
# =========================================================
validation_errors = []

if not JWT_SECRET or JWT_SECRET.strip() == "" or JWT_SECRET == "CHANGE-THIS-TO-A-LONG-RANDOM-SECRET":
    validation_errors.append("JWT_SECRET is required and must not be empty or set to the default insecure value.")

if not ADMIN_PASSWORD or ADMIN_PASSWORD.strip() == "" or ADMIN_PASSWORD == "admin123":
    validation_errors.append("ADMIN_PASSWORD is required and must not be empty or set to the default 'admin123'.")

if validation_errors:
    raise ValueError(
        "\n========================================================================\n"
        "CONFIG ERROR:\n" +
        "\n".join(f" - {err}" for err in validation_errors) +
        "\n\nPlease check your .env file and set these required variables securely."
        "\n========================================================================\n"
    )

# Warnings for optional configs
if not ORDER_BOT_TOKEN or not ORDER_CHAT_ID:
    print("[WARNING]: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing. Telegram alerts are disabled.")

if not TICKETSHOP_USERNAME or not TICKETSHOP_PASSWORD:
    print("[WARNING]: TICKETSHOP_USERNAME or TICKETSHOP_PASSWORD is missing. Ticketshop inventory checks will fail.")

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
TICKETSSHOP_RESULTS_FILE = os.path.join(BASE_DIR, "ticketsshop_check_results.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
ORDER_DETAILS_CACHE_FILE = os.path.join(BASE_DIR, "order_details_cache.json")
ORDER_STATUS_STATE_FILE = os.path.join(BASE_DIR, "order_status_state.json")
ORDER_STATUS_ALERTS_FILE = os.path.join(BASE_DIR, "order_status_alerts.json")

DEBUG_ORDERS_HTML = os.path.join(BASE_DIR, "debug_orders_page.html")
DEBUG_LOGIN_HTML = os.path.join(BASE_DIR, "debug_login_response.html")
DEBUG_CHUNK_JS = os.path.join(BASE_DIR, "debug_login_chunk.js")
DEBUG_ORDER_DETAILS_HTML = os.path.join(BASE_DIR, "debug_order_details.html")

LOGIN_STATE_TREE_RAW = '["",{"children":["(landing)",{"children":["login",{"children":["__PAGE__",{},null,null]},null,null]},null,null,true]},null,null]'
LOGIN_STATE_TREE_ENCODED = quote(LOGIN_STATE_TREE_RAW)

SENT_FOOTBALLTICKETNET_ORDERS_FILE = os.path.join(BASE_DIR, "sent_footballticketnet_orders.json")
FOOTBALLTICKETNET_STATE_FILE = os.path.join(BASE_DIR, "footballticketnet_state.json")

AUTO_CACHE_THREADS = 3
AUTO_CACHE_SLEEP_SECONDS = 0.8
