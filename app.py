import os
from dotenv import load_dotenv
load_dotenv()
from flask import Flask

import extensions as context
from config import APP_TITLE, JWT_SECRET
from core.state import AppState
from core.users import ensure_admin_user
from platforms.registry import build_platform_adapters
from routes import register_routes


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.secret_key = JWT_SECRET

    # Configure template reload based on environment
    is_prod = (os.getenv("FLASK_ENV") == "production")
    app.config["TEMPLATES_AUTO_RELOAD"] = not is_prod

    # Proxy Configuration for Nginx
    if os.getenv("TRUST_PROXY") == "true":
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


    # Security warnings for dev fallbacks
    from config import ADMIN_PASSWORD
    if ADMIN_PASSWORD == "admin123":
        print("\n[SECURITY WARNING]: Using default ADMIN_PASSWORD ('admin123')! Please set the ADMIN_PASSWORD environment variable in production.\n")
    if JWT_SECRET == "CHANGE-THIS-TO-A-LONG-RANDOM-SECRET":
        print("\n[SECURITY WARNING]: Using default JWT_SECRET! Please set the JWT_SECRET environment variable to a secure value in production.\n")

    from database import init_db, test_db_connection, get_engine_type
    try:
        init_db()
        if test_db_connection():
            engine_type = get_engine_type().upper()
            print("\n===============================")
            print(f"{engine_type} connected")
            print("===============================\n")
            context.db_connected = True
        else:
            print("Database connection failed!")
            context.db_connected = False
    except Exception as e:
        print(f"Database Initialization Failed (Falling back to JSON): {e}")
    ensure_admin_user()
    context.state = AppState()
    context.platform_adapters = build_platform_adapters()

    from services.scheduler_service import SchedulerService
    context.scheduler = SchedulerService()

    # Document: A separate scheduler service is planned for Phase 2 to isolate processes.
    # Auto-start scheduler if configured
    if os.getenv("AUTO_START_SCHEDULER") == "true":
        print("[SCHEDULER]: AUTO_START_SCHEDULER is enabled. Booting background scheduler thread...")
        context.scheduler.start()

    # Graceful shutdown handler for container SIGTERM/SIGINT signals
    import signal
    import sys
    def handle_shutdown(signum, frame):
        print(f"[SYSTEM]: Received shutdown signal {signum}. Initiating graceful exit...")
        if context.scheduler:
            print("[SCHEDULER]: Stopping background thread...")
            context.scheduler.stop()
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)
    except ValueError:
        # signal only works in main thread, ignore if run inside worker threads
        pass

    register_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print(f"Starting {APP_TITLE} on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
