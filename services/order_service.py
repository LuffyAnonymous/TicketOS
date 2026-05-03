import time
import threading
from datetime import datetime
import extensions as context
from core.helpers import clean_text, parse_sale_datetime, is_event_expired
from services.telegram_service import send_telegram
from services.cache_service import auto_cache_order_details, launch_auto_cache_if_needed

def build_order_message(order):
    source = clean_text(order.get('source', 'Unknown'))
    order_id = clean_text(order.get('id', '-'))
    event_name = clean_text(order.get('event', '-'))
    
    # We assume the app is hosted somewhere, but we'll use a placeholder URL if not set
    # Ideally this would come from an env var like APP_URL
    import os
    app_url = os.environ.get("APP_URL", "http://127.0.0.1:5000")
    
    # We can link directly to the app dashboard, maybe later with a query param or fragment to open the order
    # For now, link to the dashboard, and maybe the user can just search or click the order
    link = f"{app_url}"
    
    if source.lower() == "liveticketgroup":
        title = "New Live order detected"
    else:
        title = "        NEW ORDER"

    return (
        f"{title}\n"
        f"SOURCE: {source}\n"
        f"ID: {order_id}\n"
        f"CUSTOMER: {order.get('customer', '-')}\n"
        f"EVENT: {event_name}\n"
        f"SALE DATE: {order.get('sale_date', '-')}"
    )


def build_status_message(order, status):
    order_id = clean_text(order.get('id', '-'))
    event_name = clean_text(order.get('event', '-'))
    customer = clean_text(order.get('customer', '-'))
    
    if status == "cancelled":
        title = "❌ ORDER CANCELLED"
    elif status == "resold":
        title = "🔁 ORDER RESOLD"
    elif status == "completed":
        title = "✅ ORDER COMPLETED"
    else:
        title = "ℹ️ ORDER STATUS CHANGED"
        
    return (
        f"{title}\n\n"
        f"Order: {order_id}\n"
        f"Event: {event_name}\n"
        f"Customer: {customer}"
    )

def unique_order_key(order):
    return f"{clean_text(order.get('source','Unknown'))}::{clean_text(order.get('id',''))}"


def check_all_platforms_once(seen_orders):
    all_rows = []
    latest_candidates = []

    mon = {
        "LiveTicketGroup":   context.state.settings.get("monitor_liveticketgroup",  True),
        "FootballTicketNet": context.state.settings.get("monitor_footballticketnet", True),
        "Fanpass":           context.state.settings.get("monitor_fanpass",           False),
        "Tixstock":          context.state.settings.get("monitor_tixstock",          False),
    }

    for adapter in context.platform_adapters:
        try:
            enabled = mon.get(adapter.source_name, True)
            if not enabled:
                context.state.log(f"{adapter.source_name}: monitoring disabled, skipping")
                continue

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

    from config import ORDER_STATUS_STATE_FILE, SENT_FOOTBALLTICKETNET_ORDERS_FILE
    from core.storage import load_json_file, save_json_file
    from core.helpers import standardize_status
    
    status_state = load_json_file(ORDER_STATUS_STATE_FILE, {})
    status_state_changed = False
    ftn_sent = set(load_json_file(SENT_FOOTBALLTICKETNET_ORDERS_FILE, []))
    ftn_changed = False

    for row in all_rows:
        source = clean_text(row.get("source", ""))
        order_id = clean_text(row.get("id", ""))
        if not source or not order_id:
            continue
            
        key = f"{source}::{order_id}"
        
        # 1. New Order Alerts
        if source == "FootballTicketNet":
            # ftn_sent is a set of platform_order_id
            if key not in ftn_sent:
                msg = (
                    f"🟢 NEW FOOTBALLTICKETNET ORDER\n\n"
                    f"Order: {order_id}\n"
                    f"Event: {row.get('event', '-')}\n"
                    f"Category: {row.get('category', '-')}\n"
                    f"Customer: {row.get('customer', '-')}\n"
                    f"Mobile: {row.get('phone', '-')}\n"
                    f"Status: {row.get('status', '-')}"
                )
                send_telegram(msg)
                ftn_sent.add(key)
                ftn_changed = True
                context.state.log(f"FootballTicketNet: alert SENT for order -> {order_id}")
            else:
                context.state.log(f"FootballTicketNet: duplicate alert skipped -> {order_id}")
        
        elif source == "LiveTicketGroup":
            if key not in seen_orders:
                send_telegram(build_order_message(row))
                seen_orders.add(key)
                context.state.save_seen_orders(seen_orders)
                context.state.log(f"LiveTicketGroup: alert SENT for order -> {order_id}")

    # ─── STEP 2: Status Tracking ─────────────────────────────
    # Build set of currently visible order keys
    current_keys = set()
    for row in all_rows:
        source = clean_text(row.get("source", ""))
        order_id = clean_text(row.get("id", ""))
        if source and order_id:
            current_keys.add(f"{source}::{order_id}")

    status_state_changed = False

    for row in all_rows:
        source = clean_text(row.get("source", ""))
        order_id = clean_text(row.get("id", ""))
        if not source or not order_id:
            continue

        key = f"{source}::{order_id}"
        raw_status = row.get("status", "")
        resale_raw = row.get("resale_status", "")

        # Determine dashboard status using helper
        dash_status = standardize_status(raw_status, source=source, resale_status=resale_raw)

        old_data = status_state.get(key, {})
        if not old_data:
            status_state[key] = {
                "order_number": order_id,
                "event_name":   row.get("event", "-"),
                "event_date":   row.get("event_date", "-"),
                "customer":     row.get("customer", "-"),
                "sale_date":    row.get("sale_date", "-"),
                "order_status": dash_status,
                "source":       source,
                "last_seen":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            status_state_changed = True
            context.state.log(f"{source}: tracked new order → {order_id} [{dash_status}]")
        else:
            # Update last_seen timestamp
            status_state[key]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Only update if not already marked completed (disappeared orders keep that state)
            if old_data.get("order_status") not in ("completed",):
                if dash_status != old_data.get("order_status"):
                    status_state[key]["order_status"] = dash_status
                    status_state_changed = True

    # ─── STEP 3: Detect Disappeared LTG Orders → Completed ───
    # Any LTG order tracked in status_state that is no longer visible = completed
    for key, data in status_state.items():
        if not key.startswith("LiveTicketGroup::"):
            continue
        if key in current_keys:
            continue  # still visible, keep as-is
        if data.get("order_status") in ("completed", "cancelled", "resold"):
            continue  # already terminal, skip

        # Order was tracked but has now disappeared → mark completed
        status_state[key]["order_status"] = "completed"
        status_state_changed = True
        context.state.log(f"LiveTicketGroup: order {data.get('order_number',key)} disappeared → marked COMPLETED")

    if status_state_changed:
        save_json_file(ORDER_STATUS_STATE_FILE, status_state)

    if ftn_changed:
        save_json_file(SENT_FOOTBALLTICKETNET_ORDERS_FILE, list(ftn_sent))

    if all_rows:
        latest_order = all_rows[0]
        context.state.set_last_order(latest_order["id"], latest_order["event"], latest_order["sale_date"])
    else:
        context.state.log("No orders found in this cycle")



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
    context.state.log("Bot worker thread initiated")

    try:
        context.state.log("Bot starting first check cycle...")
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
