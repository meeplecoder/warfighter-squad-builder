from app import mailer


def test_feedback_validation(client):
    assert client.post('/api/feedback', json={'kind': 'nope', 'text': 'long enough text'}).status_code == 400
    assert client.post('/api/feedback', json={'kind': 'bug', 'text': 'short'}).status_code == 400


def test_feedback_sent(app, client):
    app.config['BUG_REPORT_EMAIL'] = 'dev@example.com'
    mailer.outbox.clear()
    r = client.post('/api/feedback', json={'kind': 'feature', 'text': 'please add a dark theme'})
    assert r.status_code == 200
    assert len(mailer.outbox) == 1 and mailer.outbox[0]['To'] == 'dev@example.com'
    # honeypot: pretends success but sends nothing
    client.post('/api/feedback', json={'kind': 'bug', 'text': 'spam spam spam spam', 'website': 'x'})
    assert len(mailer.outbox) == 1
