from flask import Flask
from config import Config
from models import db, Member, Payment, Project, Expense

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    db.create_all()
    print("Database created successfully!")
