import os
import re
import json
from datetime import datetime, timedelta
from curl_cffi import requests
from bs4 import BeautifulSoup
import extensions as context
from config import ORDER_STATE_FILE, DEBUG_ORDER_DETAILS_HTML, LOGIN_STATE_TREE_ENCODED, DEBUG_ORDERS_HTML
from core.storage import load_json_file, save_json_file
from core.helpers import clean_text, parse_sale_datetime, to_number, parse_event_datetime
from platforms.base import OrderPlatformAdapter

class LiveTicketGroupAdapter(OrderPlatformAdapter):
    def __init__(self, config):
        super().__init__("LiveTicketGroup", config)
        self.session = requests.Session()
        self.next_action = None
        self.restore_session()

    def restore_session(self):
        data = load_json_file(ORDER_STATE_FILE, {}).get(self.source_name, {})
        self.next_action = data.get("next_action")
        for k, v in data.get("cookies", {}).items():
            try: self.session.cookies.set(k, v)
            except: pass

    def persist_session(self):
        data = load_json_file(ORDER_STATE_FILE, {})
        cookies = {}
        try:
            for c in self.session.cookies:
                if hasattr(c, 'name'): cookies[c.name] = c.value
                elif isinstance(c, str): cookies[c] = self.session.cookies.get(c)
        except: pass
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
                    if m: self.next_action = m.group(1); break
                except: continue
        except Exception as e: print(f"LTG next_action error: {e}")
        self.persist_session()

    def login(self):
        self.fetch_next_action()
        if not self.next_action: return
        payload = json.dumps([{"email": self.config["username"], "password": self.config["password"]}])
        r = self.session.post(self.config["login_url"], headers={"accept": "text/x-component", "content-type": "text/plain;charset=UTF-8", "next-action": self.next_action, "next-router-state-tree": LOGIN_STATE_TREE_ENCODED}, data=payload, timeout=30)
        m = re.search(r'"NEXT_REDIRECT;replace;(.*?);', r.text)
        if m: self.session.get(m.group(1), allow_redirects=True, timeout=30); self.persist_session()

    def ensure_logged_in(self, target_url=None):
        url = target_url or "https://my.liveticketgroup.com/pages/content/orders.aspx?topnav=1&subnav=26"
        try:
            r = self.session.get(url, timeout=30)
            if "Exception:" in r.text and "Refresh token" in r.text:
                raise Exception("LiveTicketGroup session expired. Please re-login.")
            if self.looks_authenticated_response(r): return r.text
        except Exception as e:
            if "session expired" in str(e): raise e
        
        self.login()
        r2 = self.session.get(url, timeout=30)
        if "Exception:" in r2.text and "Refresh token" in r2.text:
            raise Exception("LiveTicketGroup session expired. Please re-login.")
        return r2.text

    def parse_orders_from_html(self, html):
        if not html: return [], None
        with open(DEBUG_ORDERS_HTML, "w", encoding="utf-8") as f: f.write(html)
        soup = BeautifulSoup(html, "html.parser")
        table = None
        for t in soup.find_all("table"):
            h = [x.get_text().lower() for x in t.find_all(["th", "td"])[:30]]
            if any("id" in x for x in h) and (any("status" in x for x in h) or any("event" in x for x in h)):
                table = t; break
        if not table: return [], None
        rows = []
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) < 5: continue
            headers = [clean_text(th.get_text()).lower() for th in table.find_all("tr")[0].find_all(["th", "td"])]
            id_idx = next((i for i, h in enumerate(headers) if h == "id"), 0)
            
            if len(tds) <= id_idx: continue
            oid_txt = clean_text(tds[id_idx].get_text())
            if not oid_txt.isdigit(): continue
            
            def get_val(lbls):
                for l in lbls:
                    for i, h in enumerate(headers):
                        if h == l:
                            if i < len(tds): return clean_text(tds[i].get_text())
                for l in lbls:
                    for i, h in enumerate(headers):
                        if l in h:
                            if i < len(tds): return clean_text(tds[i].get_text())
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
                "currency": "£", "source": self.source_name
            })
        return rows, rows[0] if rows else None

    def fetch_orders(self):
        # Go to urgent orders page (Dashboard)
        url = "https://my.liveticketgroup.com/pages/content/index.aspx?topnav=1&subnav=4"
        html = self.ensure_logged_in(url)
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
                if rows: return rows, rows[0]
            except: pass
        
        # Fallback to general parsing
        return self.parse_orders_from_html(html)

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
        r_post = self.session.post("https://my.liveticketgroup.com/pages/content/orders.aspx?topnav=1&subnav=26", data=data, timeout=30)
        rows, _ = self.parse_orders_from_html(r_post.text)
        return rows

    def fetch_order_details(self, order_id):
        self.ensure_logged_in()
        # Bypass legacy RefreshTokenRedirect and hit the Next.js orders page directly
        url = f"https://www.liveticketgroup.com/orders/{order_id}"
        r = self.session.get(url, timeout=30, allow_redirects=True)
        html = r.text
        
        # Check if Next.js session expired and redirected to login
        if "name=\"email\"" in html.lower() or "login" in r.url.lower() or "Exception:" in html:
            self.login()
            r = self.session.get(url, timeout=30, allow_redirects=True)
            html = r.text
            if "name=\"email\"" in html.lower() or "login" in r.url.lower() or "Exception:" in html:
                raise Exception("LiveTicketGroup session expired. Please re-login.")
        
        # Unescape Next.js JSON state
        html_clean = html.replace('\\"', '"').replace('\\\\', '\\')
        
        try:
            m = re.search(r'"data":(\{"id":' + str(order_id) + r'.*?"problematicOrderNotes":\[.*?\]\})', html_clean)
            if m: return self._map_ltg_json_to_db(json.loads(m.group(1)), html, url)
            
            # Fallback regex in case structure slightly differs
            m2 = re.search(r'(\{"id":' + str(order_id) + r',.*?"problematicOrderNotes":\[.*?\]\})', html)
            if m2: return self._map_ltg_json_to_db(json.loads(m2.group(1)), html, url)
        except: pass
        return self._parse_ltg_details_html(html, order_id, url)

    def _map_ltg_json_to_db(self, data, html, source_url):
        if not isinstance(data, dict): return {}
        buyer = data.get("buyer") or {}; tinfo = data.get("ticketInfo") or {}; pdet = tinfo.get("pricingDetails") or {}; show = data.get("show") or {}
        seating_list = tinfo.get("seating", [])
        seat_names = [str(s.get("name", "")) if isinstance(s, dict) else str(s) for s in seating_list]
        return {
            "event_name": show.get("name") if isinstance(show, dict) else str(show), 
            "event_date": parse_event_datetime(show.get("showDate")) if isinstance(show, dict) else None,
            "customer_name": buyer.get("fullName"), "billing_full_name": buyer.get("fullName"),
            "mobile_number": buyer.get("shipping", {}).get("mobile") or buyer.get("billing", {}).get("mobile"),
            "billing_mobile": buyer.get("billing", {}).get("mobile"), "email": buyer.get("email"),
            "sale_date": parse_sale_datetime(data.get("createdOn")), "raw_status": data.get("status"), "resale_status": data.get("resaleStatus"),
            "category": tinfo.get("category"), "section": tinfo.get("section") or tinfo.get("category"),
            "row_name": tinfo.get("row"), "seat_number": ", ".join(seat_names),
            "quantity": tinfo.get("quantity"), "list_price_per_ticket": to_number(pdet.get("listPricePerTicket") or pdet.get("listPrice")),
            "shipping_type": data.get("shippingType") or data.get("shippingMethod"), "shipping_amount": to_number(pdet.get("shipping")),
            "total_amount": to_number(pdet.get("total")), "total_value": to_number(pdet.get("total")),
            "currency": data.get("currency"), "delivery_status": data.get("shippingStatus"),
            "pod_status": "Sent" if data.get("podSubmitted") else "Pending", "broker_name": data.get("brokerName"),
            "source_url": source_url, "details_fetched_at": datetime.utcnow(), "raw_payload": {"json": data}
        }

    def _parse_ltg_details_html(self, html, order_id, source_url):
        soup = BeautifulSoup(html, "html.parser")
        def find_val(labels):
            for l in labels:
                el = soup.find(string=re.compile(r'^' + l + r'$', re.I)) or soup.find(string=re.compile(l, re.I))
                if el:
                    p = el.parent
                    while p and not p.find_next_sibling(): p = p.parent
                    if p: 
                        nxt = p.find_next()
                        if nxt: return clean_text(nxt.get_text())
            return None
        def extract_by_label(label):
            target = soup.find(string=re.compile(label, re.I))
            if target:
                sib = target.find_next()
                if sib: return clean_text(sib.get_text())
            return None
        lp = extract_by_label("List Price per ticket"); qty = extract_by_label("Qty."); ship = extract_by_label("Shipping"); tot = extract_by_label("Total Amount")
        fname = extract_by_label("Full name"); mob = extract_by_label("Mobile")
        curr = "£"
        if tot:
            if "€" in tot: curr = "€"
            elif "$" in tot: curr = "$"
        return {
            "order_number": str(order_id), "event_name": find_val(["Event", "Show"]), "event_date": parse_event_datetime(find_val(["Date"])),
            "customer_name": fname or find_val(["Customer", "Buyer"]), "billing_full_name": fname,
            "mobile_number": mob or find_val(["Mobile", "Phone"]), "billing_mobile": mob,
            "sale_date": parse_sale_datetime(find_val(["Created", "Sale Date"])), "raw_status": find_val(["Status"]),
            "quantity": to_number(qty) or 1, "list_price_per_ticket": to_number(lp),
            "shipping_type": ship.split("(")[0].strip() if ship else None, "shipping_amount": to_number(ship),
            "total_amount": to_number(tot), "total_value": to_number(tot), "currency": curr,
            "pod_status": "Pending", "details_fetched_at": datetime.utcnow(), "source_url": source_url, "raw_payload": {"html_parsing": True}
        }

def get_ltg_adapter():
    for item in context.platform_adapters:
        if getattr(item, "source_name", "") == "LiveTicketGroup": return item
    return None
