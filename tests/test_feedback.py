from app import mailer


def test_feedback_requires_login(client):
    assert client.post('/api/feedback', json={'kind': 'bug', 'text': 'long enough text'}).status_code == 401
    assert client.get('/api/feedback').status_code == 401


def test_feedback_validation(client, login):
    login(client)
    assert client.post('/api/feedback', json={'kind': 'nope', 'text': 'long enough text'}).status_code == 400
    assert client.post('/api/feedback', json={'kind': 'bug', 'text': 'short'}).status_code == 400


def test_feedback_stored_mailed_and_admin_only(app, client, login):
    app.config['BUG_REPORT_EMAIL'] = 'dev@example.com'
    mailer.outbox.clear()
    login(client)
    assert client.post('/api/feedback', json={'kind': 'feature', 'text': 'please add a dark theme'}).status_code == 200
    assert len(mailer.outbox) == 1 and mailer.outbox[0]['To'] == 'dev@example.com'
    client.post('/api/feedback', json={'kind': 'bug', 'text': 'spam spam spam spam', 'website': 'x'})
    assert len(mailer.outbox) == 1                      # honeypot: nothing stored or sent
    assert client.get('/api/feedback').status_code == 403
    admin = app.test_client()
    login(admin, 'admin')
    reports = admin.get('/api/feedback').get_json()['reports']
    assert [r['kind'] for r in reports] == ['feature'] and reports[0]['username'] == 'tester'
