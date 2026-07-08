import traceback
from platforms.liveticketgroup import get_ltg_adapter

def scrape_customer_details(order_id):
    """
    Reuses the existing authenticated LiveTicketGroup session to open the order detail page,
    extract all available customer/order fields, and return a clean Python dictionary.
    Never sends Telegram messages and never crashes the app on failure.
    """
    try:
        adapter = get_ltg_adapter()
        if not adapter:
            print("Customer Scraper Warning: LiveTicketGroup adapter not initialized or not found.")
            return {}
        
        # Call the adapter's details scraper (which reuses session and logs in if needed)
        details = adapter.fetch_order_details(order_id)
        if not details:
            print(f"Customer Scraper Warning: No details returned for order {order_id}.")
            return {}
        
        # Clean details dictionary
        details_clean = {}
        for k, v in details.items():
            if k in ("raw_payload", "details_fetched_at"):
                continue
            if hasattr(v, "strftime"):
                details_clean[k] = v.strftime("%Y-%m-%d %H:%M:%S")
            else:
                details_clean[k] = v
        
        # Ensure order number exists
        details_clean["order_number"] = str(order_id)
        return details_clean
    except Exception as e:
        print(f"Error in LiveTicketGroup customer scraper for order {order_id}: {e}")
        traceback.print_exc()
        return {}
