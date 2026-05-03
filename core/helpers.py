import re
from datetime import datetime

def clean_text(text):
    text = str(text or "").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()

def standardize_status(raw_status, source=None, resale_status=None):
    """
    Map raw platform status string to an internal status for dashboard cards.

    Rules for LiveTicketGroup:
    - 'cancelled' → cancelled
    - 'resale' or 'resold' (in status or resale_status) → resold
    - 'processed', 'submitted', 'complete', 'completed' → pending (while visible)
    - everything else → pending

    'completed' internal status is ONLY for orders that were previously tracked but later disappeared.
    """
    if not raw_status:
        return "pending"
    
    status_low = clean_text(str(raw_status)).lower()
    resale_low = clean_text(str(resale_status or "")).lower()

    # 1. Cancelled check
    if "cancel" in status_low:
        return "cancelled"
    
    # 2. Resold check (includes resale_status)
    if "resol" in status_low or "resale" in status_low or "resold" in status_low:
        return "resold"
    if "resol" in resale_low or "resale" in resale_low:
        return "resold"

    # 3. LTG specific pending logic (Processed/Submitted/Complete → Pending while visible)
    # Note: We return 'pending' here. The 'completed' status is managed by disappearance logic.
    return "pending"

def parse_event_datetime(value):
    if not value:
        return None

    text = clean_text(str(value))
    candidates = [text, text.replace(",", "")]
    formats = [
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%a %d %b %Y %I:%M%p",
        "%A %d %B %Y %I:%M%p",
        "%a %d %B %Y %I:%M%p",
        "%A %d %b %Y %I:%M%p",
        "%a %d %b %Y %H:%M",
        "%A %d %B %Y %H:%M",
        "%d %b %Y %H:%M",
        "%d %B %Y %H:%M",
    ]

    for candidate in candidates:
        candidate = re.sub(r'(\d{1,2})(st|nd|rd|th)', r'\1', candidate)
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt)
            except Exception:
                pass
    return None


def parse_sale_datetime(value):
    if not value:
        return None
    text = clean_text(str(value))
    for fmt in ("%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            pass
    return None


def is_event_expired(event_date_text):
    dt = parse_event_datetime(event_date_text)
    if dt is None:
        return False
    return datetime.now() >= dt


def to_number(value):
    if value is None:
        return 0.0
    text = str(value).replace("£", "").replace(",", "").strip()
    try:
        return float(text)
    except Exception:
        return 0.0


def to_int(value):
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return 0
