import time
import threading
from datetime import datetime
import extensions as context
from core.helpers import clean_text, parse_sale_datetime
from services.telegram_service import send_telegram
from services.cache_service import auto_cache_order_details

def build_order_message(order):
    return (
        f"🔥 NEW ORDER 🔥\n"
        f"SOURCE: {order.get('source', 'Unknown')}\n"
        f"ID: {order.get('id', '-')}\n"
        f"CUSTOMER: {order.get('customer', '-')}\n"
        f"EVENT: {order.get('event', '-')}\n"
        f"SALE DATE: {order.get('sale_date', '-')}"
    )


def unique_order_key(order):
    return f"{clean_text(order.get('source','Unknown'))}::{clean_text(order.get('id',''))}"


def check_all_platforms_once(seen_orders):
    all_rows = []
    latest_candidates = []

    for adapter in context.platform_adapters:
        try:
            rows, latest_order = adapter.fetch_orders()
            all_rows.extend(rows)
            if latest_order:
                latest_candidates.append(latest_order)
            context.state.log(f"{adapter.source_name}: parsed {len(rows)} active rows")
        except Exception as e:
            context.state.log(f"{adapter.source_name}: error -> {repr(e)}")

    all_rows.sort(
        key=lambda r: parse_sale_datetime(r.get("sale_date", "")) or datetime.min,
        reverse=True
    )
    context.state.current_order_rows = all_rows

    latest_order = None
    latest_dt = None
    for order in latest_candidates:
        dt = parse_sale_datetime(order.get("sale_date", ""))
        if dt is not None and (latest_dt is None or dt > latest_dt):
            latest_dt = dt
            latest_order = order

    if not latest_order and all_rows:
        latest_order = all_rows[0]

    if not latest_order:
        context.state.log("No latest order found")
        return

    context.state.set_last_order(latest_order["id"], latest_order["event"], latest_order["sale_date"])

    order_key = unique_order_key(latest_order)

    if order_key not in seen_orders and not is_event_expired(latest_order["event_date"]):
        send_telegram(build_order_message(latest_order))
        seen_orders.add(order_key)
        context.state.save_seen_orders(seen_orders)
        latest_order["status"] = latest_order.get("status") or "Sent to Telegram"
        context.state.upsert_sent_order_row(latest_order)
        context.state.set_last_alert()
        context.state.log(f"New order sent -> {order_key}")
    else:
        context.state.upsert_sent_order_row(latest_order)
        context.state.log("No new latest order")


def is_sleep_window(now=None):
    now = now or datetime.now()
    return 0 <= now.hour < 5


def seconds_until_5am(now=None):
    now = now or datetime.now()
    resume_time = now.replace(hour=5, minute=0, second=0, microsecond=0)
    return max(0, int((resume_time - now).total_seconds()))


def get_interval_seconds():
    try:
        minutes = int(context.state.settings.get("interval_minutes", 30))
        return max(1, minutes) * 60
    except Exception:
        return 30 * 60


def wait_with_stop(total_seconds):
    for _ in range(total_seconds):
        if context.state.stop_event.is_set():
            return False
        time.sleep(1)
    return True


def execute_check_cycle(seen_orders):
    context.state.set_last_check()
    context.state.clean_histories()
    try:
        check_all_platforms_once(seen_orders)

        # auto-cache details for current visible orders in background
        try:
            launch_auto_cache_if_needed(context.state.current_order_rows)
        except Exception as e:
            context.state.log(f"Auto-cache cycle error: {e}")

    except Exception as e:
        context.state.log(f"Order cycle error: {e}")


def bot_worker():
    seen_orders = context.state.load_seen_orders()
    context.state.running = True
    context.state.log("Bot started")

    try:
        while not context.state.stop_event.is_set():
            if context.state.settings.get("sleep_window_enabled", False) and is_sleep_window():
                context.state.session_status = "Sleeping (12AM-5AM)"
                context.state.log("Sleep window active. Waiting until 5:00 AM.")
                if not wait_with_stop(seconds_until_5am()):
                    break
                continue

            execute_check_cycle(seen_orders)

            if not context.platform_adapters:
                interval = 60
                context.state.log("No enabled platforms. Retrying in 1 minute.")
            else:
                interval = get_interval_seconds()
                context.state.log(f"Waiting {interval // 60} minute(s) for next cycle")

            if not wait_with_stop(interval):
                break
    except Exception as e:
        context.state.log(f"Fatal worker error: {e}")
    finally:
        context.state.running = False
        context.state.log("Bot stopped")

# =========================================================
# AGGREGATION
