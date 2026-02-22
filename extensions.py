from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager

# এক্সটেনশন অবজেক্ট তৈরি করুন (app ছাড়া)
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
