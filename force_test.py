from services.inventory_service import check_ticketsshop_for_order
from services.telegram_service import send_telegram

import extensions as context

class MockState:
    def log(self, msg):
        print(f"App Log: {msg}")

context.state = MockState()

if __name__ == "__main__":
    print("Forcing a real Telegram alert test...")
    
    # 1. We mock the order data just like it came from LiveTicketGroup
    mock_order = {
        "id": "1818472", # The order you removed
        "event": "Liverpool vs Palace",
        "source": "LiveTicketGroup"
    }
    
    print(f"Logging into TicketsShop to check order {mock_order['id']}...")
    is_listed = check_ticketsshop_for_order(mock_order["event"], mock_order["id"])
    
    if is_listed is False:
        print("❌ Not listed! Sending the missing inventory Telegram alert NOW...")
        msg = (
            f"⚠️ *Missing Inventory Alert* ⚠️\n\n"
            f"The order `{mock_order['id']}` from LiveTicketGroup "
            f"({mock_order['event']}) is **NOT** listed in the TicketsShop system! "
            f"Please add it."
        )
        send_telegram(msg)
        print("✅ Telegram alert sent successfully! Check your phone.")
        
    elif is_listed is True:
        print("✅ Listed! No missing alert needed.")
    else:
        print("⚠️ Error occurred during the browser check.")
