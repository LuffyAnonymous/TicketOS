import threading

state = None
platform_adapters = []
AUTO_CACHE_MANAGER = {"running": False, "lock": threading.Lock()}
