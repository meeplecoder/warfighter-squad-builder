"""Outgoing mail for auth flows (verification, password reset, notices).

Backends (MAIL_BACKEND): 'console' logs the message (local development — links appear in the
server log), 'resend' posts to the Resend HTTPS API, 'smtp' delivers through any SMTP relay,
'memory' appends to `outbox` (tests). Real deliveries run in a background thread so response time
does not reveal whether an account exists.
"""
import json
import smtplib
import ssl
import threading
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import make_msgid

from flask import current_app

outbox = []  # 'memory' backend


def send(to, subject, body):
    cfg = current_app.config
    msg = EmailMessage()
    msg['From'] = cfg['MAIL_FROM']
    msg['To'] = to
    msg['Subject'] = subject
    msg['Message-ID'] = make_msgid()
    msg.set_content(body)

    backend = cfg['MAIL_BACKEND']
    if backend == 'memory':
        outbox.append(msg)
    elif backend in ('resend', 'smtp'):
        deliver = _deliver_resend if backend == 'resend' else _deliver_smtp
        app = current_app._get_current_object()
        threading.Thread(target=deliver, args=(app, msg), daemon=True).start()
    else:
        current_app.logger.warning('[mail:console] To: %s | Subject: %s\n%s', to, subject, body)


RESEND_URL = 'https://api.resend.com/emails'


def _deliver_resend(app, msg):
    """POST /emails (https://resend.com/docs/api-reference/emails/send-email). The From domain must be
    verified in Resend."""
    payload = {
        'from': msg['From'],
        'to': [msg['To']],
        'subject': msg['Subject'],
        'text': msg.get_content(),
    }
    req = urllib.request.Request(RESEND_URL, data=json.dumps(payload).encode('utf-8'), method='POST', headers={
        'Authorization': f"Bearer {app.config['RESEND_API_KEY']}",
        'Content-Type': 'application/json',
        'User-Agent': 'warfighter-squad-builder',
        'Idempotency-Key': msg['Message-ID'].strip('<>'),  # unique per message: a resent request is not delivered twice
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            res.read()
    except urllib.error.HTTPError as e:
        app.logger.error('Resend rejected mail (to=%s, subject=%s): HTTP %s %s',
                         msg['To'], msg['Subject'], e.code, e.read().decode('utf-8', 'replace')[:500])
    except Exception:
        app.logger.exception('Resend delivery failed (to=%s, subject=%s)', msg['To'], msg['Subject'])


def _deliver_smtp(app, msg):
    cfg = app.config
    try:
        context = ssl.create_default_context()
        if cfg['MAIL_USE_SSL']:
            server = smtplib.SMTP_SSL(cfg['MAIL_HOST'], cfg['MAIL_PORT'], context=context, timeout=20)
        else:
            server = smtplib.SMTP(cfg['MAIL_HOST'], cfg['MAIL_PORT'], timeout=20)
            server.starttls(context=context)
        with server:
            if cfg['MAIL_USERNAME']:
                server.login(cfg['MAIL_USERNAME'], cfg['MAIL_PASSWORD'])
            server.send_message(msg)
    except Exception:
        app.logger.exception('Mail delivery failed (to=%s, subject=%s)', msg['To'], msg['Subject'])
