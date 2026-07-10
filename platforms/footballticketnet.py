import json
import time
import os
import random
import re
from datetime import datetime
from playwright.sync_api import sync_playwright
import extensions as context
from core.helpers import clean_text, parse_sale_datetime, parse_event_datetime, standardize_status
from platforms.base import OrderPlatformAdapter
from config import BASE_DIR, FOOTBALLTICKETNET_STATE_FILE
from core.logger import get_logger
from core.errors import PlatformLoginError, PlatformBlockedError, PlatformLayoutError, PlatformTimeoutError, PlatformMissingDataError

logger = get_logger("FootballTicketNet")

class FootballTicketNetAdapter(OrderPlatformAdapter):
    def __init__(self, config):
        super().__init__("FootballTicketNet", config)

    def save_debug(self, page, name):
        try:
            html = page.content()
            debug_html_path = os.path.join(BASE_DIR, f"debug_ftn_{name}.html")
            debug_png_path = os.path.join(BASE_DIR, f"debug_ftn_{name}.png")
            with open(debug_html_path, "w", encoding="utf-8") as f:
                f.write(html)
            page.screenshot(path=debug_png_path, full_page=True)
            logger.info(f"debug saved -> debug_ftn_{name}.html / .png")
        except Exception as e:
            logger.warning(f"save_debug failed -> {e}")

    def _login_internal(self, page):
        """
        Internal helper to perform the form actions to log in on a given page.
        """
        username = self.config.get("username", "").strip()
        password = self.config.get("password", "").strip()
        
        is_logged_in = page.locator("a:has-text('Log Out'), a:has-text('Logout'), a:has-text('Sign Out')").count() > 0
        if is_logged_in:
            return True

        logger.info("starting login flow...")
        login_btn = page.locator("a.login_btn").first
        if login_btn.count() == 0:
            self.save_debug(page, "no_login_btn")
            # If login button is missing, we might be blocked or page did not load
            if "captcha" in page.content().lower() or "cloudflare" in page.content().lower():
                raise PlatformBlockedError("IP blocked or Cloudflare challenge active on homepage.")
            raise PlatformLayoutError("Login button 'a.login_btn' not found. Layout might have changed.")

        login_btn.click()
        page.wait_for_timeout(2000)

        # Click the Supplier/Seller tab
        page.evaluate("""() => {
            let btn = document.querySelector('button.link_supplier');
            if (!btn) {
                btn = document.querySelector('#wrapper > div.top_header.top_header_append > div > div.right_top > div > div.tab > button.tablinks.link_supplier');
            }
            if (!btn) {
                btn = Array.from(document.querySelectorAll('button.tablinks')).find(b => b.textContent.trim().toLowerCase().includes('supplier') || b.textContent.trim().toLowerCase().includes('seller'));
            }
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(2000)

        try:
            page.wait_for_selector("#supplier_email", timeout=10000)
        except Exception:
            self.save_debug(page, "no_supplier_form")
            raise PlatformTimeoutError("Supplier login form email field failed to load.")

        page.locator("#supplier_email").fill(username)
        page.locator("#supplier_password").fill(password)
        page.wait_for_timeout(500)

        submit = page.locator("#submit_supplier").first
        if submit.count() > 0:
            submit.click()
        else:
            page.keyboard.press("Enter")

        page.wait_for_timeout(3000)
        is_ok = page.locator("a:has-text('Log Out'), a:has-text('Logout'), a:has-text('Sign Out')").count() > 0
        if is_ok:
            logger.info("login successful.")
            return True
        else:
            self.save_debug(page, "login_failed")
            error_msg = "Invalid credentials or session rejected."
            try:
                error_el = page.locator(".error, .alert, .notification, [class*='error'], [class*='alert']").first
                if error_el.count() > 0:
                    error_msg = error_el.inner_text().strip()
            except:
                pass
            raise PlatformLoginError(f"Login failed: {error_msg}")

    # =========================================================
    # UNIFIED PLATFORM ADAPTER INTERFACE
    # =========================================================

    def login(self):
        """
        Authenticate and save browser context state.
        """
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
            page.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())

            try:
                page.goto("https://www.footballticketnet.com/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                
                success = self._login_internal(page)
                if success:
                    browser_context.storage_state(path=FOOTBALLTICKETNET_STATE_FILE)
                browser.close()
                return success
            except Exception as e:
                logger.error(f"login exception: {e}")
                browser.close()
                raise e

    def get_orders(self):
        """
        Crawl FootballTicketNet delivery panel for orders.
        """
        results = []
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
            storage_state = FOOTBALLTICKETNET_STATE_FILE if os.path.exists(FOOTBALLTICKETNET_STATE_FILE) else None
            browser_context = browser.new_context(
                storage_state=storage_state,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-GB",
                timezone_id="Europe/London",
            )
            page = browser_context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())

            try:
                page.goto("https://www.footballticketnet.com/supplier-information", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)

                # Check login
                if not (page.locator("a:has-text('Log Out'), a:has-text('Logout'), a:has-text('Sign Out')").count() > 0):
                    page.goto("https://www.footballticketnet.com/", wait_until="domcontentloaded", timeout=60000)
                    if not self._login_internal(page):
                        browser.close()
                        return []
                    browser_context.storage_state(path=FOOTBALLTICKETNET_STATE_FILE)
                    page.goto("https://www.footballticketnet.com/supplier-information", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2000)

                # Navigate to delivery page
                delivery_nav = page.locator("a[href='?action=delivery_info']:has-text('Delivery')").first
                if delivery_nav.count() == 0:
                    delivery_nav = page.locator("a:has-text('Delivery')").first
                
                if delivery_nav.count() > 0:
                    delivery_nav.click()
                    page.wait_for_timeout(3000)
                else:
                    page.goto("https://www.footballticketnet.com/?action=delivery_info", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3000)

                self.save_debug(page, "delivery_page")

                # Expand all events
                event_rows = page.locator("tr.event_row_delivery, tr[class*='event'], tr[onclick*='event'], [class*='event_row']")
                count = event_rows.count()
                for i in range(count):
                    try:
                        event_rows.nth(i).click()
                        page.wait_for_timeout(1000)
                    except: pass

                # Expand all categories
                cat_rows = page.locator("tr.category_row, tr[class*='cat'], [class*='category_row']")
                for j in range(cat_rows.count()):
                    try:
                        cat_row.nth(j).click()
                        page.wait_for_timeout(1000)
                    except: pass

                # Parse rows
                order_rows = page.locator("tr.order_row_delivery, tr[class*='order_row'], [class*='order_id_delivery']")
                total_orders = order_rows.count()
                for k in range(total_orders):
                    order_row = order_rows.nth(k)
                    try:
                        event_name = page.evaluate(f"""(rowIdx) => {{
                            let rows = Array.from(document.querySelectorAll("tr"));
                            let orderRow = document.querySelectorAll("tr.order_row_delivery, tr[class*='order_row'], [class*='order_id_delivery']")[rowIdx];
                            if (!orderRow) return "Unknown Event";
                            let idx = rows.indexOf(orderRow);
                            for (let i = idx; i >= 0; i--) {{
                                let r = rows[i];
                                if (r.classList.contains("event_row_delivery") || r.className.includes("event") || r.getAttribute("onclick")?.includes("event")) {{
                                    return r.textContent.trim();
                                }}
                            }}
                            return "Unknown Event";
                        }}""", k)

                        # Extract details from page cells or click eye modal
                        eye = order_row.locator("i.fa-eye, .fa-eye, .view_order_btn, [class*='view']").first
                        if eye.count() > 0:
                            eye.click()
                            page.wait_for_timeout(2000)
                            
                            oid = clean_text(page.locator(".order_id, #order_id_val, [class*='order_id']").first.inner_text()).replace("Order #", "").strip()
                            cust = clean_text(page.locator(".client_name, #client_name, [class*='client_name']").first.inner_text())
                            phone = clean_text(page.locator(".client_phone, #client_phone, [class*='client_phone']").first.inner_text())
                            stat = clean_text(page.locator(".order_status, #order_status, [class*='order_status']").first.inner_text())

                            results.append({
                                "id": oid,
                                "event": event_name,
                                "customer": cust,
                                "phone": phone,
                                "status": stat,
                                "source": self.source_name,
                                "sale_date": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                            })
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(1000)
                    except Exception as e:
                        logger.warning(f"error parsing row {k}: {e}")
                        self.save_debug(page, f"row_error_{k}")
                        try: page.keyboard.press("Escape")
                        except: pass

                browser.close()
                return results
            except Exception as e:
                self.save_debug(page, "error")
                browser.close()
                raise e

    def get_customers(self):
        """
        Fetch historical customer/order listing from FootballTicketNet.
        """
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
            storage_state = FOOTBALLTICKETNET_STATE_FILE if os.path.exists(FOOTBALLTICKETNET_STATE_FILE) else None
            browser_context = browser.new_context(
                storage_state=storage_state,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-GB",
                timezone_id="Europe/London",
            )
            page = browser_context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())

            try:
                page.goto("https://www.footballticketnet.com/supplier-information", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)

                # Check login
                if not (page.locator("a:has-text('Log Out'), a:has-text('Logout'), a:has-text('Sign Out')").count() > 0):
                    page.goto("https://www.footballticketnet.com/", wait_until="domcontentloaded", timeout=60000)
                    if not self._login_internal(page):
                        browser.close()
                        return []
                    browser_context.storage_state(path=FOOTBALLTICKETNET_STATE_FILE)
                    page.goto("https://www.footballticketnet.com/supplier-information", wait_until="domcontentloaded", timeout=60000)

                page.goto("https://www.footballticketnet.com/?action=delivery_info", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)

                # Expand rows
                event_rows = page.locator("tr.event_row_delivery, tr[class*='event'], tr[onclick*='event'], [class*='event_row']")
                for i in range(event_rows.count()):
                    try: event_rows.nth(i).click(); page.wait_for_timeout(500)
                    except: pass
                
                cat_rows = page.locator("tr.category_row, tr[class*='cat'], [class*='category_row']")
                for j in range(cat_rows.count()):
                    try: cat_rows.nth(j).click(); page.wait_for_timeout(500)
                    except: pass

                # Scraping rows
                order_rows = page.locator("tr.order_row_delivery, tr[class*='order_row'], [class*='order_id_delivery']")
                total_orders = order_rows.count()

                for k in range(total_orders):
                    order_row = order_rows.nth(k)
                    try:
                        event_name = page.evaluate(f"""(rowIdx) => {{
                            let rows = Array.from(document.querySelectorAll("tr"));
                            let orderRow = document.querySelectorAll("tr.order_row_delivery, tr[class*='order_row'], [class*='order_id_delivery']")[rowIdx];
                            if (!orderRow) return "Unknown Event";
                            let idx = rows.indexOf(orderRow);
                            for (let i = idx; i >= 0; i--) {{
                                let r = rows[i];
                                if (r.classList.contains("event_row_delivery") || r.className.includes("event") || r.getAttribute("onclick")?.includes("event")) {{
                                    return r.textContent.trim();
                                }}
                            }}
                            return "Unknown Event";
                        }}""", k)

                        cust_name = ""
                        cust_phone = ""
                        cust_email = ""
                        qty = 1
                        sale_date = ""
                        order_id = f"FTN_TEMP_{k}"

                        eye = order_row.locator("i.fa-eye, .fa-eye, .view_order_btn, [class*='view']").first
                        if eye.count() > 0:
                            eye.click()
                            page.wait_for_timeout(2500)
                            
                            try:
                                id_text = page.locator(".order_id, #order_id_val, [class*='order_id']").first.inner_text()
                                order_id = id_text.replace("Order #", "").replace("Order", "").strip()
                            except: pass
                            
                            try: cust_name = page.locator(".client_name, #client_name, [class*='client_name']").first.inner_text().strip()
                            except: pass
                            
                            try: cust_phone = page.locator(".client_phone, #client_phone, [class*='client_phone']").first.inner_text().strip()
                            except: pass
                            
                            try:
                                email_el = page.locator(".client_email, #client_email, [class*='email'], [class*='mail']").first
                                if email_el.count() > 0:
                                    cust_email = email_el.inner_text().strip()
                                else:
                                    modal_html = page.locator("[class*='modal'], [class*='dialog'], [class*='popup']").first.inner_html()
                                    m = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', modal_html)
                                    if m: cust_email = m.group(0)
                            except: pass
                            
                            try:
                                qty_text = page.locator(".quantity, .qty, #quantity, #qty, [class*='qty'], [class*='quantity']").first.inner_text()
                                qty = int(re.sub(r'\D', '', qty_text))
                            except: pass
                            
                            try:
                                date_text = page.locator(".sale_date, .order_date, .purchase_date, #sale_date, #order_date, #purchase_date, [class*='date'], [class*='time']").first.inner_text()
                                sale_date = date_text.strip()
                            except: pass

                            page.keyboard.press("Escape")
                            page.wait_for_timeout(1000)

                        parts = cust_name.strip().split(maxsplit=1)
                        if len(parts) == 2:
                            first_name, last_name = parts[0], parts[1]
                        elif len(parts) == 1:
                            first_name, last_name = parts[0], "-"
                        else:
                            first_name, last_name = "-", "-"

                        orders_list.append({
                            "order_id": order_id,
                            "first_name": first_name,
                            "last_name": last_name,
                            "mobile_number": cust_phone or "N/A",
                            "email": cust_email or "N/A",
                            "game_purchased": event_name,
                            "purchase_date": sale_date.split()[0] if sale_date else "N/A",
                            "purchase_time": sale_date.split()[1] if sale_date and len(sale_date.split()) > 1 else "N/A",
                            "quantity": qty
                        })
                    except Exception as e:
                        logger.warning(f"error extracting customer history row {k}: {e}")
                        try: page.keyboard.press("Escape")
                        except: pass

                browser.close()
                return orders_list
            except Exception as e:
                self.save_debug(page, "cust_history_error")
                browser.close()
                raise e

    def get_order_details(self, order_id):
        """
        Crawl FootballTicketNet for details on a specific order ID.
        """
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
            storage_state = FOOTBALLTICKETNET_STATE_FILE if os.path.exists(FOOTBALLTICKETNET_STATE_FILE) else None
            browser_context = browser.new_context(
                storage_state=storage_state,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-GB",
                timezone_id="Europe/London",
            )
            page = browser_context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())

            try:
                page.goto("https://www.footballticketnet.com/supplier-information", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)

                # Check login
                if not (page.locator("a:has-text('Log Out'), a:has-text('Logout'), a:has-text('Sign Out')").count() > 0):
                    page.goto("https://www.footballticketnet.com/", wait_until="domcontentloaded", timeout=60000)
                    if not self._login_internal(page):
                        browser.close()
                        return {}
                    browser_context.storage_state(path=FOOTBALLTICKETNET_STATE_FILE)
                    page.goto("https://www.footballticketnet.com/supplier-information", wait_until="domcontentloaded", timeout=60000)

                page.goto("https://www.footballticketnet.com/?action=delivery_info", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)

                # Expand rows
                event_rows = page.locator("tr.event_row_delivery, tr[class*='event'], tr[onclick*='event'], [class*='event_row']")
                for i in range(event_rows.count()):
                    try: event_rows.nth(i).click(); page.wait_for_timeout(300)
                    except: pass
                
                cat_rows = page.locator("tr.category_row, tr[class*='cat'], [class*='category_row']")
                for j in range(cat_rows.count()):
                    try: cat_rows.nth(j).click(); page.wait_for_timeout(300)
                    except: pass

                # Locate our target order_id row
                order_rows = page.locator("tr.order_row_delivery, tr[class*='order_row'], [class*='order_id_delivery']")
                total_orders = order_rows.count()

                details = {}
                for k in range(total_orders):
                    row = order_rows.nth(k)
                    row_text = row.inner_text()
                    if order_id in row_text:
                        eye = row.locator("i.fa-eye, .fa-eye, .view_order_btn, [class*='view']").first
                        if eye.count() > 0:
                            eye.click()
                            page.wait_for_timeout(2500)
                            
                            cust_name = page.locator(".client_name, #client_name, [class*='client_name']").first.inner_text().strip()
                            cust_phone = page.locator(".client_phone, #client_phone, [class*='client_phone']").first.inner_text().strip()
                            cust_email = ""
                            try:
                                email_el = page.locator(".client_email, #client_email, [class*='email'], [class*='mail']").first
                                if email_el.count() > 0:
                                    cust_email = email_el.inner_text().strip()
                                else:
                                    modal_html = page.locator("[class*='modal'], [class*='dialog'], [class*='popup']").first.inner_html()
                                    m = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', modal_html)
                                    if m: cust_email = m.group(0)
                            except: pass

                            details = {
                                "order_number": order_id,
                                "customer_name": cust_name,
                                "mobile_number": cust_phone,
                                "email": cust_email,
                                "details_fetched_at": datetime.utcnow()
                            }
                            page.keyboard.press("Escape")
                            break

                browser.close()
                if not details:
                    raise PlatformMissingDataError(f"Could not locate order details modal for {order_id} in delivery lists.")
                return details
            except Exception as e:
                self.save_debug(page, f"details_error_{order_id}")
                browser.close()
                raise e

    def save_orders(self, orders):
        """
        Save/synchronize orders list to DB.
        """
        from database import get_db, DBOrder
        db = get_db()
        if not db:
            return
        try:
            for r in orders:
                oid = clean_text(r.get("id", ""))
                if not oid: continue
                dbo = db.query(DBOrder).filter(DBOrder.platform == self.source_name, DBOrder.order_number == oid).first()
                
                pod = dbo.pod_status if dbo else "Pending"
                dash_status = standardize_status(r.get("status"), source=self.source_name, resale_status=r.get("resale_status"), pod_status=pod)
                
                if not dbo:
                    dbo = DBOrder(
                        platform=self.source_name, order_number=oid, event_name=r.get("event"),
                        customer_name=r.get("customer"), raw_status=r.get("status"),
                        resale_status=r.get("resale_status"), normalized_status=dash_status,
                        total_value=r.get("total_price"), currency=r.get("currency", "£"), quantity=r.get("quantity", 1),
                        is_visible_on_platform=True
                    )
                    db.add(dbo)
                else:
                    dbo.raw_status = r.get("status")
                    dbo.resale_status = r.get("resale_status")
                    dbo.normalized_status = dash_status
                    dbo.is_visible_on_platform = True
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"save_orders failed: {e}")
        finally:
            db.close()

    # =========================================================
    # BACKWARD COMPATIBILITY ALIASES
    # =========================================================

    def fetch_orders(self):
        rows = self.get_orders()
        return rows, rows[0] if rows else None

    def fetch_orders_by_event(self, event_name):
        rows = self.get_orders()
        return [r for r in rows if event_name.lower() in r.get("event", "").lower()]

def get_ftn_adapter():
    for item in context.platform_adapters:
        if getattr(item, "source_name", "") == "FootballTicketNet": 
            return item
    return None
