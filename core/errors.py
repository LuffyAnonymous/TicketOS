class PlatformError(Exception):
    """Base exception for all ticket platform connector issues."""
    pass

class PlatformLoginError(PlatformError):
    """Raised when authentication with the platform fails due to bad credentials, expired sessions, or verification checkpoints."""
    pass

class PlatformTimeoutError(PlatformError):
    """Raised when a page resource or locator fails to load within the timeout limit."""
    pass

class PlatformBlockedError(PlatformError):
    """Raised when the platform blocks access (e.g. Captcha, Cloudflare, IP ban)."""
    pass

class PlatformLayoutError(PlatformError):
    """Raised when the platform changes its HTML DOM structure or JSON schema, making scraping selectors obsolete."""
    pass

class PlatformMissingDataError(PlatformError):
    """Raised when critical order or customer attributes are missing or cannot be extracted."""
    pass
