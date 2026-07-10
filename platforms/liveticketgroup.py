import os
import re
import json
from datetime import datetime
from curl_cffi import requests
from bs4 import BeautifulSoup
import extensions as context
from config import ORDER_STATE_FILE, DEBUG_ORDER_DETAILS_HTML, LOGIN_STATE_TREE_ENCODED, DEBUG_ORDERS_HTML
from core.storage import load_json_file, save_json_file
from core.helpers import clean_text, parse_sale_datetime, to_number, parse_event_datetime, standardize_status
from platforms.base import OrderPlatformAdapter
from core.logger import get_logger
from core.errors import PlatformLoginError, PlatformBlockedError, PlatformLayoutError, PlatformTimeoutError

logger = get_logger("LiveTicketGroup")

class LiveTicketGroupAdapter(OrderPlatformAdapter):
    def __init__(self, config):
        super().__init__("LiveTicketGroup", config)
        self.session = requests.Session()
        self.next_action = None
        self.restore_session()

    # =========================================================
    # UNIFIED PLATFORM ADAPTER INTERFACE
    # =========================================================

    def login(self):
        """
        Authenticate with LiveTicketGroup next.js endpoints.
        """
        logger.info("logging in...")
        self.fetch_next_action()
        if not self.next_action:
            raise PlatformLoginError("login failed - next_action token not found on homepage. Layout might have changed.")
            
        payload = json.dumps([{"email": self.config["username"], "password": self.config["password"]}])
        try:
            r = self.session.post(
                self.config["login_url"],
                headers={
                    "accept": "text/x-component",
                    "content-type": "text/plain;charset=UTF-8",
                    "next-action": self.next_action,
                    "next-router-state-tree": LOGIN_STATE_TREE_ENCODED
                },
                data=payload,
                timeout=30
            )
            
            if r.status_code == 403 or "blocked" in r.text.lower():
                raise PlatformBlockedError("Login request was blocked or forbidden by security shield.")

            m = re.search(r'"NEXT_REDIRECT;replace;(.*?);', r.text)
            if m:
                self.session.get(m.group(1), allow_redirects=True, timeout=30)
                self.persist_session()
                logger.info("login successful.")
                return True
            else:
                logger.warning(f"NEXT_REDIRECT match failed. Status: {r.status_code}. Response: {r.text[:300]}")
                raise PlatformLoginError("Login failed: redirection payload not found. Check credentials or site structure.")
        except requests.exceptions.Timeout:
            raise PlatformTimeoutError("Login request timed out.")
        except PlatformLoginError as le:
            raise le
        except PlatformBlockedError as be:
            raise be
        except Exception as e:
            raise PlatformLoginError(f"login HTTP post failed: {e}")

    def get_orders(self):
        """
        Retrieve recent/urgent orders.
        """
        logger.info("fetching urgent orders...")
        url = "https://my.liveticketgroup.com/pages/content/index.aspx?topnav=1&subnav=4"
        try:
            html = self.ensure_logged_in(url)
        except PlatformLoginError as le:
            raise le
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Submit the urgent orders filter (672 for 4 weeks)
        dropdown = soup.find("select", {"name": "ctl00$plcContent$urcDashBoard$urcToBeDispatch$drpUrgentOrders"})
        if dropdown:
            data = {
                "__VIEWSTATE": soup.find("input", id="__VIEWSTATE")["value"] if soup.find("input", id="__VIEWSTATE") else "",
                "__VIEWSTATEGENERATOR": soup.find("input", id="__VIEWSTATEGENERATOR")["value"] if soup.find("input", id="__VIEWSTATEGENERATOR") else "",
                "__EVENTVALIDATION": soup.find("input", id="__EVENTVALIDATION")["value"] if soup.find("input", id="__EVENTVALIDATION") else "",
                "ctl00$plcContent$urcDashBoard$urcToBeDispatch$drpUrgentOrders": "672",
            }
            try:
                r_post = self.session.post(url, data=data, timeout=30)
                rows, _ = self.parse_orders_from_html(r_post.text)
                if rows: 
                    return rows
            except Exception as e:
                logger.warning(f"Failed to fetch urgent orders filter: {e}. Falling back to default list.")
        
        # Fallback to general parsing
        rows, _ = self.parse_orders_from_html(html)
        return rows

    def get_customers(self):
        """
        Scrapes pagination pages to build customer history log.
        """
        logger.info("starting customer history retrieval...")
        self.ensure_logged_in()
        order_ids = self._get_all_historical_order_ids()
        logger.info(f"Total unique historical orders found: {len(order_ids)}")
        
        customers = []
        from database import get_db, DBOrder
        db = get_db()
        existing_orders_map = {}
        if db:
            try:
                db_orders = db.query(DBOrder).filter(DBOrder.platform == self.source_name).all()
                for dbo in db_orders:
                    existing_orders_map[str(dbo.order_number)] = dbo
            except Exception as db_err:
                logger.warning(f"database warning while fetching existing orders: {db_err}")
            finally:
                db.close()
                
        for idx, oid in enumerate(order_ids, start=1):
            # Check DB cache first
            dbo = existing_orders_map.get(str(oid))
            if dbo and (dbo.email or dbo.mobile_number):
                cust_details = {
                    "billing_full_name": dbo.billing_full_name or dbo.customer_name,
                    "customer_name": dbo.customer_name,
                    "billing_mobile": dbo.billing_mobile or dbo.mobile_number,
                    "mobile_number": dbo.mobile_number,
                    "email": dbo.email
                }
                cust = self._extract_customer_from_details(cust_details)
                if cust:
                    customers.append(cust)
                    continue
                    
            try:
                details = self.get_order_details(oid)
                if details:
                    cust = self._extract_customer_from_details(details)
                    if cust:
                        customers.append(cust)
            except Exception as e:
                logger.error(f"Error processing order customer {oid}: {e}")
                
        return customers

    def get_order_details(self, order_id):
        """
        Fetch details for a single order by ID.
        """
        self.ensure_logged_in()
        url = f"https://www.liveticketgroup.com/orders/{order_id}"
        
        try:
            r = self.session.get(url, timeout=30, allow_redirects=True)
            html = r.text
        except requests.exceptions.Timeout:
            raise PlatformTimeoutError(f"Request for order details {order_id} timed out.")
        except Exception as e:
            raise PlatformLayoutError(f"HTTP call to details {order_id} failed: {e}")
        
        # Check if Next.js session expired and redirected to login
        if "name=\"email\"" in html.lower() or "login" in r.url.lower() or "Exception:" in html:
            self.login()
            r = self.session.get(url, timeout=30, allow_redirects=True)
            html = r.text
            if "name=\"email\"" in html.lower() or "login" in r.url.lower() or "Exception:" in html:
                raise PlatformLoginError("Session expired. Please re-login.")
        
        # Unescape Next.js JSON state
        html_clean = html.replace('\\"', '"').replace('\\\\', '\\')
        
        try:
            m = re.search(r'"data":(\{"id":' + str(order_id) + r'.*?"problematicOrderNotes":\[.*?\]\})', html_clean)
            if m: 
                return self._map_ltg_json_to_db(json.loads(m.group(1)), html, url)
            
            m2 = re.search(r'(\{"id":' + str(order_id) + r',.*?"problematicOrderNotes":\[.*?\]\})', html)
            if m2: 
                return self._map_ltg_json_to_db(json.loads(m2.group(1)), html, url)
        except Exception as parse_err:
            logger.warning(f"JSON extraction regex failed for details: {parse_err}. Falling back to HTML parsing.")
            
        return self._parse_ltg_details_html(html, order_id, url)

    def save_orders(self, orders):
        """
        Insert or update a list of scraped order dictionaries.
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

    def fetch_order_details(self, order_id):
        return self.get_order_details(order_id)

    def fetch_orders_by_event(self, event_name):
        html = self.ensure_logged_in("https://my.liveticketgroup.com/pages/content/orders.aspx?topnav=1&subnav=26")
        soup = BeautifulSoup(html, "html.parser")
        data = {
            "__VIEWSTATE": soup.find("input", id="__VIEWSTATE")["value"] if soup.find("input", id="__VIEWSTATE") else "",
            "__VIEWSTATEGENERATOR": soup.find("input", id="__VIEWSTATEGENERATOR")["value"] if soup.find("input", id="__VIEWSTATEGENERATOR") else "",
            "__EVENTVALIDATION": soup.find("input", id="__EVENTVALIDATION")["value"] if soup.find("input", id="__EVENTVALIDATION") else "",
            "ctl00$plcContent$urcSearch$txtEventName": event_name,
            "ctl00$plcContent$urcSearch$txtStartDate": "2024-01-01",
            "ctl00$plcContent$urcSearch$btnSearch": "Search"
        }
        try:
            r_post = self.session.post("https://my.liveticketgroup.com/pages/content/orders.aspx?topnav=1&subnav=26", data=data, timeout=30)
            rows, _ = self.parse_orders_from_html(r_post.text)
            return rows
        except Exception as e:
            logger.error(f"fetch_orders_by_event failed: {e}")
            return []

    # =========================================================
    # INTERNAL SCRAPER HELPERS
    # =========================================================

    def restore_session(self):
        data = load_json_file(ORDER_STATE_FILE, {}).get(self.source_name, {})
        self.next_action = data.get("next_action")
        for k, v in data.get("cookies", {}).items():
            try: 
                self.session.cookies.set(k, v)
            except: 
                pass

    def persist_session(self):
        data = load_json_file(ORDER_STATE_FILE, {})
        cookies = {}
        try:
            for c in self.session.cookies:
                if hasattr(c, 'name'): 
                    cookies[c.name] = c.value
                elif isinstance(c, str): 
                    cookies[c] = self.session.cookies.get(c)
        except: 
            pass
        data[self.source_name] = {"cookies": cookies, "next_action": self.next_action}
        save_json_file(ORDER_STATE_FILE, data)

    def looks_authenticated_response(self, response):
        return "my.liveticketgroup.com" in str(response.url).lower() and 'name="email"' not in response.text.lower()

    def fetch_next_action(self):
        try:
            r = self.session.get(self.config["login_url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            chunks = re.findall(r'(/_next/static/chunks/[^"\']+?\.js)', r.text)
            for c in chunks:
                try:
                    js = self.session.get("https://www.liveticketgroup.com" + c, timeout=30).text
                    m = re.search(r'createServerReference\)\("(.*?)"', js)
                    if m: 
                        self.next_action = m.group(1)
                        break
                except: 
                    continue
        except Exception as e: 
            logger.warning(f"next_action token fetch error: {e}")
        self.persist_session()

    def ensure_logged_in(self, target_url=None):
        url = target_url or "https://my.liveticketgroup.com/pages/content/orders.aspx?topnav=1&subnav=26"
        try:
            r = self.session.get(url, timeout=30)
            if "Exception:" in r.text and "Refresh token" in r.text:
                raise PlatformLoginError("LiveTicketGroup session expired. Please re-login.")
            if self.looks_authenticated_response(r): 
                return r.text
        except PlatformLoginError as pe:
            raise pe
        except Exception as e:
            pass
        
        self.login()
        r2 = self.session.get(url, timeout=30)
        if "Exception:" in r2.text and "Refresh token" in r2.text:
            raise PlatformLoginError("LiveTicketGroup session expired. Please re-login.")
        return r2.text

    def parse_orders_from_html(self, html):
        if not html: 
            return [], None
        with open(DEBUG_ORDERS_HTML, "w", encoding="utf-8") as f: 
            f.write(html)
        soup = BeautifulSoup(html, "html.parser")
        table = None
        for t in soup.find_all("table"):
            h = [x.get_text().lower() for x in t.find_all(["th", "td"])[:30]]
            if any("id" in x for x in h) and (any("status" in x for x in h) or any("event" in x for x in h)):
                table = t
                break
        if not table: 
            if "captcha" in html.lower() or "cloudflare" in html.lower() or "blocked" in html.lower():
                raise PlatformBlockedError("LiveTicketGroup blocked our request (Captcha/Cloudflare/Blocked).")
            if 'name="email"' in html.lower() or "login" in html.lower():
                raise PlatformLoginError("LiveTicketGroup session expired / redirection to login page detected.")
            raise PlatformLayoutError("Orders list table element not found on page. Layout might have changed.")
            
        rows = []
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) < 5: 
                continue
            headers = [clean_text(th.get_text()).lower() for th in table.find_all("tr")[0].find_all(["th", "td"])]
            id_idx = next((i for i, h in enumerate(headers) if h == "id"), 0)
            
            if len(tds) <= id_idx: 
                continue
            oid_txt = clean_text(tds[id_idx].get_text())
            if not oid_txt.isdigit(): 
                continue
            
            def get_val(lbls):
                for l in lbls:
                    for i, h in enumerate(headers):
                        if h == l:
                            if i < len(tds): 
                                return clean_text(tds[i].get_text())
                for l in lbls:
                    for i, h in enumerate(headers):
                        if l in h:
                            if i < len(tds): 
                                return clean_text(tds[i].get_text())
                return None

            rows.append({
                "id": oid_txt, 
                "status": get_val(["status"]) or "Unknown",
                "resale_status": get_val(["resale", "resale status"]),
                "customer": get_val(["customer", "buyer", "attendees"]) or "-",
                "sale_date": get_val(["sale date"]) or "-",
                "event_date": get_val(["event date"]) or "-",
                "event": get_val(["event"]) or "-",
                "quantity": to_number(get_val(["qty", "quantity", "tickets"])) or 1,
                "total_price": to_number(get_val(["total", "price", "value"])),
                "currency": "£", 
                "source": self.source_name
            })
        return rows, rows[0] if rows else None

    def _map_ltg_json_to_db(self, data, html, source_url):
        if not isinstance(data, dict): 
            return {}
        buyer = data.get("buyer") or {}
        tinfo = data.get("ticketInfo") or {}
        pdet = tinfo.get("pricingDetails") or {}
        show = data.get("show") or {}
        seating_list = tinfo.get("seating", [])
        seat_names = [str(s.get("name", "")) if isinstance(s, dict) else str(s) for s in seating_list]
        return {
            "event_name": show.get("name") if isinstance(show, dict) else str(show), 
            "event_date": parse_event_datetime(show.get("showDate")) if isinstance(show, dict) else None,
            "customer_name": buyer.get("fullName"), 
            "billing_full_name": buyer.get("fullName"),
            "mobile_number": buyer.get("shipping", {}).get("mobile") or buyer.get("billing", {}).get("mobile"),
            "billing_mobile": buyer.get("billing", {}).get("mobile"), 
            "email": buyer.get("email"),
            "sale_date": parse_sale_datetime(data.get("createdOn")), 
            "raw_status": data.get("status"), 
            "resale_status": data.get("resaleStatus"),
            "category": tinfo.get("category"), 
            "section": tinfo.get("section") or tinfo.get("category"),
            "row_name": tinfo.get("row"), 
            "seat_number": ", ".join(seat_names),
            "quantity": tinfo.get("quantity"), 
            "list_price_per_ticket": to_number(pdet.get("listPricePerTicket") or pdet.get("listPrice")),
            "shipping_type": data.get("shippingType") or data.get("shippingMethod"), 
            "shipping_amount": to_number(pdet.get("shipping")),
            "total_amount": to_number(pdet.get("total")), 
            "total_value": to_number(pdet.get("total")),
            "currency": data.get("currency"), 
            "delivery_status": data.get("shippingStatus"),
            "pod_status": "Sent" if data.get("podSubmitted") else "Pending", 
            "broker_name": data.get("brokerName"),
            "source_url": source_url, 
            "details_fetched_at": datetime.utcnow(), 
            "raw_payload": {"json": data}
        }

    def _parse_ltg_details_html(self, html, order_id, source_url):
        soup = BeautifulSoup(html, "html.parser")
        
        # Verify if layout changed significantly
        if not soup.find(string=re.compile("order", re.I)):
            raise PlatformLayoutError(f"Order details page for {order_id} has invalid structure or failed to render.")
            
        def find_val(labels):
            for l in labels:
                el = soup.find(string=re.compile(r'^' + l + r'$', re.I)) or soup.find(string=re.compile(l, re.I))
                if el:
                    p = el.parent
                    while p and not p.find_next_sibling(): 
                        p = p.parent
                    if p: 
                        nxt = p.find_next()
                        if nxt: 
                            return clean_text(nxt.get_text())
            return None
            
        def extract_by_label(label):
            target = soup.find(string=re.compile(label, re.I))
            if target:
                sib = target.find_next()
                if sib: 
                    return clean_text(sib.get_text())
            return None
            
        lp = extract_by_label("List Price per ticket")
        qty = extract_by_label("Qty.")
        ship = extract_by_label("Shipping")
        tot = extract_by_label("Total Amount")
        fname = extract_by_label("Full name")
        mob = extract_by_label("Mobile")
        curr = "£"
        if tot:
            if "€" in tot: 
                curr = "€"
            elif "$" in tot: 
                curr = "$"
        return {
            "order_number": str(order_id), 
            "event_name": find_val(["Event", "Show"]), 
            "event_date": parse_event_datetime(find_val(["Date"])),
            "customer_name": fname or find_val(["Customer", "Buyer"]), 
            "billing_full_name": fname,
            "mobile_number": mob or find_val(["Mobile", "Phone"]), 
            "billing_mobile": mob,
            "sale_date": parse_sale_datetime(find_val(["Created", "Sale Date"])), 
            "raw_status": find_val(["Status"]),
            "quantity": to_number(qty) or 1, 
            "list_price_per_ticket": to_number(lp),
            "shipping_type": ship.split("(")[0].strip() if ship else None, 
            "shipping_amount": to_number(ship),
            "total_amount": to_number(tot), 
            "total_value": to_number(tot), 
            "currency": curr,
            "pod_status": "Pending", 
            "details_fetched_at": datetime.utcnow(), 
            "source_url": source_url, 
            "raw_payload": {"html_parsing": True}
        }

    # =========================================================
    # CUSTOMER EXTRACTION HELPERS FOR GET_CUSTOMERS()
    # =========================================================

    def _extract_customer_from_details(self, details):
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

    def _get_all_historical_order_ids(self):
        logger.info("Scanning page 1 for historical orders...")
        url = "https://my.liveticketgroup.com/pages/content/orders.aspx?topnav=1&subnav=26"
        try:
            html = self.ensure_logged_in(url)
        except PlatformLoginError as le:
            raise le
            
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
        
        try:
            r = self.session.post(url, data=data, timeout=30)
            html = r.text
        except Exception as e:
            raise PlatformTimeoutError(f"Failed to post historical search query: {e}")
            
        order_ids = []
        rows, _ = self.parse_orders_from_html(html)
        logger.info(f"Found {len(rows)} orders on page 1.")
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
            
            logger.info(f"Scanning page {next_page}...")
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
                r_page = self.session.post(url, data=page_data, timeout=30)
                html = r_page.text
                page_rows, _ = self.parse_orders_from_html(html)
                logger.info(f"Found {len(page_rows)} orders on page {next_page}.")
                for row in page_rows:
                    if row.get("id"):
                        order_ids.append(row["id"])
                        
                new_matches = re.findall(r"__doPostBack\('([^']+)','(Page\$(\d+))'\)", html)
                for _, m_arg, m_page in new_matches:
                    p_num = int(m_page)
                    if p_num not in visited_pages:
                        pages_to_visit.add(p_num)
            except Exception as e:
                logger.error(f"Error fetching historical page {next_page}: {e}")
                
        unique_order_ids = []
        seen = set()
        for o in order_ids:
            if o not in seen:
                seen.add(o)
                unique_order_ids.append(o)
                
        return unique_order_ids

def get_ltg_adapter():
    for item in context.platform_adapters:
        if getattr(item, "source_name", "") == "LiveTicketGroup": 
            return item
    return None
