import threading
from datetime import datetime
from config import SETTINGS_FILE, ORDER_SEEN_FILE, SENT_ORDERS_FILE
from core.storage import load_json_file, save_json_file, load_order_details_cache
from core.helpers import clean_text, is_event_expired

class AppState:
    def __init__(self):
        self.running = False
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.lock = threading.Lock()

        self.logs = []
        self.last_alert_time = "-"
        self.last_check_time = "-"
        self.last_order_info = "No order yet"
        self.session_status = "Unknown"

        self.current_order_rows = []
        self.settings = self.load_settings()
        self.sent_order_rows = self.load_sent_orders_history()
        self.sync_sent_orders_from_seen_file()

    def load_settings(self):
        default = {
            "interval_minutes": 30,
            "sleep_window_enabled": False,
        }
        saved = load_json_file(SETTINGS_FILE, default)
        if isinstance(saved, dict):
            default.update(saved)
        return default

    def save_settings(self):
        save_json_file(SETTINGS_FILE, self.settings)

    def log(self, message):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] {message}"
        with self.lock:
            self.logs.append(line)
            self.logs = self.logs[-500:]
        print(line)

    def set_last_check(self):
        self.last_check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def set_last_alert(self):
        self.last_alert_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def set_last_order(self, order_id, event_name, sale_date):
        self.last_order_info = f"ID: {order_id} | EVENT: {event_name} | SALE DATE: {sale_date}"

    def load_seen_orders(self):
        data = load_json_file(ORDER_SEEN_FILE, [])
        if isinstance(data, list):
            return set(str(x).strip() for x in data if str(x).strip())
        return set()

    def save_seen_orders(self, seen_orders):
        save_json_file(ORDER_SEEN_FILE, sorted(list(seen_orders)))

    def load_sent_orders_history(self):
        data = load_json_file(SENT_ORDERS_FILE, [])
        rows = []
        if isinstance(data, list):
            for row in data:
                if not isinstance(row, dict):
                    continue
                
                order_id = clean_text(row.get("id", ""))
                if not order_id:
                    continue
                
                rows.append({
                    "id": order_id,
                    "customer": clean_text(row.get("customer", "Unknown")) or "Unknown",
                    "status": clean_text(row.get("status", "Unknown")) or "Unknown",
                    "sale_date": clean_text(row.get("sale_date", "Unknown")) or "Unknown",
                    "event_date": clean_text(row.get("event_date", "Unknown")) or "Unknown",
                    "event": clean_text(row.get("event", "Previously sent order")) or "Previously sent order",
                    "source": clean_text(row.get("source", "Unknown")) or "Unknown",
            })
        return rows

    def save_sent_orders_history(self):
        unique_rows = []
        seen_ids = set()

        for row in self.sent_order_rows:
            unique_key = f"{clean_text(row.get('source',''))}::{clean_text(row.get('id',''))}"
            if not unique_key or unique_key in seen_ids:
                continue

            seen_ids.add(unique_key)
            unique_rows.append({
                "id": clean_text(row.get("id", "")),
                "customer": clean_text(row.get("customer", "Unknown")) or "Unknown",
                "status": clean_text(row.get("status", "Unknown")) or "Unknown",
                "sale_date": clean_text(row.get("sale_date", "Unknown")) or "Unknown",
                "event_date": clean_text(row.get("event_date", "Unknown")) or "Unknown",
                "event": clean_text(row.get("event", "Previously sent order")) or "Previously sent order",
                "source": clean_text(row.get("source", "Unknown")) or "Unknown",
            })

        self.sent_order_rows = unique_rows
        save_json_file(SENT_ORDERS_FILE, self.sent_order_rows)

    def upsert_sent_order_row(self, row_data):
        unique_key = f"{clean_text(row_data.get('source',''))}::{clean_text(row_data.get('id',''))}"
        if not unique_key:
            return
    
        for row in self.sent_order_rows:
            row_key = f"{clean_text(row.get('source',''))}::{clean_text(row.get('id',''))}"
            if row_key == unique_key:
                row["customer"] = clean_text(row_data.get("customer", row.get("customer", "Unknown"))) or "Unknown"
                row["status"] = clean_text(row_data.get("status", row.get("status", "Unknown"))) or "Unknown"
                row["sale_date"] = clean_text(row_data.get("sale_date", row.get("sale_date", "Unknown"))) or "Unknown"
                row["event_date"] = clean_text(row_data.get("event_date", row.get("event_date", "Unknown"))) or "Unknown"
                row["event"] = clean_text(row_data.get("event", row.get("event", "Previously sent order"))) or "Previously sent order"
                row["source"] = clean_text(row_data.get("source", row.get("source", "Unknown"))) or "Unknown"
                self.save_sent_orders_history()
                return
    
        self.sent_order_rows.insert(0, {
            "id": clean_text(row_data.get("id", "")),
            "customer": clean_text(row_data.get("customer", "Unknown")) or "Unknown",
            "status": clean_text(row_data.get("status", "Unknown")) or "Unknown",
            "sale_date": clean_text(row_data.get("sale_date", "Unknown")) or "Unknown",
            "event_date": clean_text(row_data.get("event_date", "Unknown")) or "Unknown",
            "event": clean_text(row_data.get("event", "Previously sent order")) or "Previously sent order",
            "source": clean_text(row_data.get("source", "Unknown")) or "Unknown",
        })
        self.save_sent_orders_history()

    def sync_sent_orders_from_seen_file(self):
        seen_ids = self.load_seen_orders()
        existing_ids = {
            f"{clean_text(row.get('source',''))}::{clean_text(row.get('id',''))}"
            for row in self.sent_order_rows
        }
        changed = False
        for item in sorted(seen_ids):
            if item and item not in existing_ids:
                source, order_id = item.split("::", 1) if "::" in item else ("Unknown", item)
                self.sent_order_rows.append({
                    "id": order_id,
                    "customer": "Unknown",
                    "status": "Sent to Telegram",
                    "sale_date": "Unknown",
                    "event_date": "Unknown",
                    "event": "Previously sent order",
                    "source": source,
                })
                changed = True
        if changed:
            self.save_sent_orders_history()

    def clean_histories(self):
        self.current_order_rows = [
            row for row in self.current_order_rows
            if not is_event_expired(row.get("event_date", ""))
        ]

    def summary(self):
        source_counts = {}
        status_counts = {"processed": 0, "cancelled": 0, "pending": 0}

        import datetime
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        try:
            from config import TICKETSSHOP_RESULTS_FILE
            from utils.helpers import load_json_file
            ts_cache = load_json_file(TICKETSSHOP_RESULTS_FILE, {})
        except:
            ts_cache = {}

        for row in self.current_order_rows:
            source = clean_text(row.get("source", "Unknown")) or "Unknown"
            source_counts[source] = source_counts.get(source, 0) + 1

        cache = load_order_details_cache()
        for row in self.current_order_rows:
            source = clean_text(row.get("source", "Unknown")) or "Unknown"
            order_id = clean_text(row.get("id", ""))
            details = cache.get(f"{source}::{order_id}", {})
            status_text = clean_text(details.get("status", row.get("status", ""))).lower()
            
            is_cancelled = "cancel" in status_text

            if is_cancelled:
                status_counts["cancelled"] += 1
                
            if "liveticketgroup" in source.lower():
                ts_info = ts_cache.get(order_id)
                if isinstance(ts_info, dict):
                    ts_status = ts_info.get("status", "unchecked")
                else:
                    ts_status = ts_info if ts_info else "unchecked"

                if ts_status == "listed":
                    status_counts["processed"] += 1
                else:
                    if not is_cancelled:
                        status_counts["pending"] += 1

        return {
            "running": self.running,
            "status": "Running" if self.running else "Stopped",
            "session_status": self.session_status,
            "last_check_time": self.last_check_time,
            "last_alert_time": self.last_alert_time,
            "last_order_info": self.last_order_info,
            "order_count": len(self.current_order_rows),
            "new_orders_count": len({
                f"{clean_text(r.get('source',''))}::{clean_text(r.get('id',''))}"
                for r in self.sent_order_rows
                if clean_text(r.get("id", ""))
            }),
            "processed_count": status_counts["processed"],
            "cancelled_count": status_counts["cancelled"],
            "pending_count": status_counts["pending"],
            "source_counts": source_counts,
            "settings": self.settings,
        }
