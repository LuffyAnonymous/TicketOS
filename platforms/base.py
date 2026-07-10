from abc import ABC, abstractmethod

class PlatformAdapter(ABC):
    """
    Standard interface for all TicketOS platform connectors.
    Each ticket platform adapter should implement these 5 key methods.
    """
    def __init__(self, source_name, config):
        self.source_name = source_name
        self.config = config

    def login(self):
        """
        Authenticate with the ticket selling platform.
        """
        raise NotImplementedError(f"login() is not implemented for platform {self.source_name}")

    def get_orders(self):
        """
        Retrieve recent/active orders from the platform.
        Returns:
            list: List of dictionaries containing order data.
        """
        raise NotImplementedError(f"get_orders() is not implemented for platform {self.source_name}")

    def get_customers(self):
        """
        Retrieve customer history or client list from the platform.
        Returns:
            list: List of dictionaries containing customer records.
        """
        raise NotImplementedError(f"get_customers() is not implemented for platform {self.source_name}")

    def get_order_details(self, order_id):
        """
        Fetch details for a specific order by ID.
        Parameters:
            order_id (str): The target order number.
        Returns:
            dict: Detailed order attributes mapped to database columns.
        """
        raise NotImplementedError(f"get_order_details() is not implemented for platform {self.source_name}")

    def save_orders(self, orders):
        """
        Synchronize order records into the local database.
        Default implementation uses order_service / database helpers.
        """
        # Default pass-through, can be overridden by subclasses if custom saving is needed.
        pass

class OrderPlatformAdapter(PlatformAdapter):
    """
    Legacy wrapper to keep current scrapers running during incremental refactoring.
    All existing scrapers inherit from this.
    """
    @abstractmethod
    def fetch_orders(self):
        pass

    @abstractmethod
    def fetch_orders_by_event(self, event_name):
        pass
