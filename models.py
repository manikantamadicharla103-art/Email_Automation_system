from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ─── Admin User ───────────────────────────────────────────────────────────────
class Admin(db.Model):
    __tablename__ = 'admins'
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)

    def set_password(self, raw):
        self.password = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password, raw)


# ─── Contact ──────────────────────────────────────────────────────────────────
class Contact(db.Model):
    __tablename__ = 'contacts'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    email      = db.Column(db.String(120), nullable=False)
    course     = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ─── Email Template ───────────────────────────────────────────────────────────
class EmailTemplate(db.Model):
    __tablename__ = 'email_templates'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    subject    = db.Column(db.String(255), nullable=False)
    body       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Email Log ────────────────────────────────────────────────────────────────
class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    id         = db.Column(db.Integer, primary_key=True)
    recipient  = db.Column(db.String(120), nullable=False)
    subject    = db.Column(db.String(255), nullable=False)
    status     = db.Column(db.String(20), nullable=False)   # 'sent' | 'failed'
    error_msg  = db.Column(db.Text, nullable=True)
    sent_at    = db.Column(db.DateTime, default=datetime.utcnow)
