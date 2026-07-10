import threading

state = None
platform_adapters = []
scheduler = None
AUTO_CACHE_MANAGER = {"running": False, "lock": threading.Lock()}
