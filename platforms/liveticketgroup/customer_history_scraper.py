import re
import traceback
from bs4 import BeautifulSoup
from platforms.liveticketgroup import get_ltg_adapter
from database import get_db, DBOrder

def extract_customer_from_details(details):
    """
    Extracts first name, last name, phone number, and email from details dict.
    Converts missing email to "N/A" and handles name splitting.
    """
    if not details:
        return None
    
    full_name = details.get("billing_full_name") or details.get("customer_name") or "-"
    parts = full_name.strip().split(maxsplit=1)
    if len(parts) == 2:
        first_name, last_name = parts[0], parts[1]
    elif len(parts) == 1:
        first_name, last_name = parts[0], "-"
    else:
        first_name, last_name = "-", "-"
        
    phone_number = details.get("billing_mobile") or details.get("mobile_number") or ""
    email = details.get("email") or "N/A"
    if not email or email.strip() == "":
        email = "N/A"
        
    return {
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number,
        "email": email
    }

def get_all_order_ids(adapter):
    """
    Navigates search order list page and handles pagination to collect all unique order IDs.
    """
    print("Scraping page 1...")
    url = "https://my.liveticketgroup.com/pages/content/orders.aspx?topnav=1&subnav=26"
    html = adapter.ensure_logged_in(url)
    
    soup = BeautifulSoup(html, "html.parser")
    viewstate = soup.find("input", id="__VIEWSTATE")["value"] if soup.find("input", id="__VIEWSTATE") else ""
    viewstategen = soup.find("input", id="__VIEWSTATEGENERATOR")["value"] if soup.find("input", id="__VIEWSTATEGENERATOR") else ""
    eventvalidation = soup.find("input", id="__EVENTVALIDATION")["value"] if soup.find("input", id="__EVENTVALIDATION") else ""
    
    data = {
        "__VIEWSTATE": viewstate,
        "__VIEWSTATEGENERATOR": viewstategen,
        "__EVENTVALIDATION": eventvalidation,
        "ctl00$plcContent$urcSearch$txtEventName": "",
        "ctl00$plcContent$urcSearch$txtStartDate": "2000-01-01",
        "ctl00$plcContent$urcSearch$txtEndDate": "2026-07-04",
        "ctl00$plcContent$urcSearch$btnSearch": "Search"
    }
    
    r = adapter.session.post(url, data=data, timeout=30)
    html = r.text
    
    order_ids = []
    rows, _ = adapter.parse_orders_from_html(html)
    print(f"Found {len(rows)} orders on page 1.")
    for row in rows:
        if row.get("id"):
            order_ids.append(row["id"])
            
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
        
        print(f"Scraping page {next_page}...")
        soup = BeautifulSoup(html, "html.parser")
        viewstate = soup.find("input", id="__VIEWSTATE")["value"] if soup.find("input", id="__VIEWSTATE") else ""
        viewstategen = soup.find("input", id="__VIEWSTATEGENERATOR")["value"] if soup.find("input", id="__VIEWSTATEGENERATOR") else ""
        eventvalidation = soup.find("input", id="__EVENTVALIDATION")["value"] if soup.find("input", id="__EVENTVALIDATION") else ""
        
        page_data = {
            "__VIEWSTATE": viewstate,
            "__VIEWSTATEGENERATOR": viewstategen,
            "__EVENTVALIDATION": eventvalidation,
            "__EVENTTARGET": target,
            "__EVENTARGUMENT": f"Page${next_page}",
            "ctl00$plcContent$urcSearch$txtEventName": "",
            "ctl00$plcContent$urcSearch$txtStartDate": "2000-01-01",
            "ctl00$plcContent$urcSearch$txtEndDate": "2026-07-04",
        }
        
        try:
            r_page = adapter.session.post(url, data=page_data, timeout=30)
            html = r_page.text
            page_rows, _ = adapter.parse_orders_from_html(html)
            print(f"Found {len(page_rows)} orders on page {next_page}.")
            for row in page_rows:
                if row.get("id"):
                    order_ids.append(row["id"])
                    
            new_matches = re.findall(r"__doPostBack\('([^']+)','(Page\$(\d+))'\)", html)
            for _, m_arg, m_page in new_matches:
                p_num = int(m_page)
                if p_num not in visited_pages:
                    pages_to_visit.add(p_num)
        except Exception as e:
            print(f"Error fetching page {next_page}: {e}")
            
    unique_order_ids = []
    seen = set()
    for o in order_ids:
        if o not in seen:
            seen.add(o)
            unique_order_ids.append(o)
            
    return unique_order_ids

def scrape_customer_history():
    """
    Main entry point to scrape all customer history.
    """
    adapter = get_ltg_adapter()
    if not adapter:
        raise Exception("LiveTicketGroup adapter not initialized or not found.")
        
    adapter.ensure_logged_in()
    order_ids = get_all_order_ids(adapter)
    print(f"Total unique historical orders found: {len(order_ids)}")
    
    customers = []
    db = get_db()
    existing_orders_map = {}
    if db:
        try:
            db_orders = db.query(DBOrder).filter(DBOrder.platform == "LiveTicketGroup").all()
            for dbo in db_orders:
                existing_orders_map[str(dbo.order_number)] = dbo
        except Exception as db_err:
            print(f"Database warning while fetching existing orders: {db_err}")
        finally:
            db.close()
            
    for idx, oid in enumerate(order_ids, start=1):
        print(f"[{idx}/{len(order_ids)}] Processing order {oid}...")
        
        dbo = existing_orders_map.get(str(oid))
        if dbo and (dbo.email or dbo.mobile_number):
            cust_details = {
                "billing_full_name": dbo.billing_full_name or dbo.customer_name,
                "customer_name": dbo.customer_name,
                "billing_mobile": dbo.billing_mobile or dbo.mobile_number,
                "mobile_number": dbo.mobile_number,
                "email": dbo.email
            }
            cust = extract_customer_from_details(cust_details)
            if cust:
                customers.append(cust)
                print(f"  Loaded customer '{cust['first_name']} {cust['last_name']}' from database.")
                continue
                
        try:
            details = adapter.fetch_order_details(oid)
            if details:
                cust = extract_customer_from_details(details)
                if cust:
                    customers.append(cust)
                    print(f"  Extracted customer: {cust['first_name']} {cust['last_name']}")
        except Exception as e:
            print(f"  Error processing order {oid}: {e}")
            
    return customers
