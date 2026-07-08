import json
import time
import os
import random
from datetime import datetime
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import extensions as context
from core.helpers import clean_text
from platforms.base import OrderPlatformAdapter
from config import BASE_DIR, FOOTBALLTICKETNET_STATE_FILE, SENT_FOOTBALLTICKETNET_ORDERS_FILE

load_dotenv()

def save_debug(page, name):
    try:
        html = page.content()
        with open(os.path.join(BASE_DIR, f"debug_ftn_{name}.html"), "w", encoding="utf-8") as f:
            f.write(html)
        page.screenshot(path=os.path.join(BASE_DIR, f"debug_ftn_{name}.png"), full_page=True)
        context.state.log(f"FootballTicketNet: debug saved -> debug_ftn_{name}.html")
    except Exception as e:
        context.state.log(f"FootballTicketNet: save_debug failed -> {e}")

def scrape_ftn_deep(target_event=None):
    from config import PLATFORM_CONFIGS
    config = PLATFORM_CONFIGS.get("FootballTicketNet", {})
    username = config.get("username", "").strip()
    password = config.get("password", "").strip()

    if not username or not password:
        context.state.log("FootballTicketNet: ERROR - credentials not configured in config.py")
        return [], None

    context.state.log(f"FootballTicketNet: using email={username}")
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
        if storage_state:
            context.state.log("FootballTicketNet: loading saved session from disk")

        browser_context = browser.new_context(
            storage_state=storage_state,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-GB",
            timezone_id="Europe/London",
        )

        page = browser_context.new_page()

        # Anti-bot: hide webdriver flag
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Only block images, not CSS/JS (needed for form interaction)
        page.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())

        def is_logged_in_check():
            # FTN uses href="#" for logout, so check by text content
            count = page.locator("a:has-text('Log Out'), a:has-text('Logout'), a:has-text('Sign Out')").count()
            return count > 0

        try:
            # ─── STEP 1: Check if already logged in ─────────────────────
            context.state.log("FootballTicketNet: STEP 1 - loading homepage")
            page.goto("https://www.footballticketnet.com/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

            is_logged_in = is_logged_in_check()
            context.state.log(f"FootballTicketNet: logged_in_check = {is_logged_in}")

            # ─── STEP 2: Login if needed ─────────────────────────────────
            if not is_logged_in:
                context.state.log("FootballTicketNet: STEP 2 - starting login flow")

                # Click the Login button in the top nav
                login_btn = page.locator("a.login_btn").first
                if login_btn.count() == 0:
                    context.state.log("FootballTicketNet: ERROR - login button not found, saving debug")
                    save_debug(page, "no_login_btn")
                    browser.close()
                    return [], None

                login_btn.click()
                page.wait_for_timeout(2000)

                # Click the "Supplier" / "Seller" tab  (exact selector from user's DOM)
                context.state.log("FootballTicketNet: clicking Supplier tab")
                clicked_tab = page.evaluate("""() => {
                    // Try exact path first
                    let btn = document.querySelector('#wrapper > div.top_header.top_header_append > div > div.right_top > div > div.tab > button.tablinks.link_supplier');
                    if (!btn) {
                        // Fallback: any button with class link_supplier
                        btn = document.querySelector('button.link_supplier');
                    }
                    if (!btn) {
                        // Fallback: find by text
                        btn = Array.from(document.querySelectorAll('button.tablinks')).find(b => b.textContent.trim().toLowerCase().includes('supplier') || b.textContent.trim().toLowerCase().includes('seller'));
                    }
                    if (btn) { btn.click(); return btn.textContent.trim(); }
                    return null;
                }""")
                context.state.log(f"FootballTicketNet: Supplier tab click result = {clicked_tab}")
                page.wait_for_timeout(2000)

                # Wait for the supplier form to be visible
                try:
                    page.wait_for_selector("#supplier_email", timeout=10000)
                except Exception:
                    context.state.log("FootballTicketNet: ERROR - supplier_email field not visible after tab click")
                    save_debug(page, "no_supplier_form")
                    browser.close()
                    return [], None

                # Type credentials in a human-like way
                context.state.log("FootballTicketNet: typing email")
                page.locator("#supplier_email").click()
                page.wait_for_timeout(300)
                page.locator("#supplier_email").type(username, delay=random.randint(60, 120))

                context.state.log("FootballTicketNet: typing password")
                page.locator("#supplier_password").click()
                page.wait_for_timeout(300)
                page.locator("#supplier_password").type(password, delay=random.randint(60, 120))
                page.wait_for_timeout(500)

                # Click submit
                context.state.log("FootballTicketNet: clicking submit")
                submit = page.locator("#submit_supplier").first
                if submit.count() > 0:
                    submit.click()
                else:
                    page.keyboard.press("Enter")

                # Wait for result — either logout link or error message
                try:
                    page.wait_for_selector("a:has-text('Logout'), a[href*='logout'], .error-message, .login-error", timeout=20000)
                except Exception:
                    pass

                # Check result
                page.wait_for_timeout(2000)
                save_debug(page, "after_login_attempt")

                if is_logged_in_check():
                    context.state.log("FootballTicketNet: LOGIN SUCCESS - saving session")
                    browser_context.storage_state(path=FOOTBALLTICKETNET_STATE_FILE)
                else:
                    # Extract any error message from page
                    error_msg = ""
                    try:
                        error_el = page.locator(".error, .alert, .notification, [class*='error'], [class*='alert']").first
                        if error_el.count() > 0:
                            error_msg = clean_text(error_el.inner_text())
                    except:
                        pass
                    context.state.log(f"FootballTicketNet: LOGIN FAILED - page_error='{error_msg}' | Check debug_ftn_after_login_attempt.html")
                    browser.close()
                    return [], None

            # ─── STEP 3: Load Supplier Panel & click Delivery tab ────────
            context.state.log("FootballTicketNet: STEP 3 - loading supplier panel")
            page.goto("https://www.footballticketnet.com/supplier-information", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            if not is_logged_in_check():
                context.state.log("FootballTicketNet: ERROR - session lost on supplier-information page")
                if os.path.exists(FOOTBALLTICKETNET_STATE_FILE):
                    os.remove(FOOTBALLTICKETNET_STATE_FILE)
                browser.close()
                return [], None

            # Click the "Delivery" link/tab in the supplier panel nav
            context.state.log("FootballTicketNet: clicking Delivery nav link")
            delivery_nav = page.locator("a[href='?action=delivery_info']:has-text('Delivery')").first
            if delivery_nav.count() == 0:
                delivery_nav = page.locator("a:has-text('Delivery')").first

            if delivery_nav.count() > 0:
                delivery_nav.click()
                context.state.log("FootballTicketNet: clicked Delivery, waiting for AJAX content...")
                # Wait for the table/content to appear after AJAX loads
                try:
                    page.wait_for_selector("table, tr, [class*='event'], [class*='order'], [class*='delivery']", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(3000)
            else:
                context.state.log("FootballTicketNet: Delivery link not found, trying direct URL")
                page.goto("https://www.footballticketnet.com/?action=delivery_info", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)

            save_debug(page, "delivery_page")
            page_title = page.title()
            page_url = page.url
            context.state.log(f"FootballTicketNet: delivery page title='{page_title}' url='{page_url}'")

            # ─── STEP 4: Parse HTML to discover real selectors ───────────
            from bs4 import BeautifulSoup
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            all_trs = soup.find_all("tr")
            context.state.log(f"FootballTicketNet: total <tr> on delivery page = {len(all_trs)}")

            tr_classes_seen = set()
            for tr in all_trs[:100]:
                cls = " ".join(tr.get("class", []))
                if cls:
                    tr_classes_seen.add(cls)
            context.state.log(f"FootballTicketNet: tr classes found = {tr_classes_seen}")

            # Also log any divs/containers with delivery-related classes
            delivery_divs = soup.find_all(attrs={"class": lambda c: c and any("delivery" in x.lower() or "event" in x.lower() or "order" in x.lower() for x in (c if isinstance(c,list) else [c]))})
            div_classes = set(" ".join(d.get("class",[])) for d in delivery_divs[:20])
            context.state.log(f"FootballTicketNet: delivery/event/order div classes = {div_classes}")

            # ─── STEP 5: Identify event rows ─────────────────────────────
            # Try several selectors based on common FTN patterns
            event_rows = page.locator("tr.event_row_delivery, tr[class*='event'], tr[onclick*='event'], [class*='event_row']")
            count = event_rows.count()
            context.state.log(f"FootballTicketNet: event rows found = {count}")

            if count == 0:
                context.state.log("FootballTicketNet: WARN - 0 events. Check debug_ftn_delivery_page.html for real selector")
                browser.close()
                return [], None

            for i in range(count):
                row = event_rows.nth(i)
                event_name = clean_text(row.inner_text())

                if target_event and target_event.lower() not in event_name.lower():
                    continue

                context.state.log(f"FootballTicketNet: opening event[{i}] -> {event_name}")
                row.click()
                page.wait_for_timeout(2000)

                # ─── STEP 6: Categories ───────────────────────────────────
                cat_rows = page.locator("tr.category_row, tr[class*='cat'], [class*='category_row']")
                for j in range(cat_rows.count()):
                    cat_row = cat_rows.nth(j)
                    cat_name = clean_text(cat_row.inner_text())
                    cat_row.click()
                    page.wait_for_timeout(2000)

                    # ─── STEP 7: Orders ───────────────────────────────────
                    order_rows = page.locator("tr.order_row_delivery, tr[class*='order_row'], [class*='order_id_delivery']")
                    for k in range(order_rows.count()):
                        order_row = order_rows.nth(k)
                        eye = order_row.locator("i.fa-eye, .fa-eye, .view_order_btn, [class*='view']").first
                        if eye.count() == 0:
                            continue

                        eye.click()
                        page.wait_for_timeout(3000)

                        try:
                            oid = clean_text(page.locator(".order_id, #order_id_val, [class*='order_id']").first.inner_text()).replace("Order #", "").strip()
                            cust = clean_text(page.locator(".client_name, #client_name, [class*='client_name']").first.inner_text())
                            phone = clean_text(page.locator(".client_phone, #client_phone, [class*='client_phone']").first.inner_text())
                            stat = clean_text(page.locator(".order_status, #order_status, [class*='order_status']").first.inner_text())

                            results.append({
                                "id": oid,
                                "event": event_name,
                                "category": cat_name,
                                "customer": cust,
                                "phone": phone,
                                "status": stat,
                                "source": "FootballTicketNet",
                                "sale_date": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                            })
                            context.state.log(f"FootballTicketNet: extracted order {oid}")
                        except Exception as e:
                            context.state.log(f"FootballTicketNet: modal extraction error -> {repr(e)}")
                            save_debug(page, f"modal_error_{k}")

                        page.keyboard.press("Escape")
                        page.wait_for_timeout(1000)

            browser.close()
            context.state.log(f"FootballTicketNet: DONE - total orders extracted = {len(results)}")
            return results, results[0] if results else None

        except Exception as e:
            context.state.log(f"FootballTicketNet: UNHANDLED ERROR -> {repr(e)}")
            try:
                save_debug(page, "exception")
            except:
                pass
            browser.close()
            return [], None


class FootballTicketNetAdapter(OrderPlatformAdapter):
    def __init__(self, config):
        super().__init__("FootballTicketNet", config)

    def fetch_orders(self):
        return scrape_ftn_deep()

    def fetch_orders_by_event(self, event_name):
        res, _ = scrape_ftn_deep(target_event=event_name)
        return res
