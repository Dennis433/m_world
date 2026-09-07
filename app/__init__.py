from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    from app.routes.auth import auth
    from app.routes.shop import shop
    from app.routes.cart import cart
    from app.routes.admin import admin

    app.register_blueprint(auth)
    app.register_blueprint(shop)
    app.register_blueprint(cart)
    app.register_blueprint(admin, url_prefix='/admin')

    return app