import os
import sys
import re
import time
import json
import traceback
from dotenv import load_dotenv
load_dotenv()

# Add root folder to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extensions as context
from core.state import AppState
from platforms.registry import build_platform_adapters
from platforms.liveticketgroup import get_ltg_adapter
from database import get_db, DBOrder
from services.excel_exporter import export_customer_history, EXCEL_HISTORY_FILE
from bs4 import BeautifulSoup

def split_customer_name(full_name):
    if not full_name or full_name.strip() in ("", "-", "None"):
        return "", ""
    parts = full_name.strip().split(maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    elif len(parts) == 1:
        return parts[0], ""
    return "", ""

def format_purchase_datetime(sale_date):
    if not sale_date:
        return "N/A", "N/A"
    from datetime import datetime
    if isinstance(sale_date, str):
        from core.helpers import parse_sale_datetime
        dt = parse_sale_datetime(sale_date)
        if not dt:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    dt = datetime.strptime(sale_date, fmt)
                    break
                except:
                    pass
        if dt:
            sale_date = dt
        else:
            parts = sale_date.split()
            if len(parts) == 2:
                return parts[0], parts[1]
            return sale_date, "N/A"
            
    if hasattr(sale_date, "strftime"):
        return sale_date.strftime("%Y-%m-%d"), sale_date.strftime("%H:%M:%S")
        
    return "N/A", "N/A"

def extract_order_info(oid, details_or_dbo, fallback_sale_date=None, fallback_game=None, fallback_qty=None):
    """
    Extracts customer info and order info from a details dictionary or a DBOrder object.
    """
    if not details_or_dbo:
        return None
        
    from datetime import datetime
    is_dbo = not isinstance(details_or_dbo, dict)
    
    if is_dbo:
        full_name = details_or_dbo.billing_full_name or details_or_dbo.customer_name or "-"
        mobile = details_or_dbo.billing_mobile or details_or_dbo.mobile_number or ""
        email = details_or_dbo.email or ""
        game = details_or_dbo.event_name or ""
        sale_date = details_or_dbo.sale_date
        qty = details_or_dbo.quantity
    else:
        full_name = details_or_dbo.get("billing_full_name") or details_or_dbo.get("customer_name") or "-"
        mobile = details_or_dbo.get("billing_mobile") or details_or_dbo.get("mobile_number") or ""
        email = details_or_dbo.get("email") or ""
        game = details_or_dbo.get("event_name") or details_or_dbo.get("event") or ""
        sale_date = details_or_dbo.get("sale_date")
        qty = details_or_dbo.get("quantity")

    if not sale_date or sale_date == "-":
        sale_date = fallback_sale_date
    if (not game or game == "-" or game == "") and fallback_game:
        game = fallback_game
    if (qty is None or qty == 0 or qty == 1) and fallback_qty:
        qty = fallback_qty

    first_name, last_name = split_customer_name(full_name)
    
    if not email or email.strip() == "" or email.lower() == "none":
        email = "N/A"
    else:
        email = email.strip()
        
    mobile = mobile.strip()
    game = game.strip()
    purchase_date, purchase_time = format_purchase_datetime(sale_date)
    
    try:
        qty = int(qty) if qty is not None else 1
    except:
        qty = 1
    if qty <= 0:
        qty = 1
        
    return {
        "order_id": str(oid),
        "first_name": first_name,
        "last_name": last_name,
        "mobile_number": mobile,
        "email": email,
        "game_purchased": game,
        "purchase_date": purchase_date,
        "purchase_time": purchase_time,
        "quantity": qty
    }


    
def build_post_payload(soup, overrides):
    payload = {}
    for input_tag in soup.find_all("input"):
        name = input_tag.get("name")
        if not name:
            continue
        val = input_tag.get("value", "")
        if input_tag.get("type") == "submit" and name not in overrides:
            continue
        payload[name] = val
        
    for select_tag in soup.find_all("select"):
        name = select_tag.get("name")
        if not name:
            continue
        selected_opt = select_tag.find("option", selected=True)
        if not selected_opt:
            selected_opt = select_tag.find("option")
        val = selected_opt.get("value", "") if selected_opt else ""
        payload[name] = val
        
    for k, v in overrides.items():
        payload[k] = v
        
    return payload

def main():
    # Initialize state and adapters
    context.state = AppState()
    context.platform_adapters = build_platform_adapters()
    
    adapter = get_ltg_adapter()
    if not adapter:
        print("Error: LiveTicketGroup adapter not found.")
        return
        
    # Explicitly set cookies for all subdomains to prevent session loss on my/www navigation
    from config import ORDER_STATE_FILE
    from core.storage import load_json_file
    cookies_dict = load_json_file(ORDER_STATE_FILE, {}).get("LiveTicketGroup", {}).get("cookies", {})
    for k, v in cookies_dict.items():
        for d in [".liveticketgroup.com", "my.liveticketgroup.com", "www.liveticketgroup.com"]:
            try:
                adapter.session.cookies.set(k, v, domain=d, path="/")
            except:
                pass
                
    username = adapter.config.get("username")
    password = adapter.config.get("password")
    if not username or not password:
        print("Error: LIVE_USERNAME and LIVE_PASSWORD must be set in environmental variables.")
        return

    print("Logging in to LiveTicketGroup...")
    adapter.login()
    
    print("Opening HOME...")
    adapter.ensure_logged_in("https://my.liveticketgroup.com/pages/content/index.aspx")
    
    print("Opening Orders...")
    url = "https://my.liveticketgroup.com/pages/content/orders.aspx?topnav=1&subnav=26"
    html = adapter.ensure_logged_in(url)
    
    print("Setting sale date range: 2000-01-01 to 2026-07-04")
    
    # Generate hybrid intervals to avoid server-side search result truncation (max 150 items per search)
    from datetime import datetime, timedelta
    intervals = []
    
    # 1. 2000-01-01 to 2024-12-31: 1-year intervals (very low volume, safe from truncation)
    curr = datetime.strptime("2000-01-01", "%Y-%m-%d")
    end_legacy = datetime.strptime("2024-12-31", "%Y-%m-%d")
    while curr <= end_legacy:
        next_date = min(curr + timedelta(days=364), end_legacy)
        intervals.append((curr.strftime("%Y-%m-%d"), next_date.strftime("%Y-%m-%d")))
        curr = next_date + timedelta(days=1)
        
    # 2. 2025-01-01 to 2026-07-04: 10-day intervals (high volume, protects against 150-order truncation)
    curr = datetime.strptime("2025-01-01", "%Y-%m-%d")
    end_active = datetime.strptime("2026-07-04", "%Y-%m-%d")
    while curr <= end_active:
        next_date = min(curr + timedelta(days=9), end_active)
        intervals.append((curr.strftime("%Y-%m-%d"), next_date.strftime("%Y-%m-%d")))
        curr = next_date + timedelta(days=1)
        
    search_orders_map = {}
    
    # Perform Search POST and dynamic pagination for each interval
    for idx, (s_from, s_to) in enumerate(intervals, start=1):
        r_get = adapter.session.get(url, timeout=30)
        soup_get = BeautifulSoup(r_get.text, "html.parser")
        
        search_overrides = {
            "ctl00$plcContent$urcSearch$txtStartDate": s_from,
            "ctl00$plcContent$urcSearch$txtEndDate": s_to,
            "ctl00$plcContent$urcSearch$btnSearch": "Search"
        }
        data = build_post_payload(soup_get, search_overrides)
        r_search = adapter.session.post(url, data=data, timeout=45)
        html = r_search.text
        
        rows, _ = adapter.parse_orders_from_html(html)
        for r in rows:
            oid = r.get("id")
            if oid:
                search_orders_map[str(oid)] = r
        
        # Paginate through subsequent pages if they exist
        visited_pages = {1}
        pages_to_visit = set()
        matches = re.findall(r"__doPostBack\('([^']+)','(Page\$(\d+))'\)", html)
        target = None
        for m_target, m_arg, m_page in matches:
            target = m_target
            p_num = int(m_page)
            if p_num not in visited_pages:
                pages_to_visit.add(p_num)
                
        while pages_to_visit:
            next_page = min(pages_to_visit)
            pages_to_visit.remove(next_page)
            visited_pages.add(next_page)
            
            soup_page = BeautifulSoup(html, "html.parser")
            page_overrides = {
                "__EVENTTARGET": target,
                "__EVENTARGUMENT": f"Page${next_page}",
                "ctl00$plcContent$urcSearch$txtStartDate": s_from,
                "ctl00$plcContent$urcSearch$txtEndDate": s_to,
            }
            page_data = build_post_payload(soup_page, page_overrides)
            
            try:
                r_page = adapter.session.post(url, data=page_data, timeout=30)
                html = r_page.text
                page_rows, _ = adapter.parse_orders_from_html(html)
                for row in page_rows:
                    oid = row.get("id")
                    if oid:
                        search_orders_map[str(oid)] = row
                        
                new_matches = re.findall(r"__doPostBack\('([^']+)','(Page\$(\d+))'\)", html)
                for _, m_arg, m_page in new_matches:
                    p_num = int(m_page)
                    if p_num not in visited_pages:
                        pages_to_visit.add(p_num)
            except Exception:
                pass
                
    # Dedup order IDs preserving order
    unique_order_ids = []
    seen_ids = set()
    for o in search_orders_map.keys():
        if o not in seen_ids:
            seen_ids.add(o)
            unique_order_ids.append(o)
            
    orders_found = len(unique_order_ids)
    print("Scraping all orders found...")
        
    # Load database cache map to speed up lookups
    db = get_db()
    existing_orders_map = {}
    if db:
        try:
            db_orders = db.query(DBOrder).filter(DBOrder.platform == "LiveTicketGroup").all()
            for dbo in db_orders:
                existing_orders_map[str(dbo.order_number)] = dbo
        except Exception:
            pass
        finally:
            db.close()

    failed_order_ids = []
    orders_list = []
    
    # Scrape details for each unique order ID
    for idx, oid in enumerate(unique_order_ids, start=1):
        print(f"Scraping order {idx} / {orders_found}")
        
        search_info = search_orders_map.get(str(oid)) or {}
        fallback_sale_date_str = search_info.get("sale_date")
        fallback_game = search_info.get("event")
        fallback_qty = search_info.get("quantity")
        
        # Check local DB cache
        dbo = existing_orders_map.get(str(oid))
        if dbo and (dbo.email or dbo.mobile_number):
            # If DB cache has missing/None sale_date, try to back-fill it
            if (not dbo.sale_date or dbo.sale_date == "-") and fallback_sale_date_str and fallback_sale_date_str != "-":
                from core.helpers import parse_sale_datetime
                dt = parse_sale_datetime(fallback_sale_date_str)
                if dt:
                    dbo.sale_date = dt
                    db = get_db()
                    if db:
                        try:
                            db_dbo = db.query(DBOrder).filter(DBOrder.platform == "LiveTicketGroup", DBOrder.order_number == str(oid)).first()
                            if db_dbo:
                                db_dbo.sale_date = dt
                                db.commit()
                        except:
                            pass
                        finally:
                            db.close()
            
            order_info = extract_order_info(oid, dbo, fallback_sale_date=fallback_sale_date_str, fallback_game=fallback_game, fallback_qty=fallback_qty)
            if order_info:
                orders_list.append(order_info)
                print("Extracted customer and game details...")
                continue
                
        # Perform HTTP GET request to scrape order details
        try:
            details = adapter.fetch_order_details(oid)
            if details:
                order_info = extract_order_info(oid, details, fallback_sale_date=fallback_sale_date_str, fallback_game=fallback_game, fallback_qty=fallback_qty)
                if order_info:
                    orders_list.append(order_info)
                    print("Extracted customer and game details...")
                    
                    resolved_sale_date = None
                    if order_info["purchase_date"] != "N/A":
                        try:
                            resolved_sale_date = datetime.strptime(
                                f"{order_info['purchase_date']} {order_info['purchase_time']}",
                                "%Y-%m-%d %H:%M:%S"
                            )
                        except:
                            pass
                    
                    # Cache in DB
                    db = get_db()
                    if db:
                        try:
                            existing_dbo = db.query(DBOrder).filter(
                                DBOrder.platform == "LiveTicketGroup",
                                DBOrder.order_number == str(oid)
                            ).first()
                            if not existing_dbo:
                                dbo = DBOrder(
                                    platform="LiveTicketGroup",
                                    order_number=str(oid),
                                    customer_name=details.get("customer_name") or details.get("billing_full_name") or "",
                                    billing_full_name=details.get("billing_full_name") or details.get("customer_name") or "",
                                    email=details.get("email") or "",
                                    mobile_number=details.get("mobile_number") or details.get("billing_mobile") or "",
                                    billing_mobile=details.get("billing_mobile") or details.get("mobile_number") or "",
                                    event_name=order_info["game_purchased"],
                                    quantity=order_info["quantity"],
                                    total_amount=details.get("total_amount") or details.get("total_value") or 0.0,
                                    raw_status=details.get("raw_status") or "Completed",
                                    sale_date=resolved_sale_date
                                )
                                db.add(dbo)
                                db.commit()
                        except:
                            pass
                        finally:
                            db.close()
                else:
                    failed_order_ids.append(oid)
            else:
                failed_order_ids.append(oid)
        except Exception:
            failed_order_ids.append(oid)

    # 1. Export using the refactored excel exporter
    export_customer_history(orders_list)
    print("Export finished.")
    
    if failed_order_ids:
        print(f"Failed order IDs: {failed_order_ids}")

if __name__ == "__main__":
    main()
