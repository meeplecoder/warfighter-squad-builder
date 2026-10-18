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
    assert over['valid'] and not over['errors']       # over budget is a warning, it does not block
    assert [w['code'] for w in over['warnings']] == ['OVER_BUDGET']


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


def test_builders_work_anonymously_but_saving_needs_login(client):
    # The generator and the validators are open to visitors; only saving requires an account
    assert client.get('/api/generator/options').status_code == 200
    assert client.post('/api/generator/generate', json={}).status_code != 401
    assert client.post('/api/campaigns/validate', json={}).status_code == 200
    assert client.post('/api/squads/', json={}).status_code == 401
    assert client.post('/api/campaigns', json={}).status_code == 401


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


def test_bundled_card_csv_format():
    """The shipped card CSV (when present) has the columns the importer reads and no card images are tracked."""
    import csv
    import pathlib
    import subprocess
    root = pathlib.Path(__file__).resolve().parent.parent
    path = root / 'cards' / 'warfighter_cards.csv'
    if path.exists():
        with open(path, newline='', encoding='utf-8') as f:
            header = next(csv.reader(f))
        assert {'Number', 'Name', 'Type', 'Nation', 'Stats', 'Notes', 'Module'} <= set(header)
    tracked = subprocess.run(['git', 'ls-files', 'static/card_images'], cwd=root, capture_output=True, text=True).stdout.split()
    assert tracked in ([], ['static/card_images/README.md'])      # card images never belong in the repository


def test_expansions_endpoint(app, client, login):
    assert client.get('/api/profile/expansions').status_code == 401
    login(client)
    r = client.get('/api/profile/expansions').get_json()
    assert (r['owned'], r['total']) == (1, 1)
    exp = r['expansions'][0]
    assert exp['module'] == 'Sample Set' and exp['owned'] and exp['cards'] == 19
    assert exp['player_soldiers'] == 4 and exp['missions'] == 3 and exp['nations'] == ['US']


def test_expansions_order_core_first():
    from app.required_modules import module_rank
    names = ['Multi-Era Expansion #01', '#10 - UK #1', 'KS', '#02 - US #1', 'Core Europe', '#01 - Core Pacific']
    assert sorted(names, key=module_rank) == ['Core Europe', '#01 - Core Pacific', '#02 - US #1', '#10 - UK #1',
                                              'KS', 'Multi-Era Expansion #01']


def test_healthz(client):
    r = client.get('/healthz')
    assert r.status_code == 200 and r.get_json()['status'] == 'ok'


def test_overloaded_soldier_is_a_warning(app, client, login):
    from app.models import Card
    c = app.test_client()
    login(c, 'loader')
    with app.app_context():
        mission = Card.query.filter_by(number='S-200').first().id
        soldier = Card.query.filter_by(number='S-001').first()
        gear = Card.query.filter(Card.card_type == 'Weapon').first()
        ids = (mission, soldier.id, gear.id)
    mission, soldier, gear = ids
    r = c.post('/api/squads/validate', json={'nation': 'US', 'mission_card_id': mission,
        'soldiers': [{'card_id': soldier, 'gear': [{'card_id': gear, 'quantity': 40}]}]}).get_json()
    assert 'OVER_LOADOUT' in [w['code'] for w in r['warnings']]
    assert 'OVER_LOADOUT' not in [e['code'] for e in r['errors']]


def test_ammo_card_numbers_from_weapon_notes():
    from app.models import ammo_number_for
    assert ammo_number_for('Single Shot.\nEach Rocket: costs 1. Loadout 2.\nRockets (0).') == 'AM-R1L2'
    assert ammo_number_for('Each Rocket: costs 2.\nExpended.') == 'AM-R2'
    assert ammo_number_for('Each shell: costs 2.') == 'AM-S2'
    assert ammo_number_for('Each Grenade: costs 1.') == 'AM-G1'
    assert ammo_number_for('Rockets (8).') is None and ammo_number_for(None) is None


def test_text_import_reads_strategy_notes(app):
    from app import squad_io
    with app.test_request_context('/'):
        text = ("Squad: Imported\nNation: US\n\nAlder [S-001] — 12 RP\n\n"
                "Strategy Notes:\nSource video: https://www.youtube.com/watch?v=XXXX\nSecond line\n\n— Warfighter WWII - Squad Builder\n")
        draft, _warnings = squad_io.import_text(text)
        assert draft['notes'] == 'Source video: https://www.youtube.com/watch?v=XXXX\nSecond line'
        assert [s['card'].number for s in draft['soldiers']] == ['S-001']
        assert squad_io.draft_to_json(draft, [])['notes'] == draft['notes']
