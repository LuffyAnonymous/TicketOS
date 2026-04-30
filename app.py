import os
from dotenv import load_dotenv
load_dotenv()
from flask import Flask

import extensions as context
from config import APP_TITLE, JWT_SECRET
from core.state import AppState
from core.users import ensure_admin_user
from platforms.registry import build_platform_adapters
from routes.register_routes import register_routes


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.secret_key = JWT_SECRET
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    ensure_admin_user()
    context.state = AppState()
    context.platform_adapters = build_platform_adapters()

    register_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print(f"Starting {APP_TITLE} on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
