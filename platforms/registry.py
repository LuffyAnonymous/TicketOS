from config import PLATFORM_CONFIGS
from platforms.liveticketgroup import LiveTicketGroupAdapter
from platforms.footballticketnet import FootballTicketNetAdapter
from platforms.placeholder import PlaceholderPlatformAdapter

def build_platform_adapters():
    adapters = []

    for source_name, config in PLATFORM_CONFIGS.items():
        if not config.get("enabled", False):
            continue

        if source_name == "LiveTicketGroup":
            adapters.append(LiveTicketGroupAdapter(config))
        elif source_name == "FootballTicketNet":
            adapters.append(FootballTicketNetAdapter(config))
        else:
            adapters.append(PlaceholderPlatformAdapter(source_name, config))

    return adapters


platform_adapters = build_platform_adapters()
