import re
from datetime import datetime

def clean_text(text):
    text = str(text or "").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()

def normalize_event_name(name):
    if not name or name.strip() in ("-", "None", ""): return None
    n = clean_text(name)
    n = n.replace(" vs ", " vs. ").replace(" vs. ", " vs ")
    return n

def standardize_status(raw_status, source=None, resale_status=None, pod_status=None):
    if not raw_status: return "pending"
    s = clean_text(str(raw_status)).lower()
    r = clean_text(str(resale_status or "")).lower()
    p = clean_text(str(pod_status or "")).lower()
    
    # Cancelled check
    if "cancel" in s: return "cancelled"
    
    # Resold check
    if any(x in s for x in ("resol", "resale", "resold")) or any(x in r for x in ("resol", "resale")): return "resold"
    
    # Completed check: ONLY if POD was actually sent/submitted
    if any(x in p for x in ("sent", "submit", "yes", "true", "pod")): return "completed"
    
    # Default: Processed/Submitted/Complete → Pending (unless POD sent)
    return "pending"

def parse_event_datetime(value):
    if not value: return None
    text = clean_text(str(value))
    candidates = [text, text.replace(",", "")]
    formats = ["%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%a %d %b %Y %I:%M%p", "%A %d %B %Y %I:%M%p", "%a %d %B %Y %I:%M%p", "%A %d %b %Y %I:%M%p", "%a %d %b %Y %H:%M", "%A %d %B %Y %H:%M", "%d %b %Y %H:%M", "%d %B %Y %H:%M"]
    for candidate in candidates:
        candidate = re.sub(r'(\d{1,2})(st|nd|rd|th)', r'\1', candidate)
        for fmt in formats:
            try: return datetime.strptime(candidate, fmt)
            except: pass
    return None

def parse_sale_datetime(value):
    if not value: return None
    text = clean_text(str(value))
    for fmt in ("%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M"):
        try: return datetime.strptime(text, fmt)
        except: pass
    return None

def is_event_expired(event_date_text):
    dt = parse_event_datetime(event_date_text)
    return datetime.now() >= dt if dt else False

def to_number(value):
    if value is None: return 0.0
    # Handle values like "Mobile (£ 0.00)" or "£ 400.00"
    text = str(value)
    match = re.search(r'([\d\.,]+)', text.replace(",", ""))
    if match:
        try: return float(match.group(1))
        except: return 0.0
    return 0.0

def to_int(value):
    try: return int(float(str(value).replace(",", "").strip()))
    except: return 0
