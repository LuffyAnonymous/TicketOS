import time
from playwright.sync_api import sync_playwright

def check_ticketsshop_for_order(event_name, order_id):
    """
    Logs into ticketsshop.net and searches if the order_id is listed under the event_name
    specifically for the broker 'Live Football Tickets'.
    Returns True if listed, False if not, and None if an error occurred.
    """
    username = "arvin@gmail.com"
    password = "AHSseoi38d"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            # 1. Login
            page.goto("https://ticketsshop.net/AppUserLogin")
            page.fill('input[type="email"]', username)
            page.fill('input[type="password"]', password)
            page.click('button:has-text("Sign In")')
            
            # Wait for any page to load after login
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)
            
            # 2. Go to Matches page
            page.goto("https://ticketsshop.net/matches")
            page.wait_for_selector('input[placeholder="Search matches..."]')
            
            # Split teams to make search more robust
            teams = event_name.split(' vs ')
            search_query = event_name
            if len(teams) == 2:
                search_query = f"{teams[0].strip()} vs {teams[1].strip()}"
                
            page.fill('input[placeholder="Search matches..."]', search_query)
            time.sleep(2) 
            
            # Click the match row.
            first_team = teams[0].strip() if len(teams) > 0 else event_name
            match_row = page.locator(f"div:has-text('{first_team}')").first
            if match_row.count() > 0:
                match_row.click()
            else:
                browser.close()
                return False 
                
            # Wait for Match Details page
            page.wait_for_selector('input[placeholder*="Search by account"]', timeout=15000)
            
            # 3. Search for the order ID
            page.fill('input[placeholder*="Search by account"]', str(order_id))
            time.sleep(2) # Give it time to filter the table
            
            # Verify if the order is present AND associated with Live Football Tickets
            page_text = page.locator("body").inner_text()
            
            is_listed = False
            if str(order_id) in page_text and "Live Football Tickets" in page_text:
                is_listed = True
                
            browser.close()
            return is_listed
            
    except Exception as e:
        print(f"Error checking ticketsshop: {e}")
        return None
