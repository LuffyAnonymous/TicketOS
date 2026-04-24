import os
import re
import json
from datetime import datetime
from curl_cffi import requests
from bs4 import BeautifulSoup
import extensions as context
from config import ORDER_STATE_FILE, DEBUG_LOGIN_HTML, DEBUG_CHUNK_JS, DEBUG_ORDERS_HTML, DEBUG_ORDER_DETAILS_HTML, LOGIN_STATE_TREE_ENCODED
from core.storage import load_json_file, save_json_file
from core.helpers import clean_text, parse_sale_datetime, is_event_expired
from platforms.base import OrderPlatformAdapter

class LiveTicketGroupAdapter(OrderPlatformAdapter):
    def __init__(self, config):
        super().__init__("LiveTicketGroup", config)
        self.session = requests.Session()
        self.next_action = None
        self.restore_session()

    def restore_session(self):
        data = load_json_file(ORDER_STATE_FILE, {})
        source_state = data.get(self.source_name, {})
        self.next_action = source_state.get("next_action")
        cookies = source_state.get("cookies", {})

        for name, value in cookies.items():
            try:
                self.session.cookies.set(name, value)
            except Exception:
                pass

    def persist_session(self):
        data = load_json_file(ORDER_STATE_FILE, {})
        cookies_dict = {}

        for c in self.session.cookies:
            try:
                cookies_dict[c.name] = c.value
            except Exception:
                pass

        data[self.source_name] = {
            "cookies": cookies_dict,
            "next_action": self.next_action,
        }
        save_json_file(ORDER_STATE_FILE, data)

    def looks_authenticated_response(self, response):
        url = str(response.url).lower()
        text = response.text.lower()

        if "my.liveticketgroup.com" in url:
            if 'name="email"' in text and 'name="password"' in text:
                return False
            return True

        if "liveticketgroup.com/login" in url:
            return False

        return False

    def get_login_page(self):
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-GB,en;q=0.9",
            "priority": "u=0, i",
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        }
        context.state.log(f"{self.source_name}: opening login page")
        r = self.session.get(self.config["login_url"], headers=headers, timeout=30)
        r.raise_for_status()
        return r

    def fetch_next_action(self):
        headers = {
            "sec-ch-ua-platform": '"Windows"',
            "Referer": self.config["login_url"],
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
        }

        context.state.log(f"{self.source_name}: opening login page for dynamic chunk discovery")
        login_page = self.session.get(self.config["login_url"], headers=headers, timeout=30)
        login_page.raise_for_status()

        html = login_page.text
        with open(DEBUG_LOGIN_HTML, "w", encoding="utf-8") as f:
            f.write(html)

        chunk_candidates = re.findall(r'(/_next/static/chunks/[^"\']+?\.js)', html)
        if not chunk_candidates:
            raise RuntimeError(f"{self.source_name}: could not find any Next.js chunk in login page")

        next_action = None
        chosen_chunk_url = None

        for chunk_path in chunk_candidates:
            chunk_url = "https://www.liveticketgroup.com" + chunk_path
            try:
                context.state.log(f"{self.source_name}: checking chunk -> {chunk_url}")
                js_resp = self.session.get(chunk_url, headers=headers, timeout=30)
                js_resp.raise_for_status()

                match = re.search(r'createServerReference\)\("(.*?)"', js_resp.text)
                if match:
                    next_action = match.group(1)
                    chosen_chunk_url = chunk_url

                    with open(DEBUG_CHUNK_JS, "w", encoding="utf-8") as f:
                        f.write(js_resp.text)
                    break
            except Exception:
                continue

        if not next_action:
            raise RuntimeError(
                f"{self.source_name}: could not extract next-action from discovered chunks. "
                f"Check {os.path.basename(DEBUG_LOGIN_HTML)}"
            )

        self.next_action = next_action
        self.persist_session()
        context.state.log(f"{self.source_name}: dynamic next-action extracted from {chosen_chunk_url}")

    def login(self):
        username = self.config.get("username", "").strip()
        password = self.config.get("password", "").strip()

        if not username or not password:
            raise RuntimeError(f"{self.source_name}: username/password not configured")

        self.get_login_page()
        self.fetch_next_action()

        headers = {
            "accept": "text/x-component",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "text/plain;charset=UTF-8",
            "next-action": self.next_action,
            "next-router-state-tree": LOGIN_STATE_TREE_ENCODED,
            "origin": "https://www.liveticketgroup.com",
            "priority": "u=1, i",
            "referer": self.config["login_url"],
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        }

        payload = json.dumps([{"email": username, "password": password}])

        context.state.log(f"{self.source_name}: sending login request")
        response = self.session.post(
            self.config["login_url"],
            headers=headers,
            data=payload,
            timeout=30,
        )
        response.raise_for_status()

        with open(DEBUG_LOGIN_HTML, "w", encoding="utf-8") as f:
            f.write(response.text)

        redirect_match = re.search(r'"NEXT_REDIRECT;replace;(.*?);', response.text)
        if not redirect_match:
            raise RuntimeError(
                f"{self.source_name}: login redirect not found. "
                f"Check {os.path.basename(DEBUG_LOGIN_HTML)}"
            )

        redirect_url = redirect_match.group(1)
        context.state.log(f"{self.source_name}: redirect found -> {redirect_url}")

        follow = self.session.get(
            redirect_url,
            headers={
                "User-Agent": headers["user-agent"],
                "Referer": self.config["login_url"],
            },
            allow_redirects=True,
            timeout=30,
        )
        follow.raise_for_status()

        self.persist_session()
        context.state.log(f"{self.source_name}: login successful")

    def get_orders_page(self):
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-GB,en;q=0.9",
            "priority": "u=0, i",
            "referer": "https://my.liveticketgroup.com/pages/content/index.aspx?TopNav=1&SubNav=4",
            "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        }

        params = {
            "TopNav": "1",
            "SubNav": "4",
            "urgent": "672",
        }

        context.state.log(f"{self.source_name}: loading urgent orders page")
        r = self.session.get(
            self.config["orders_base_url"],
            params=params,
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        self.persist_session()
        return r

    def ensure_logged_in(self):
        try:
            response = self.get_orders_page()
            if self.looks_authenticated_response(response):
                context.state.session_status = "✅ Active"
                context.state.log(f"{self.source_name}: existing session still active")
                return response.text

            context.state.log(f"{self.source_name}: existing session not authenticated")
        except Exception as e:
            context.state.log(f"{self.source_name}: session check failed: {repr(e)}")

        context.state.session_status = "⚠ Re-logging"
        self.login()

        response = self.get_orders_page()
        if not self.looks_authenticated_response(response):
            with open(DEBUG_ORDERS_HTML, "w", encoding="utf-8") as f:
                f.write(response.text)
            raise RuntimeError(
                f"{self.source_name}: still unauthenticated after login. "
                f"Check {os.path.basename(DEBUG_ORDERS_HTML)}"
            )

        context.state.session_status = "✅ Active"
        return response.text

    def find_orders_table(self, soup):
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue

            first_row = rows[0]
            headers = [clean_text(x.get_text(" ", strip=True)).lower() for x in first_row.find_all(["th", "td"])]
            if not headers:
                continue

            joined = " | ".join(headers)
            if all(k in joined for k in ["id", "status", "sale", "event"]):
                return table, headers

        return None, []

    def parse_orders_from_html(self, html):
        soup = BeautifulSoup(html, "html.parser")
        table, headers = self.find_orders_table(soup)

        if table is None:
            with open(DEBUG_ORDERS_HTML, "w", encoding="utf-8") as f:
                f.write(html)
            raise RuntimeError(f"{self.source_name}: orders table not found")

        column_map = {}
        for i, header in enumerate(headers):
            h = header.lower()
            if h == "id":
                column_map["id"] = i
            elif h == "status":
                column_map["status"] = i
            elif "sale date" in h:
                column_map["sale_date"] = i
            elif "event date" in h:
                column_map["event_date"] = i
            elif h == "event" or "event" in h:
                column_map["event"] = i
            elif "customer" in h or "name" in h or "client" in h or "buyer" in h:
                column_map["customer"] = i

        required = ["id", "status", "sale_date", "event_date", "event", "customer"]
        missing = [x for x in required if x not in column_map]
        if missing:
            raise RuntimeError(f"{self.source_name}: missing columns -> {', '.join(missing)}")

        rows = []
        latest_order = None
        latest_dt = None

        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if not tds:
                continue

            try:
                row_data = {
                    "id": clean_text(tds[column_map["id"]].get_text(" ", strip=True)),
                    "customer": clean_text(tds[column_map["customer"]].get_text(" ", strip=True)),
                    "status": clean_text(tds[column_map["status"]].get_text(" ", strip=True)),
                    "sale_date": clean_text(tds[column_map["sale_date"]].get_text(" ", strip=True)),
                    "event_date": clean_text(tds[column_map["event_date"]].get_text(" ", strip=True)),
                    "event": clean_text(tds[column_map["event"]].get_text(" ", strip=True)),
                    "source": self.source_name,
                }
            except Exception:
                continue

            if not row_data["id"]:
                continue

            if not is_event_expired(row_data["event_date"]):
                rows.append(row_data)

            sale_dt = parse_sale_datetime(row_data["sale_date"])
            if sale_dt is not None and (latest_dt is None or sale_dt > latest_dt):
                latest_dt = sale_dt
                latest_order = row_data

        if latest_order is None and rows:
            latest_order = rows[0]

        return rows, latest_order

    def fetch_orders(self):
        html = self.ensure_logged_in()
        return self.parse_orders_from_html(html)


def get_ltg_adapter():
    for item in context.platform_adapters:
        if getattr(item, "source_name", "") == "LiveTicketGroup":
            return item
    return None


def parse_ltg_order_details_html(html):
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text("\n", strip=True)

    def txt(node):
        try:
            return clean_text(node.get_text(" ", strip=True)) if node else "-"
        except Exception:
            return "-"

    def norm(value):
        return clean_text(value).lower().replace(":", "").strip()

    def clean_shipping(value):
        value = clean_text(value)
        value = re.sub(r"\s*\(\s*[£$]\s*[0-9.,]+\s*\)", "", value).strip()
        return value or "-"

    def find_event():
        try:
            el = soup.select_one("p.MuiTypography-subtitle1")
            if el:
                v = txt(el)
                if " vs " in v.lower():
                    return v
        except Exception:
            pass

        m = re.search(r'([A-Za-z0-9 &\'\-.]+ vs [A-Za-z0-9 &\'\-.]+)', page_text, re.IGNORECASE)
        if m:
            return clean_text(m.group(1))

        return "-"

    def find_league():
        patterns = [
            r'English Premier League',
            r'Premier League',
            r'Champions League',
            r'Europa League',
            r'FA Cup',
            r'Carabao Cup',
            r'La Liga',
            r'Bundesliga',
            r'Serie A',
            r'Ligue 1',
        ]
        for p in patterns:
            m = re.search(p, page_text, re.IGNORECASE)
            if m:
                return clean_text(m.group(0))
        return "-"

    def find_venue():
        lines = [clean_text(x) for x in page_text.splitlines() if clean_text(x)]
        for line in lines:
            if "|" in line:
                lower = line.lower()
                if any(k in lower for k in [
                    "liverpool", "manchester", "london", "united kingdom",
                    "stadium", "road", "park", "bridge", "anfield", "old trafford"
                ]):
                    return line
        return "-"

    def find_event_date():
        lines = [clean_text(x) for x in page_text.splitlines() if clean_text(x)]
        for line in lines:
            if re.search(r'\b\d{1,2}(st|nd|rd|th)\s+[A-Za-z]{3,9}\s+\d{4}\s+\d{1,2}:\d{2}\b', line, re.IGNORECASE):
                return line
        return "-"

    def extract_pairs():
        pairs = {}

        try:
            for block in soup.find_all(["div", "section"]):
                children = block.find_all(["p", "span"], recursive=False)
                texts = [txt(c) for c in children if txt(c) != "-"]
                if len(texts) == 2:
                    label = norm(texts[0])
                    value = texts[1]
                    if label and value and len(label) < 50:
                        pairs[label] = value
        except Exception:
            pass

        try:
            ps = soup.find_all("p")
            for i in range(len(ps) - 1):
                label = norm(txt(ps[i]))
                value = txt(ps[i + 1])
                if label and value and len(label) < 50 and label not in pairs:
                    pairs[label] = value
        except Exception:
            pass

        return pairs

    def find_attendees():
        attendees = []
        try:
            match = re.search(r'Attendees(.*?)(Restrictions|Listing Notes|Order Summary|$)', page_text, re.DOTALL | re.IGNORECASE)
            if match:
                chunk = match.group(1)
                for line in chunk.splitlines():
                    line = clean_text(line)
                    if not line or line.lower() == "attendees":
                        continue
                    if len(line.split()) >= 2 and line not in attendees:
                        attendees.append(line)
        except Exception:
            pass
        return attendees

    pairs = extract_pairs()

    category = pairs.get("category", "-")
    section = pairs.get("section", "-")
    row_value = pairs.get("row", "-")
    seating = pairs.get("seating arr", pairs.get("seating", "-"))
    allocation = pairs.get("allocation", "-")
    shipping = clean_shipping(pairs.get("shipping", pairs.get("delivery", "-")))
    quantity = pairs.get("qty", pairs.get("quantity", pairs.get("qty.", "-")))
    restrictions = pairs.get("restrictions", "-")
    listing_notes = pairs.get("listing notes", pairs.get("notes", "-"))
    customer_name = pairs.get("full name", pairs.get("customer name", "-"))
    customer_phone = pairs.get("mobile", pairs.get("phone", "-"))
    price_per_ticket = pairs.get("list price per ticket", pairs.get("price per ticket", "-"))
    total_amount = pairs.get("total amount", pairs.get("total price", "-"))

    if category == "-":
        m = re.search(r'ANFIELD ROAD UPPER|ANFIELD ROAD LOWER|MAIN STAND|SIR KENNY DALGLISH STAND|KOP', page_text, re.IGNORECASE)
        if m:
            category = clean_text(m.group(0))

    event = find_event()
    league = find_league()
    venue = find_venue()
    event_date = find_event_date()

    line_items = []
    if any(v != "-" for v in [category, section, row_value, seating, allocation, shipping, quantity]):
        line_items.append([
            category,
            section,
            row_value,
            seating,
            allocation,
            shipping,
            quantity
        ])

    return {
        "event": event,
        "league": league,
        "venue": venue,
        "event_date": event_date,
        "status": pairs.get("status", "-"),
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "area": category if category != "-" else section,
        "category": category,
        "section": section,
        "row": row_value,
        "seating": seating,
        "allocation": allocation,
        "delivery": shipping,
        "shipping": shipping,
        "quantity": quantity,
        "ticket_type": allocation if allocation != "-" else category,
        "price": price_per_ticket.replace("£", "").strip() if price_per_ticket != "-" else "-",
        "price_per_ticket": price_per_ticket,
        "total_price": total_amount,
        "restrictions": restrictions,
        "notes": listing_notes,
        "sale_date": pairs.get("sale date", "-"),
        "processed_on": pairs.get("processed on", "-"),
        "attendees": find_attendees(),
        "line_items": line_items,
    }

def get_ltg_order_details(order_id):
    adapter = get_ltg_adapter()
    if adapter is None:
        raise RuntimeError("LiveTicketGroup adapter is not enabled")

    adapter.ensure_logged_in()

    detail_url = (
        "https://my.liveticketgroup.com/Pages/Content/RefreshTokenRedirect.aspx"
        f"?portalapiurl=https://www.liveticketgroup.com/orders/{order_id}"
    )

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://my.liveticketgroup.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }

    r = adapter.session.get(detail_url, headers=headers, timeout=30, allow_redirects=True)
    r.raise_for_status()

    html = r.text

    with open(DEBUG_ORDER_DETAILS_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    if not html or len(html.strip()) < 100:
        raise RuntimeError("Order details page returned empty or too short HTML")

    parsed = parse_ltg_order_details_html(html)
    parsed["detail_url"] = detail_url

    if not isinstance(parsed, dict):
        raise RuntimeError("Parsed order details is not a dictionary")

    return parsed
