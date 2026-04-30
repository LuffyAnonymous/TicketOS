import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import extensions as context
from core.helpers import clean_text
from platforms.base import OrderPlatformAdapter

class FanpassAdapter(OrderPlatformAdapter):
    def __init__(self, config):
        super().__init__("Fanpass", config)

    def fetch_orders(self):
        username = self.config.get("username", "").strip()
        password = self.config.get("password", "").strip()
        login_url = self.config.get("login_url", "https://seller.fanpass.co.uk/login")
        orders_url = self.config.get("orders_url", "https://seller.fanpass.co.uk/sales")

        if not username or not password:
            raise RuntimeError("Fanpass: username/password not configured")

        context.state.log("Fanpass: starting browser for check")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(login_url, wait_until="networkidle", timeout=60000)
                page.fill('input[name="email"]', username)
                page.fill('input[name="password"]', password)
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle", timeout=60000)
                
                page.goto(orders_url, wait_until="networkidle", timeout=60000)
                html = page.content()
                
                soup = BeautifulSoup(html, "html.parser")
                rows = []
                # Generic table parsing - likely needs adjustment for Fanpass specific DOM
                tables = soup.find_all("table")
                if tables:
                    for tr in tables[0].find_all("tr")[1:]:
                        tds = tr.find_all("td")
                        if len(tds) >= 4:
                            rows.append({
                                "id": clean_text(tds[0].get_text()),
                                "event": clean_text(tds[1].get_text()),
                                "status": clean_text(tds[2].get_text()),
                                "customer": clean_text(tds[3].get_text()),
                                "source": "Fanpass",
                                "resale_status": ""
                            })
                
                browser.close()
                return rows, rows[0] if rows else None
            except Exception as e:
                browser.close()
                raise RuntimeError(f"Fanpass scraping failed: {str(e)}")

    def fetch_orders_by_event(self, event_name):
        rows, _ = self.fetch_orders()
        ev_lower = clean_text(event_name).lower()
        return [r for r in rows if ev_lower in clean_text(r.get("event", "")).lower()]
