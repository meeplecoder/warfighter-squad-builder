"""Own usage stats: anonymous counters, bot/admin filtering, admin-only report."""
import pytest

BROWSER = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0'}


@pytest.fixture(autouse=True)
def clean_stats(app):
    from app import db
    from app.models import StatHit, StatVisitor
    with app.app_context():
        StatHit.query.delete()
        StatVisitor.query.delete()
        db.session.commit()


def test_hits_are_counted_with_unique_visitors(app):
    c = app.test_client()
    for route in ('cards', 'cards', 'squads', 'not-a-route'):
        assert c.post('/api/stats/hit', json={'route': route}, headers=BROWSER).status_code == 204
    from app.models import StatHit
    with app.app_context():
        rows = {r.route: r.hits for r in StatHit.query.all()}
    assert rows['cards'] == 2 and rows['squads'] == 1 and rows['other'] == 1
    assert rows['_visitors'] == 1                                   # same IP + UA = one visitor


def test_bots_and_admins_are_not_counted(app, login):
    c = app.test_client()
    c.post('/api/stats/hit', json={'route': 'cards'}, headers={'User-Agent': 'Googlebot/2.1'})
    login(c, 'admin')
    c.post('/api/stats/hit', json={'route': 'cards'}, headers=BROWSER)
    from app.models import StatHit
    with app.app_context():
        assert StatHit.query.count() == 0


def test_report_is_admin_only_and_aggregates(app, client, login):
    assert client.get('/api/stats/report').status_code == 401
    app.test_client().post('/api/stats/hit', json={'route': 'cards'}, headers=BROWSER)
    admin = app.test_client()
    login(admin, 'admin')
    r = admin.get('/api/stats/report?days=7').get_json()
    assert len(r['series']) == 7
    today = r['series'][-1]
    assert today['views'] == 1 and today['visitors'] == 1
    assert r['routes'] == [{'route': 'cards', 'views': 1}]
