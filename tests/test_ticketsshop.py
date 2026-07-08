import time
from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        import os
        state_file = "ticketsshop_state.json"
        
        if os.path.exists(state_file):
            context = browser.new_context(storage_state=state_file)
        else:
            context = browser.new_context()
            
        page = context.new_page()
        page.goto("https://ticketsshop.net/matches")
        page.wait_for_load_state("networkidle", timeout=15000)
        
        if "AppUserLogin" in page.url:
            page.fill('input[type="email"]', "arvin@gmail.com")
            page.fill('input[type="password"]', "AHSseoi38d")
            page.click('button:has-text("Sign In")')
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)
            context.storage_state(path=state_file)
            page.goto("https://ticketsshop.net/matches")
            page.wait_for_load_state("networkidle", timeout=15000)
            
        page.wait_for_selector('input[placeholder="Search matches..."]', timeout=15000)
        
        # We will search "Manchester United Liverpool"
        page.fill('input[placeholder="Search matches..."]', "Manchester United")
        time.sleep(3)
        
        html = page.content()
        with open("matches_dom.html", "w") as f:
            f.write(html)
            
        print("DOM saved to matches_dom.html")
        browser.close()

if __name__ == "__main__":
    test()
