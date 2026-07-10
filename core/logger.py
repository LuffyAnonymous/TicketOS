import logging
import os
import time
from datetime import datetime
from config import BASE_DIR

log_file = os.path.join(BASE_DIR, "ticketos.log")

class DatabaseLoggingHandler(logging.Handler):
    """
    Custom logging Handler that writes formatted log records to the database DBAppEvent table.
    """
    def emit(self, record):
        try:
            from database import get_db, DBAppEvent
            db = get_db()
            if db:
                log_msg = record.getMessage()
                db.add(DBAppEvent(
                    level=record.levelname,
                    source=record.name,
                    message=log_msg
                ))
                db.commit()
                db.close()
        except:
            pass

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Clear existing handlers if any (to prevent duplicates during hot reloads)
if root_logger.hasHandlers():
    root_logger.handlers.clear()

formatter = logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s) %(message)s")

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# File handler
file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

# Database handler
db_handler = DatabaseLoggingHandler()
root_logger.addHandler(db_handler)

def get_logger(name):
    return logging.getLogger(name)

# =========================================================
# TELEGRAM ERROR ALERT SYSTEM WITH DEDUPLICATION
# =========================================================

# Cache of sent error hashes to prevent spam: { cache_key: timestamp_sent }
_sent_errors_cache = {}

def send_error_alert(error_type, message):
    """
    Sends a Telegram notification for serious errors.
    Suppresses alerts if the same error occurred in the last 15 minutes.
    """
    cache_key = f"{error_type}:{message}"
    now = time.time()
    
    if cache_key in _sent_errors_cache:
        last_sent = _sent_errors_cache[cache_key]
        if now - last_sent < 900:  # 15 minutes window
            return
            
    _sent_errors_cache[cache_key] = now
    
    alert_msg = (
        f"🚨 SYSTEM ERROR ALERT\n\n"
        f"Type: {error_type}\n"
        f"Message: {message}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    try:
        from services.telegram_service import send_telegram
        send_telegram(alert_msg)
    except Exception as e:
        print(f"Failed to send Telegram error alert: {e}")
