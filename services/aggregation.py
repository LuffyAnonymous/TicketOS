from datetime import datetime
from core.storage import load_order_details_cache, should_refresh_cached_details
from core.helpers import clean_text, to_int, to_number

def build_event_totals_from_cache(rows):
    cache = load_order_details_cache()
    grouped = {}

    for row in rows:
        event_name = clean_text(row.get("event", "Unknown")) or "Unknown"
        source = clean_text(row.get("source", "Unknown")) or "Unknown"
        order_id = clean_text(row.get("id", ""))
        status = clean_text(row.get("status", "Pending"))

        cache_key = f"{source}::{order_id}"
        details = cache.get(cache_key, {})

        quantity = to_int(details.get("quantity", row.get("quantity", 0)))
        
        # total_price can be in row or details
        total_price = to_number(details.get("total_price", row.get("total_price", 0)))

        if total_price <= 0:
            price_per_ticket = to_number(details.get("price_per_ticket", row.get("price_per_ticket", 0)))
            if price_per_ticket > 0 and quantity > 0:
                total_price = round(price_per_ticket * quantity, 2)

        key = f"{event_name}:::{source}"

        if key not in grouped:
            grouped[key] = {
                "event": event_name,
                "source": source,
                "orders_count": 0,
                "total_quantity": 0,
                "total_price": 0.0,
                "cached_orders": 0,
                "needs_attention": False,
            }

        grouped[key]["orders_count"] += 1

        if quantity > 0:
            grouped[key]["total_quantity"] += quantity

        if total_price > 0:
            grouped[key]["total_price"] += total_price

        if details and not should_refresh_cached_details(details):
            grouped[key]["cached_orders"] += 1
            
        if "cancel" in status.lower() or "fail" in status.lower():
            grouped[key]["needs_attention"] = True

    result = list(grouped.values())
    for r in result:
        r["total_price"] = round(r["total_price"], 2)

    result.sort(key=lambda x: (x["event"], x["source"]))
    return result

# =========================================================
# WEB APP
# =========================================================
