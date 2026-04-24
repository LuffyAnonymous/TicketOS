import json
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from config import BASE_DIR
from core.helpers import clean_text, parse_event_datetime
from platforms.base import OrderPlatformAdapter
import os

def parse_ftn_delivery_json(html: str):
    soup = BeautifulSoup(html, "html.parser")
    delivery_node = soup.select_one("#data-delivery")

    if not delivery_node:
        raise RuntimeError("FootballTicketNet: #data-delivery not found")

    raw = delivery_node.get("data-delivery", "").strip()
    if not raw:
        raise RuntimeError("FootballTicketNet: data-delivery is empty")

    try:
        items = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"FootballTicketNet: failed to parse delivery JSON: {e}")

    rows = []
    latest_order = None

    for item in items:
        order_id = str(item.get("order_id", "")).strip()
        if not order_id:
            continue

        qty = str(item.get("qty") or item.get("order_quantity") or "0").strip()
        ticket_price = str(item.get("ticket_price") or "0").strip()

        total_price = 0.0
        try:
            total_price = float(ticket_price) * float(qty or 0)
        except Exception:
            total_price = 0.0

        event_ts = str(item.get("event_date") or "").strip()
        event_date = "-"
        if event_ts.isdigit():
            try:
                event_date = datetime.fromtimestamp(int(event_ts)).strftime("%d-%m-%Y %H:%M:%S")
            except Exception:
                event_date = "-"

        delivery_status = clean_text(item.get("deliver_status") or "Unknown")
        purchase_status = clean_text(item.get("purchase_status") or "")

        row = {
            "id": order_id,
            "customer": clean_text(item.get("name") or "Unknown") or "Unknown",
            "status": delivery_status or purchase_status or "Unknown",
            "sale_date": "-",
            "event_date": event_date,
            "event": clean_text(item.get("event_name") or "-"),
            "source": "FootballTicketNet",
            "venue": clean_text(item.get("venue") or "-"),
            "league": clean_text(item.get("tournament") or "-"),
            "quantity": qty or "0",
            "price_per_ticket": ticket_price or "0",
            "total_price": f"{total_price:.2f}",
            "category": clean_text(item.get("category") or item.get("order_category") or "-"),
            "ticket_type": clean_text(item.get("ticket_type_name") or "-"),
            "phone": clean_text(item.get("contact_numbers") or ""),
            "comments": clean_text(item.get("comments") or ""),
            "delivery_status": delivery_status,
        }

        rows.append(row)
        latest_order = row

    rows.sort(
        key=lambda r: parse_event_datetime(r.get("event_date", "")) or datetime.min,
        reverse=False
    )

    if rows:
        latest_order = rows[0]

    return rows, latest_order


def fetch_ftn_delivery_html(username: str, password: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("https://www.footballticketnet.com/", wait_until="networkidle", timeout=60000)
        page.locator("a.login_btn.set2").click()
        page.wait_for_timeout(1000)

        try:
            page.locator("button.link_supplier").click()
            page.wait_for_timeout(500)
        except Exception:
            pass

        page.locator("#supplier_email").fill(username)
        page.locator("#supplier_password").click()
        page.locator("#supplier_password").fill(password)
        page.locator("#submit_supplier").click()
        page.wait_for_load_state("networkidle", timeout=60000)

        page.goto("https://www.footballticketnet.com/?action=delivery_info", wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()
        return html


class FootballTicketNetAdapter(OrderPlatformAdapter):
    def __init__(self, config):
        super().__init__("FootballTicketNet", config)

    def fetch_orders(self):
        username = self.config.get("username", "").strip()
        password = self.config.get("password", "").strip()

        if not username or not password:
            raise RuntimeError("FootballTicketNet: username/password not configured")

        context.state.log("FootballTicketNet: opening seller login")
        html = fetch_ftn_delivery_html(username, password)
        context.state.log("FootballTicketNet: parsing delivery JSON")
        rows, latest_order = parse_ftn_delivery_json(html)
        context.state.log(f"FootballTicketNet: parsed {len(rows)} order rows")
        return rows, latest_order


