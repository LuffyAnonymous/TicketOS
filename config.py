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
        "username": os.environ.get("LIVE_USERNAME") or os.environ.get("LTG_USERNAME") or "",
        "password": os.environ.get("LIVE_PASSWORD") or os.environ.get("LTG_PASSWORD") or "",
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
        "username": os.environ.get("FOOTBALLTICKETNET_USERNAME") or os.environ.get("FTN_USERNAME") or "",
        "password": os.environ.get("FOOTBALLTICKETNET_PASSWORD") or os.environ.get("FTN_PASSWORD") or "",
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

DATA_DIR = os.environ.get("DATA_DIR")
if not DATA_DIR:
    DATA_DIR = os.path.join(BASE_DIR, "data")

# Ensure required directories exist
os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "state"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "exports"), exist_ok=True)

# Safe data migration helper
def migrate_existing_data(data_dir, base_dir):
    import shutil
    # 1. SQLite database
    old_db = os.path.join(base_dir, "order_ticket_db.sqlite")
    new_db = os.path.join(data_dir, "order_ticket_db.sqlite")
    if os.path.exists(old_db) and not os.path.exists(new_db):
        print(f"[DATA MIGRATION]: Moving SQLite database to secure data directory...")
        try:
            shutil.copy2(old_db, new_db)
            print("[DATA MIGRATION]: SQLite database migrated successfully.")
        except Exception as e:
            print(f"[DATA MIGRATION ERROR]: Failed to migrate database: {e}")

    # 2. State and setting JSON files
    state_files = [
        ("combined_alert_settings.json", os.path.join(data_dir, "state", "combined_alert_settings.json")),
        ("seen_orders.json", os.path.join(data_dir, "state", "seen_orders.json")),
        ("platform_states.json", os.path.join(data_dir, "state", "platform_states.json")),
        ("sent_orders.json", os.path.join(data_dir, "state", "sent_orders.json")),
        ("sent_footballticketnet_orders.json", os.path.join(data_dir, "state", "sent_footballticketnet_orders.json")),
        ("footballticketnet_state.json", os.path.join(data_dir, "state", "footballticketnet_state.json")),
        ("ticketsshop_check_results.json", os.path.join(data_dir, "state", "ticketsshop_check_results.json")),
        ("ticketsshop_state.json", os.path.join(data_dir, "state", "ticketsshop_state.json")),
        ("order_details_cache.json", os.path.join(data_dir, "state", "order_details_cache.json")),
        ("order_status_state.json", os.path.join(data_dir, "state", "order_status_state.json")),
        ("order_status_alerts.json", os.path.join(data_dir, "state", "order_status_alerts.json")),
        ("users.json", os.path.join(data_dir, "state", "users.json"))
    ]
    for old_name, new_path in state_files:
        old_path = os.path.join(base_dir, old_name)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            print(f"[DATA MIGRATION]: Migrating {old_name}...")
            try:
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                shutil.copy2(old_path, new_path)
            except Exception as e:
                print(f"[DATA MIGRATION ERROR]: Failed to migrate {old_name}: {e}")

# Run data migration immediately on module load
migrate_existing_data(DATA_DIR, BASE_DIR)

DATABASE_FILE = os.path.join(DATA_DIR, "order_ticket_db.sqlite")
LOG_FILE = os.path.join(DATA_DIR, "logs", "ticketos.log")

SETTINGS_FILE = os.path.join(DATA_DIR, "state", "combined_alert_settings.json")
ORDER_SEEN_FILE = os.path.join(DATA_DIR, "state", "seen_orders.json")
ORDER_STATE_FILE = os.path.join(DATA_DIR, "state", "platform_states.json")
SENT_ORDERS_FILE = os.path.join(DATA_DIR, "state", "sent_orders.json")
TICKETSSHOP_RESULTS_FILE = os.path.join(DATA_DIR, "state", "ticketsshop_check_results.json")
TICKETSSHOP_STATE_FILE = os.path.join(DATA_DIR, "state", "ticketsshop_state.json")
USERS_FILE = os.path.join(DATA_DIR, "state", "users.json")
ORDER_DETAILS_CACHE_FILE = os.path.join(DATA_DIR, "state", "order_details_cache.json")
ORDER_STATUS_STATE_FILE = os.path.join(DATA_DIR, "state", "order_status_state.json")
ORDER_STATUS_ALERTS_FILE = os.path.join(DATA_DIR, "state", "order_status_alerts.json")

DEBUG_ORDERS_HTML = os.path.join(DATA_DIR, "state", "debug_orders_page.html")
DEBUG_LOGIN_HTML = os.path.join(DATA_DIR, "state", "debug_login_response.html")
DEBUG_CHUNK_JS = os.path.join(DATA_DIR, "state", "debug_login_chunk.js")
DEBUG_ORDER_DETAILS_HTML = os.path.join(DATA_DIR, "state", "debug_order_details.html")

LOGIN_STATE_TREE_RAW = '["",{"children":["(landing)",{"children":["login",{"children":["__PAGE__",{},null,null]},null,null]},null,null,true]},null,null]'
LOGIN_STATE_TREE_ENCODED = quote(LOGIN_STATE_TREE_RAW)

SENT_FOOTBALLTICKETNET_ORDERS_FILE = os.path.join(DATA_DIR, "state", "sent_footballticketnet_orders.json")
FOOTBALLTICKETNET_STATE_FILE = os.path.join(DATA_DIR, "state", "footballticketnet_state.json")


AUTO_CACHE_THREADS = 3
AUTO_CACHE_SLEEP_SECONDS = 0.8
