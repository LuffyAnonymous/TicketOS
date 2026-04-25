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
            
            import os
            state_file = "ticketsshop_state.json"
            
            # Load session if it exists to avoid repeated logins
            if os.path.exists(state_file):
                context = browser.new_context(storage_state=state_file)
            else:
                context = browser.new_context()
                
            page = context.new_page()
            
            # Try going directly to the Matches page
            page.goto("https://ticketsshop.net/matches")
            page.wait_for_load_state("networkidle", timeout=15000)
            
            # If we were redirected to the login page, the session is expired or missing
            if "AppUserLogin" in page.url:
                page.fill('input[type="email"]', username)
                page.fill('input[type="password"]', password)
                page.click('button:has-text("Sign In")')
                
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
                
                # Save the new session to disk so we don't have to log in next time
                context.storage_state(path=state_file)
                
                # Navigate to matches now that we are logged in
                page.goto("https://ticketsshop.net/matches")
                page.wait_for_load_state("networkidle", timeout=15000)
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

def check_ticketsshop_bulk(orders_to_check):
    """
    Takes a list of order dicts. Returns a dictionary with 'listed' and 'missing' lists.
    """
    listed = []
    missing = []
    username = "arvin@gmail.com"
    password = "AHSseoi38d"
    
    try:
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
                page.fill('input[type="email"]', username)
                page.fill('input[type="password"]', password)
                page.click('button:has-text("Sign In")')
                
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
                context.storage_state(path=state_file)
                
                page.goto("https://ticketsshop.net/matches")
                page.wait_for_load_state("networkidle", timeout=15000)
                
            for order in orders_to_check:
                event_name = order.get('event', '')
                order_id = str(order.get('id', ''))
                
                page.goto("https://ticketsshop.net/matches")
                page.wait_for_selector('input[placeholder="Search matches..."]', timeout=15000)
                
                teams = event_name.split(' vs ')
                first_team = teams[0].strip() if len(teams) > 0 else event_name
                second_team = teams[1].strip() if len(teams) > 1 else ""
                
                page.fill('input[placeholder="Search matches..."]', first_team)
                time.sleep(2) 
                
                match_cards = page.locator("div.cursor-pointer")
                match_to_click = None
                
                for i in range(match_cards.count()):
                    card = match_cards.nth(i)
                    card_text = card.inner_text()
                    if second_team and first_team in card_text and second_team in card_text:
                        match_to_click = card
                        break
                    elif not second_team and first_team in card_text:
                        match_to_click = card
                        break
                        
                if match_to_click is None and match_cards.count() > 0:
                    match_to_click = match_cards.first
                
                if match_to_click and match_to_click.count() > 0:
                    match_to_click.click()
                    page.wait_for_selector('input[placeholder*="Search by account"]', timeout=15000)
                    
                    page.fill('input[placeholder*="Search by account"]', order_id)
                    time.sleep(2)
                    
                    page_text = page.locator("body").inner_text()
                    
                    if order_id in page_text and "Live Football Tickets" in page_text:
                        listed.append(order)
                    else:
                        missing.append(order)
                else:
                    missing.append(order)
                    
            browser.close()
            return {"listed": listed, "missing": missing}
    except Exception as e:
        print(f"Error checking ticketsshop bulk: {e}")
        return {"listed": [], "missing": []}
