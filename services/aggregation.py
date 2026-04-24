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

        cache_key = f"{source}::{order_id}"
        details = cache.get(cache_key, {})

        quantity = to_int(details.get("quantity", 0))
        total_price = to_number(details.get("total_price", 0))

        if total_price <= 0:
            price_per_ticket = to_number(details.get("price_per_ticket", 0))
            if price_per_ticket > 0 and quantity > 0:
                total_price = round(price_per_ticket * quantity, 2)

        if event_name not in grouped:
            grouped[event_name] = {
                "event": event_name,
                "orders_count": 0,
                "total_quantity": 0,
                "total_price": 0.0,
                "cached_orders": 0,
            }

        grouped[event_name]["orders_count"] += 1

        if quantity > 0:
            grouped[event_name]["total_quantity"] += quantity

        if total_price > 0:
            grouped[event_name]["total_price"] += total_price

        if details and not should_refresh_cached_details(details):
            grouped[event_name]["cached_orders"] += 1

    result = []
    for item in grouped.values():
        result.append({
            "event": item["event"],
            "orders_count": item["orders_count"],
            "total_quantity": item["total_quantity"],
            "total_price": round(item["total_price"], 2),
            "cached_orders": item["cached_orders"],
        })

    result.sort(key=lambda x: x["total_price"], reverse=True)
    return result

# =========================================================
# WEB APP
# =========================================================
