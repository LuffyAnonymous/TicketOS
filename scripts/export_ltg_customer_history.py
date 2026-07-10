import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add root folder to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extensions as context
from core.state import AppState
from platforms.registry import build_platform_adapters
from platforms.liveticketgroup import get_ltg_adapter
from services.excel_exporter import export_customer_history

def main():
    try:
        context.state = AppState()
        context.platform_adapters = build_platform_adapters()
        adapter = get_ltg_adapter()
        if not adapter:
            print("Error: LiveTicketGroup adapter not found.")
            return
            
        print("Fetching LiveTicketGroup customer history...")
        customers = adapter.get_customers()
        print(f"Extracted {len(customers)} customer records.")
        
        export_customer_history(customers)
        print("Export finished.")
    except Exception as e:
        print(f"Error exporting LiveTicketGroup customer history: {e}")

if __name__ == "__main__":
    main()
