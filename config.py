import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'irrigation-association-secret-key-2024'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///irrigation_association.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Admin credentials - يُنصح بتغييرها في الإنتاج
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME') or 'alqotabry'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or '01100010'

