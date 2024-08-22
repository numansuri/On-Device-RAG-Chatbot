import os
import secrets
SECRET_KEY = secrets.token_hex(16)

class Config:
    SECRET_KEY = SECRET_KEY
    SQLALCHEMY_DATABASE_URI = 'sqlite:///new_site.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LLAMA_ENDPOINT = os.environ.get('LLAMA_ENDPOINT') or 'http://localhost:11434/api/generate'