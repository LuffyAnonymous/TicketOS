import extensions as context
from platforms.base import OrderPlatformAdapter

class PlaceholderPlatformAdapter(OrderPlatformAdapter):
    def fetch_orders(self):
        context.state.log(f"{self.source_name}: adapter placeholder - not implemented yet")
        return [], None

