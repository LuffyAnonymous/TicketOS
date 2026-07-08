from routes.auth_routes import auth_bp
from routes.order_routes import order_bp
from routes.platform_routes import platform_bp
from routes.dashboard_routes import dashboard_bp

def register_routes(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(order_bp)
    app.register_blueprint(platform_bp)
    app.register_blueprint(dashboard_bp)
