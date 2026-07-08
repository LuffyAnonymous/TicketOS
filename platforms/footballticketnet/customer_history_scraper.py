import os
import random
import re
from datetime import datetime
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

def split_customer_name(full_name):
    if not full_name or str(full_name).strip() in ("", "-", "None"):
        return "", ""
    parts = str(full_name).strip().split(maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    elif len(parts) == 1:
        return parts[0], ""
    return "", ""

def format_purchase_datetime(sale_date):
    if not sale_date:
        return "N/A", "N/A"
    if isinstance(sale_date, str):
        s = str(sale_date).strip()
        for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(s, fmt)
                return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")
            except:
                pass
        parts = s.split()
        if len(parts) == 2:
            return parts[0], parts[1]
        return s, "N/A"
        
    if hasattr(sale_date, "strftime"):
        return sale_date.strftime("%Y-%m-%d"), sale_date.strftime("%H:%M:%S")
        
    return "N/A", "N/A"

def scrape_ftn_customer_history():
    # Load credentials from .env with fallback
    username = os.environ.get("FOOTBALLTICKETNET_SELLER_EMAIL") or os.environ.get("FOOTBALLTICKETNET_USERNAME", "")
    password = os.environ.get("FOOTBALLTICKETNET_SELLER_PASSWORD") or os.environ.get("FOOTBALLTICKETNET_PASSWORD", "")
    
    if not username.strip() or not password.strip():
        raise Exception("FootballTicketNet seller credentials are not configured in .env file.")
        
    print("Opening FootballTicketNet...")
    
    # Clear old failed log file if it exists
    if os.path.exists("ftn_failed_orders.log"):
        try:
            os.remove("ftn_failed_orders.log")
        except:
            pass
            
    orders_list = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-setuid-sandbox',
            ]
        )
        
        browser_context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-GB",
            timezone_id="Europe/London",
        )
        
        page = browser_context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Block heavy images to speed up scraping
        page.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())
        
        try:
            # 1. Load Homepage
            page.goto("https://www.footballticketnet.com/#", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            
            # Check if already logged in (unlikely in fresh Playwright context)
            def is_logged_in_check():
                return page.locator("a:has-text('Log Out'), a:has-text('Logout'), a:has-text('Sign Out')").count() > 0
                
            if not is_logged_in_check():
                print("Clicking Log In...")
                login_btn = page.locator("a.login_btn").first
                if login_btn.count() == 0:
                    page.screenshot(path="ftn_login_failure.png", full_page=True)
                    raise Exception("Login button 'a.login_btn' not found on homepage.")
                    
                login_btn.click()
                page.wait_for_timeout(2000)
                
                print("Choosing Seller Log In...")
                # Click the supplier tab
                clicked_tab = page.evaluate("""() => {
                    let btn = document.querySelector('button.link_supplier');
                    if (!btn) {
                        btn = document.querySelector('#wrapper > div.top_header.top_header_append > div > div.right_top > div > div.tab > button.tablinks.link_supplier');
                    }
                    if (!btn) {
                        btn = Array.from(document.querySelectorAll('button.tablinks')).find(b => b.textContent.trim().toLowerCase().includes('supplier') || b.textContent.trim().toLowerCase().includes('seller'));
                    }
                    if (btn) { btn.click(); return btn.textContent.trim(); }
                    return null;
                }""")
                if not clicked_tab:
                    page.screenshot(path="ftn_login_failure.png", full_page=True)
                    raise Exception("Supplier/Seller tab button not found in login modal.")
                    
                page.wait_for_timeout(2000)
                
                print("Logging in as seller...")
                page.locator("#supplier_email").fill(username)
                page.locator("#supplier_password").fill(password)
                page.wait_for_timeout(500)
                
                submit = page.locator("#submit_supplier").first
                if submit.count() > 0:
                    submit.click()
                else:
                    page.keyboard.press("Enter")
                    
                page.wait_for_timeout(3000)
                
                # Check if login succeeded
                if not is_logged_in_check():
                    page.screenshot(path="ftn_login_failure.png", full_page=True)
                    # Extract any error message from the page
                    error_msg = "Unknown login error"
                    try:
                        error_el = page.locator(".error, .alert, .notification, [class*='error'], [class*='alert']").first
                        if error_el.count() > 0:
                            error_msg = error_el.inner_text().strip()
                    except:
                        pass
                    raise Exception(f"Login failed: {error_msg}")
                    
            print("Opening seller orders...")
            page.goto("https://www.footballticketnet.com/?action=delivery_info", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            
            print("Scraping all orders...")
            
            # Expand all event rows first
            event_rows = page.locator("tr.event_row_delivery, tr[class*='event'], tr[onclick*='event'], [class*='event_row']")
            event_count = event_rows.count()
            
            for i in range(event_count):
                try:
                    event_rows.nth(i).click()
                    page.wait_for_timeout(1000)
                except:
                    pass
                    
            # Expand all category rows
            cat_rows = page.locator("tr.category_row, tr[class*='cat'], [class*='category_row']")
            cat_count = cat_rows.count()
            for j in range(cat_count):
                try:
                    cat_rows.nth(j).click()
                    page.wait_for_timeout(1000)
                except:
                    pass
                    
            # Locate all order rows
            order_rows = page.locator("tr.order_row_delivery, tr[class*='order_row'], [class*='order_id_delivery']")
            total_orders = order_rows.count()
            
            for k in range(total_orders):
                print(f"Scraping order {k + 1} / {total_orders}")
                order_row = order_rows.nth(k)
                
                try:
                    # 1. Try to read event name from parents or fallback
                    # In FTN, category and event are parents. Let's find the event row preceding this order row
                    event_name = "Unknown Event"
                    try:
                        # Evaluate in page to find the nearest preceding event row text
                        event_name = page.evaluate(f"""(rowIdx) => {{
                            let rows = Array.from(document.querySelectorAll("tr"));
                            let orderRow = document.querySelectorAll("tr.order_row_delivery, tr[class*='order_row'], [class*='order_id_delivery']")[rowIdx];
                            if (!orderRow) return "Unknown Event";
                            
                            // Find nearest preceding event row
                            let idx = rows.indexOf(orderRow);
                            for (let i = idx; i >= 0; i--) {{
                                let r = rows[i];
                                if (r.classList.contains("event_row_delivery") || r.className.includes("event") || r.getAttribute("onclick")?.includes("event")) {{
                                    return r.textContent.trim();
                                }}
                            }}
                            return "Unknown Event";
                        }}""", k)
                    except:
                        pass
                        
                    # 2. Check if customer details are visible in the order row columns first
                    cust_name = ""
                    cust_phone = ""
                    cust_email = ""
                    qty = 1
                    sale_date = ""
                    order_id = f"FTN_TEMP_{k}"
                    
                    # Look for eye button to open details
                    eye = order_row.locator("i.fa-eye, .fa-eye, .view_order_btn, [class*='view']").first
                    if eye.count() > 0:
                        eye.click()
                        page.wait_for_timeout(2500)
                        
                        try:
                            # Extract fields from the modal details popup
                            id_text = page.locator(".order_id, #order_id_val, [class*='order_id']").first.inner_text()
                            order_id = id_text.replace("Order #", "").replace("Order", "").strip()
                        except:
                            pass
                            
                        try:
                            cust_name = page.locator(".client_name, #client_name, [class*='client_name']").first.inner_text().strip()
                        except:
                            pass
                            
                        try:
                            cust_phone = page.locator(".client_phone, #client_phone, [class*='client_phone']").first.inner_text().strip()
                        except:
                            pass
                            
                        try:
                            # Try multiple email selectors or regex search in modal html
                            email_el = page.locator(".client_email, #client_email, [class*='email'], [class*='mail']").first
                            if email_el.count() > 0:
                                cust_email = email_el.inner_text().strip()
                            else:
                                modal_html = page.locator("[class*='modal'], [class*='dialog'], [class*='popup']").first.inner_html()
                                m = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', modal_html)
                                if m:
                                    cust_email = m.group(0)
                        except:
                            pass
                            
                        try:
                            # Try to extract quantity
                            qty_text = page.locator(".quantity, .qty, #quantity, #qty, [class*='qty'], [class*='quantity']").first.inner_text()
                            qty = int(re.sub(r'\D', '', qty_text))
                        except:
                            pass
                            
                        try:
                            # Try to extract sale date
                            date_text = page.locator(".sale_date, .order_date, .purchase_date, #sale_date, #order_date, #purchase_date, [class*='date'], [class*='time']").first.inner_text()
                            sale_date = date_text.strip()
                        except:
                            pass
                            
                        # Close the modal
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(1000)
                        
                    # If eye button is not there, or details are in the table columns
                    if not cust_name:
                        # Extract row cells values as fallback
                        row_text = order_row.inner_text()
                        # Simple heuristics to find email/phone in row_text
                        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', row_text)
                        if emails:
                            cust_email = emails[0]
                        # Extract numbers that look like phone
                        phones = re.findall(r'\+?\d[\d\s-]{7,\d}', row_text)
                        if phones:
                            cust_phone = phones[0]
                            
                    # Normalize values
                    first_name, last_name = split_customer_name(cust_name)
                    
                    email = cust_email.strip()
                    if not email or email.lower() in ("none", "null", "n/a"):
                        email = "N/A"
                        
                    mobile = cust_phone.strip()
                    if not mobile or mobile.lower() in ("none", "null", "n/a"):
                        mobile = "N/A"
                        
                    purchase_date, purchase_time = format_purchase_datetime(sale_date)
                    
                    orders_list.append({
                        "order_id": order_id,
                        "first_name": first_name,
                        "last_name": last_name,
                        "mobile_number": mobile,
                        "email": email,
                        "game_purchased": event_name,
                        "purchase_date": purchase_date,
                        "purchase_time": purchase_time,
                        "quantity": qty
                    })
                    print("Extracted customer and game details...")
                    
                except Exception as order_err:
                    print(f"Error scraping order {k+1}: {order_err}")
                    # Write to fail log
                    with open("ftn_failed_orders.log", "a", encoding="utf-8") as f_log:
                        f_log.write(f"Order Index {k+1} under Event '{event_name}': {str(order_err)}\n")
                        
            browser.close()
            return orders_list
            
        except Exception as e:
            try:
                page.screenshot(path="ftn_scrape_failure.png", full_page=True)
                print("Screenshot saved to ftn_scrape_failure.png")
            except:
                pass
            browser.close()
            raise e
