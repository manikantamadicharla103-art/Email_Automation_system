import os, smtplib, io
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

import pandas as pd
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'change-me-in-production')

BASE_DIR    = os.path.abspath(os.path.dirname(__file__))
DB_PATH     = os.path.join(BASE_DIR, 'database', 'email_automation.db')
UPLOAD_DIR  = os.path.join(BASE_DIR, 'uploads')
ATTACH_DIR  = os.path.join(BASE_DIR, 'attachments')

app.config['SQLALCHEMY_DATABASE_URI']        = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH']             = 16 * 1024 * 1024  # 16 MB

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(ATTACH_DIR, exist_ok=True)

from models import db, Admin, Contact, EmailTemplate, EmailLog
db.init_app(app)

ALLOWED_CSV = {'csv'}
ALLOWED_PDF = {'pdf'}

# ── Helpers ───────────────────────────────────────────────────────────────────
def allowed_file(filename, allowed):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def send_email(to_email, subject, body, attachment_path=None):
    try:
        msg = MIMEMultipart()
        msg['From']    = os.getenv('GMAIL_USER')
        msg['To']      = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition',
                            f'attachment; filename="{os.path.basename(attachment_path)}"')
            msg.attach(part)

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(os.getenv('GMAIL_USER'), os.getenv('GMAIL_APP_PASSWORD'))
            server.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)

# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'admin_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            session['admin_id'] = admin.id
            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    total_contacts = Contact.query.count()
    total_sent     = EmailLog.query.filter_by(status='sent').count()
    total_failed   = EmailLog.query.filter_by(status='failed').count()
    recent_logs    = EmailLog.query.order_by(EmailLog.sent_at.desc()).limit(5).all()
    return render_template('dashboard.html',
                           total_contacts=total_contacts,
                           total_sent=total_sent,
                           total_failed=total_failed,
                           recent_logs=recent_logs)

# ── Contacts ──────────────────────────────────────────────────────────────────
@app.route('/contacts')
@login_required
def contacts():
    all_contacts = Contact.query.order_by(Contact.created_at.desc()).all()
    return render_template('contacts.html', contacts=all_contacts)

@app.route('/contacts/upload', methods=['POST'])
@login_required
def upload_contacts():
    file = request.files.get('csv_file')
    if not file or not allowed_file(file.filename, ALLOWED_CSV):
        flash('Please upload a valid CSV file.', 'danger')
        return redirect(url_for('contacts'))
    try:
        df = pd.read_csv(io.StringIO(file.read().decode('utf-8')))
        df.columns = [c.strip().lower() for c in df.columns]
        added = 0
        for _, row in df.iterrows():
            name   = str(row.get('name', '')).strip()
            email  = str(row.get('email', '')).strip()
            course = str(row.get('course', '')).strip()
            if name and email and '@' in email:
                if not Contact.query.filter_by(email=email).first():
                    db.session.add(Contact(name=name, email=email, course=course))
                    added += 1
        db.session.commit()
        flash(f'{added} contact(s) imported successfully.', 'success')
    except Exception as e:
        flash(f'Error reading CSV: {e}', 'danger')
    return redirect(url_for('contacts'))

@app.route('/contacts/delete/<int:cid>', methods=['POST'])
@login_required
def delete_contact(cid):
    c = Contact.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    flash('Contact deleted.', 'info')
    return redirect(url_for('contacts'))

# ── Email Templates ───────────────────────────────────────────────────────────
@app.route('/templates')
@login_required
def email_templates():
    templates = EmailTemplate.query.order_by(EmailTemplate.created_at.desc()).all()
    return render_template('templates_page.html', templates=templates)

@app.route('/templates/create', methods=['POST'])
@login_required
def create_template():
    name    = request.form.get('name', '').strip()
    subject = request.form.get('subject', '').strip()
    body    = request.form.get('body', '').strip()
    if not (name and subject and body):
        flash('All fields are required.', 'danger')
        return redirect(url_for('email_templates'))
    db.session.add(EmailTemplate(name=name, subject=subject, body=body))
    db.session.commit()
    flash('Template created!', 'success')
    return redirect(url_for('email_templates'))

@app.route('/templates/edit/<int:tid>', methods=['POST'])
@login_required
def edit_template(tid):
    t = EmailTemplate.query.get_or_404(tid)
    t.name    = request.form.get('name', t.name).strip()
    t.subject = request.form.get('subject', t.subject).strip()
    t.body    = request.form.get('body', t.body).strip()
    t.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Template updated!', 'success')
    return redirect(url_for('email_templates'))

@app.route('/templates/delete/<int:tid>', methods=['POST'])
@login_required
def delete_template(tid):
    t = EmailTemplate.query.get_or_404(tid)
    db.session.delete(t)
    db.session.commit()
    flash('Template deleted.', 'info')
    return redirect(url_for('email_templates'))

@app.route('/templates/get/<int:tid>')
@login_required
def get_template(tid):
    t = EmailTemplate.query.get_or_404(tid)
    return jsonify({'name': t.name, 'subject': t.subject, 'body': t.body})

# ── Send Email ────────────────────────────────────────────────────────────────
@app.route('/send-email', methods=['GET', 'POST'])
@login_required
def send_email_page():
    contacts  = Contact.query.order_by(Contact.name).all()
    templates = EmailTemplate.query.order_by(EmailTemplate.name).all()

    if request.method == 'POST':
        mode        = request.form.get('mode')          # 'single' | 'bulk'
        template_id = request.form.get('template_id')
        subject_in  = request.form.get('subject', '').strip()
        body_in     = request.form.get('body', '').strip()

        # attachment
        attachment_path = None
        att_file = request.files.get('attachment')
        if att_file and att_file.filename and allowed_file(att_file.filename, ALLOWED_PDF):
            fname = secure_filename(att_file.filename)
            attachment_path = os.path.join(ATTACH_DIR, fname)
            att_file.save(attachment_path)

        def personalize(text, contact):
            return text.replace('{name}', contact.name).replace('{course}', contact.course or '')

        recipients = []
        if mode == 'bulk':
            recipients = Contact.query.all()
        else:
            cid = request.form.get('contact_id')
            c   = Contact.query.get(cid)
            if c:
                recipients = [c]
            else:
                flash('No contact selected.', 'danger')
                return redirect(url_for('send_email_page'))

        sent_count, fail_count = 0, 0
        for contact in recipients:
            subj = personalize(subject_in, contact)
            body = personalize(body_in, contact)
            ok, err = send_email(contact.email, subj, body, attachment_path)
            status = 'sent' if ok else 'failed'
            if ok: sent_count += 1
            else:  fail_count += 1
            db.session.add(EmailLog(recipient=contact.email,
                                    subject=subj, status=status, error_msg=err))
        db.session.commit()
        flash(f'Done! Sent: {sent_count} | Failed: {fail_count}', 'success')
        return redirect(url_for('logs'))

    return render_template('send_email.html', contacts=contacts, templates=templates)

# ── Logs ──────────────────────────────────────────────────────────────────────
@app.route('/logs')
@login_required
def logs():
    all_logs = EmailLog.query.order_by(EmailLog.sent_at.desc()).all()
    return render_template('logs.html', logs=all_logs)

# ── Init ──────────────────────────────────────────────────────────────────────
def init_db():
    with app.app_context():
        db.create_all()
        if not Admin.query.filter_by(username='admin').first():
            a = Admin(username='admin')
            a.set_password('admin123')
            db.session.add(a)
            db.session.commit()
            print('✅ Default admin created — username: admin | password: admin123')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
