"""Smoke tests on the demo data set: import, API, validation, metrics, generator."""
from conftest import card_id


def test_import_and_cards_api(client):
    r = client.get('/api/cards?per_page=100')
    assert r.status_code == 200
    assert r.get_json()['total'] == 19
    assert client.get('/api/nations').get_json()['nations'] == ['US']


def test_printed_gear_is_recorded(app):
    """Importing must record each soldier's printed gear (it used to be stripped from the notes unrecorded)."""
    from app.models import CardAssociation
    with app.app_context():
        assert CardAssociation.query.count() == 3


def test_validate_squad(app, client):
    mission, alder, birch = (card_id(app, n) for n in ('S-200', 'S-001', 'S-002'))
    ok = client.post('/api/squads/validate', json={
        'nation': 'US', 'mission_card_id': mission,
        'soldiers': [{'card_id': alder, 'gear': []}, {'card_id': birch, 'gear': []}]}).get_json()
    assert ok['valid'] and ok['computed']['rp_total'] == 21
    cedar = card_id(app, 'S-003')
    raid = card_id(app, 'S-201')      # budget 35
    over = client.post('/api/squads/validate', json={
        'nation': 'US', 'mission_card_id': raid,
        'soldiers': [{'card_id': i, 'gear': []} for i in (alder, birch, cedar)]}).get_json()
    assert not over['valid'] and over['errors'][0]['code'] == 'OVER_BUDGET'


def test_metrics_of_a_squad(app):
    from app import db, metrics
    from app.models import Squad, SquadSoldier, SquadGear, User
    with app.app_context():
        user = User(username='metrics', email='m@example.com', password_hash='x')
        db.session.add(user)
        db.session.flush()
        squad = Squad(user_id=user.id, name='m', mission_card_id=card_id(app, 'S-200'), nation='US', status='draft')
        db.session.add(squad)
        db.session.flush()
        ss = SquadSoldier(squad_id=squad.id, card_id=card_id(app, 'S-003'), sort_order=0)
        db.session.add(ss)
        db.session.flush()
        db.session.add(SquadGear(squad_soldier_id=ss.id, card_id=card_id(app, 'S-101'), quantity=1))
        db.session.commit()
        result = metrics.squad_metrics(squad)
    assert set(result['metrics']) == set(metrics.METRIC_KEYS)
    assert result['metrics']['ranged_fire']['raw'] > 0


def test_skill_effects():
    from app import skill_effects
    mods = skill_effects.soldier_mods({'Marksman', 'Veteran'}, {'US-Lucky Helmet'})
    assert mods['actions'] == 1 and mods['xp'] == 2 and mods['hp_add'] == 1
    assert skill_effects.bonuses(mods, {'ranged'}, 1) == (1, 0)


def test_generator_requires_login(client):
    assert client.post('/api/generator/generate', json={}).status_code == 401


def test_generator_builds_a_valid_squad(app, client, login):
    login(client)
    opts = client.get('/api/generator/options').get_json()
    assert [n['code'] for n in opts['nations']] == ['US']
    body = {'nation': 'US', 'mission_card_id': card_id(app, 'S-202'), 'seed': 'T1'}
    first = client.post('/api/generator/generate', json=body)
    assert first.status_code == 200
    a = first.get_json()
    assert not any('exceeds' in w or 'costs' in w for w in a['warnings'])
    assert any(s['card']['card_subtype'] == 'Player' for s in a['soldiers'])
    assert a['fitness']['label'] in ('strong', 'solid', 'risky', 'unfit')
    assert len(a['alternatives']) <= 2
    # Optimal is deterministic for the same inputs and seed
    b = client.post('/api/generator/generate', json=body).get_json()
    names = lambda r: [s['card']['name'] for s in r['soldiers']]
    assert names(a) == names(b)
