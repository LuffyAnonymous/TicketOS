import threading
import time
import extensions as context
from config import AUTO_CACHE_THREADS, AUTO_CACHE_SLEEP_SECONDS
from core.helpers import clean_text
from core.storage import get_cached_order_details, should_refresh_cached_details, cache_order_details
from platforms.liveticketgroup import get_ltg_order_details

def launch_auto_cache_if_needed(rows):
    if not rows:
        return

    pending = []
    for row in rows:
        source = clean_text(row.get("source", ""))
        order_id = clean_text(row.get("id", ""))
        if not source or not order_id:
            continue
        existing = get_cached_order_details(source, order_id)
        if should_refresh_cached_details(existing):
            pending.append(row)

    if not pending:
        return

    with context.AUTO_CACHE_MANAGER["lock"]:
        if context.AUTO_CACHE_MANAGER["running"]:
            return
        context.AUTO_CACHE_MANAGER["running"] = True

    def runner():
        try:
            context.state.log(f"Auto-cache: background sync started for {len(pending)} order(s)")
            auto_cache_order_details(pending)
        except Exception as e:
            context.state.log(f"Auto-cache background error: {e}")
        finally:
            with context.AUTO_CACHE_MANAGER["lock"]:
                context.AUTO_CACHE_MANAGER["running"] = False

    threading.Thread(target=runner, daemon=True).start()

def fetch_and_cache_order_details_for_row(row):
    source = clean_text(row.get("source", ""))
    order_id = clean_text(row.get("id", ""))

    if not source or not order_id:
        return False

    existing = get_cached_order_details(source, order_id)
    if existing and not should_refresh_cached_details(existing):
        return False

    try:
        if source == "LiveTicketGroup":
            details = get_ltg_order_details(order_id)
            cache_order_details(source, order_id, details)
            context.state.log(f"Auto-cache: loaded details for {source} #{order_id}")
            return True

        return False
    except Exception as e:
        context.state.log(f"Auto-cache failed for {source} #{order_id}: {e}")
        return False


def auto_cache_order_details(rows, max_threads=AUTO_CACHE_THREADS):
    if not rows:
        return

    pending_rows = []
    for row in rows:
        source = clean_text(row.get("source", ""))
        order_id = clean_text(row.get("id", ""))
        if not source or not order_id:
            continue

        existing = get_cached_order_details(source, order_id)
        if should_refresh_cached_details(existing):
            pending_rows.append(row)

    if not pending_rows:
        context.state.log("Auto-cache: all visible orders already cached")
        return

    context.state.log(f"Auto-cache: {len(pending_rows)} order(s) pending")

    semaphore = threading.Semaphore(max_threads)
    threads = []

    def worker(order_row):
        with semaphore:
            fetch_and_cache_order_details_for_row(order_row)
            time.sleep(AUTO_CACHE_SLEEP_SECONDS)

    for row in pending_rows:
        t = threading.Thread(target=worker, args=(row,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    context.state.log("Auto-cache: completed")
