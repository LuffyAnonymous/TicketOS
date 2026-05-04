import json
import os
import threading
from datetime import datetime
from database import get_db, DBOrder, DBPlatform, DBAppEvent
from config import SETTINGS_FILE

class AppState:
    def __init__(self):
        self.running = False
        self.logs = []
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.settings = self.load_settings()

    def log(self, msg):
        entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        self.logs.append(entry)
        if len(self.logs) > 1000: self.logs.pop(0)
        print(entry)

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                try: return json.load(f)
                except: return {}
        return {}

    def save_settings(self):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self.settings, f, indent=2)

    def load_seen_orders(self):
        db = get_db()
        if not db: return set()
        try:
            return {r.order_number for r in db.query(DBOrder.order_number).all()}
        except: return set()
        finally: db.close()

    def summary(self):
        db = get_db()
        if not db: return {"running": self.running, "order_count": 0}
        try:
            # Total orders: Active non-cancelled non-past
            q = db.query(DBOrder).filter(DBOrder.normalized_status != "cancelled", DBOrder.is_past_event == False)
            total = q.count()
            pending = q.filter(DBOrder.normalized_status == "pending").count()
            cancelled = db.query(DBOrder).filter(DBOrder.normalized_status == "cancelled").count()
            resold = q.filter(DBOrder.normalized_status == "resold").count()
            processed = q.filter(DBOrder.normalized_status == "completed").count()
            return {
                "running": self.running, "order_count": total, "pending_count": pending,
                "cancelled_count": cancelled, "resold_count": resold, "processed_count": processed,
                "settings": self.settings
            }
        except: return {"running": self.running, "order_count": 0}
        finally: db.close()

    def get_all_active_orders(self):
        db = get_db()
        if not db: return []
        try:
            orders = db.query(DBOrder).filter(DBOrder.is_past_event == False).order_by(DBOrder.id.desc()).all()
            return [{
                "id": o.id, "order_number": o.order_number, "platform": o.platform, "event_name": o.event_name or "-",
                "event_date": o.event_date.strftime("%Y-%m-%d %H:%M:%S") if o.event_date else "-",
                "customer_name": o.customer_name or "-", "quantity": o.quantity or 1,
                "total_value": str(o.total_value or 0), "currency": o.currency or "£",
                "normalized_status": o.normalized_status or "pending", "sale_date": o.sale_date.strftime("%Y-%m-%d %H:%M:%S") if o.sale_date else "-"
            } for o in orders]
        except: return []
        finally: db.close()

    def set_last_check(self):
        self.settings["last_check_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_settings()
