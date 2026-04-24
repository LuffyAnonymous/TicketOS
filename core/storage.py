import os
import json
from config import ORDER_DETAILS_CACHE_FILE

def load_json_file(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json_file(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_order_details_cache():
    data = load_json_file(ORDER_DETAILS_CACHE_FILE, {})
    return data if isinstance(data, dict) else {}


def save_order_details_cache(data):
    save_json_file(ORDER_DETAILS_CACHE_FILE, data)


def cache_order_details(source, order_id, details):
    cache = load_order_details_cache()
    cache[f"{source}::{order_id}"] = details
    save_order_details_cache(cache)

def get_cached_order_details(source, order_id):
    cache = load_order_details_cache()
    return cache.get(f"{source}::{order_id}", {})


def should_refresh_cached_details(details):
    if not isinstance(details, dict) or not details:
        return True

    important = [
        details.get("quantity", "-"),
        details.get("total_price", "-"),
        details.get("event", "-"),
        details.get("league", "-"),
        details.get("venue", "-"),
        details.get("event_date", "-"),
    ]

    return all(v in {"-", "", None, "Unknown"} for v in important)
