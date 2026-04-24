from abc import ABC, abstractmethod

class OrderPlatformAdapter(ABC):
    def __init__(self, source_name, config):
        self.source_name = source_name
        self.config = config

    @abstractmethod
    def fetch_orders(self):
        pass

