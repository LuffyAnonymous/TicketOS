from services.inventory_service import check_ticketsshop_for_order

if __name__ == "__main__":
    print("Testing TicketsShop Inventory Checker...")
    # Replace with the actual event name and order ID you want to test
    test_event = "Liverpool vs Palace"
    test_order_id = "1818472" # Change this to the order ID you removed!
    
    print(f"Checking if order {test_order_id} for event {test_event} is listed...")
    
    is_listed = check_ticketsshop_for_order(test_event, test_order_id)
    
    if is_listed is True:
        print(f"[SUCCESS] Result: Order IS listed under Live Football Tickets!")
    elif is_listed is False:
        print(f"[FAILED] Result: Order is NOT listed (this would trigger the Telegram warning).")
    else:
        print(f"[WARNING] Result: An error occurred during the check.")
