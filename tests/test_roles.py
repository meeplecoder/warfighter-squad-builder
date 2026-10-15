"""Roles and access control: one admin (the account named `admin`), everybody else is a plain user."""
from conftest import card_id


def _squad_payload(app, name='Roles test squad'):
    return {'name': name, 'mission_card_id': card_id(app, 'S-200'), 'nation': 'US', 'status': 'draft',
            'soldiers': [{'card_id': card_id(app, 'S-001'), 'gear': []}]}


def test_role_is_derived_from_the_username(app):
    from app.models import User
    from app.roles import role_of
    with app.app_context():
        assert role_of(User(username='admin')) == 'admin'
        assert role_of(User(username='Admin')) == 'admin'          # case-insensitive
        assert role_of(User(username='alice')) == 'user'
        sneaky = User(username='mallory')
        sneaky._legacy_is_admin = 1                                  # the stored flag is never trusted
        assert role_of(sneaky) == 'user' and not sneaky.is_admin
        assert role_of(None) == 'user'


def test_admin_name_cannot_be_registered(app, client):
    for name in ('admin', 'Admin', 'ADMIN'):
        r = client.post('/api/auth/register', json={'username': name, 'email': f'{name.lower()}x@example.com',
                                                    'password': 'a long unrelated pass phrase 4821'})
        assert r.status_code == 400 and 'reserved' in r.get_json()['error'].lower()
    from app.models import User
    with app.app_context():
        assert User.query.filter(User.email.like('%x@example.com')).count() == 0


def test_me_reports_the_role(app, client, login):
    login(client, 'admin')
    me = client.get('/api/auth/me').get_json()['user']
    assert me['role'] == 'admin' and me['is_admin'] is True
    other = app.test_client()
    login(other, 'carol')
    me = other.get('/api/auth/me').get_json()['user']
    assert me['role'] == 'user' and me['is_admin'] is False


def test_squad_permissions(app, login):
    alice, bob, admin, anon = (app.test_client() for _ in range(4))
    login(alice, 'alice'); login(bob, 'bob'); login(admin, 'admin')

    r = alice.post('/api/squads', json=_squad_payload(app))
    assert r.status_code == 201
    sid = r.get_json()['squad']['id']

    # a draft is visible to its owner and to the admin only
    assert alice.get(f'/api/squads/{sid}').status_code == 200
    assert admin.get(f'/api/squads/{sid}').status_code == 200
    assert bob.get(f'/api/squads/{sid}').status_code == 200          # the detail endpoint is public...
    assert anon.get(f'/api/squads/{sid}/export').status_code == 404  # ...but exporting a draft is not
    assert bob.get(f'/api/squads/{sid}/export').status_code == 404
    assert admin.get(f'/api/squads/{sid}/export').status_code == 200

    # another user cannot edit, publish or delete it
    body = _squad_payload(app, 'hijacked')
    assert bob.put(f'/api/squads/{sid}', json=body).status_code == 403
    assert bob.post(f'/api/squads/{sid}/publish', json={}).status_code == 403
    assert bob.delete(f'/api/squads/{sid}', json={}).status_code == 403
    assert anon.put(f'/api/squads/{sid}', json=body).status_code == 401

    # the admin can, and the squad keeps its owner
    r = admin.put(f'/api/squads/{sid}', json=_squad_payload(app, 'Edited by admin'))
    assert r.status_code == 200 and r.get_json()['squad']['name'] == 'Edited by admin'
    assert r.get_json()['squad']['owner']['username'] == 'alice'
    assert admin.post(f'/api/squads/{sid}/publish', json={}).status_code == 200
    assert admin.delete(f'/api/squads/{sid}', json={}).status_code == 200


def test_admin_sees_other_users_drafts_in_the_list(app, login):
    alice, bob, admin = (app.test_client() for _ in range(3))
    login(alice, 'alice'); login(bob, 'bob'); login(admin, 'admin')
    sid = alice.post('/api/squads', json=_squad_payload(app, 'alice draft for list'))
    sid = sid.get_json()['squad']['id']
    ids = lambda c: {s['id'] for s in c.get('/api/squads?per_page=100').get_json()['items']}
    assert sid in ids(alice) and sid in ids(admin) and sid not in ids(bob)


def test_campaign_permissions(app, login):
    alice, bob, admin = (app.test_client() for _ in range(3))
    login(alice, 'alice'); login(bob, 'bob'); login(admin, 'admin')
    draft = {'name': 'Role test campaign', 'summary': 's', 'intro': 'i', 'missions': [], 'status': 'draft'}
    r = alice.post('/api/campaigns', json=draft)
    assert r.status_code == 201
    cid = r.get_json()['campaign']['id']

    assert bob.get(f'/api/campaigns/{cid}').status_code == 404       # drafts are private...
    assert admin.get(f'/api/campaigns/{cid}').status_code == 200      # ...except for the admin
    assert bob.put(f'/api/campaigns/{cid}', json=draft).status_code == 403
    assert bob.delete(f'/api/campaigns/{cid}', json={}).status_code == 403
    r = admin.put(f'/api/campaigns/{cid}', json=dict(draft, name='Edited by admin'))
    assert r.status_code == 200 and r.get_json()['campaign']['name'] == 'Edited by admin'
    assert r.get_json()['campaign']['owner']['username'] == 'alice'
    assert admin.delete(f'/api/campaigns/{cid}', json={}).status_code == 200


def test_translation_editor_is_admin_only(app, client, login):
    rule = next(r for r in app.url_map.iter_rules()
                if r.endpoint.startswith('translations.') and 'GET' in r.methods and not r.arguments)
    assert client.get(rule.rule).status_code == 401                   # anonymous
    user = app.test_client()
    login(user, 'dave')
    assert user.get(rule.rule).status_code == 403                     # plain user
    admin = app.test_client()
    login(admin, 'admin')
    assert admin.get(rule.rule + '?lang=es').status_code not in (401, 403)


# --- creating on behalf of another owner (`owner` field) -----------------------------------------------------
def _squad_body(app, **extra):
    from app.models import Card
    with app.app_context():
        mission = Card.query.filter_by(number='S-200').first().id
        soldier = Card.query.filter_by(number='S-001').first().id
    return {'name': 'On behalf', 'nation': 'US', 'mission_card_id': mission, 'status': 'draft',
            'soldiers': [{'card_id': soldier, 'gear': []}], **extra}


def _campaign_body(**extra):
    return {'name': 'Camp on behalf', 'status': 'draft', 'missions': [], 'links': [], **extra}


def test_only_admin_can_create_for_another_owner(app, client, login):
    from app.models import User
    other = app.test_client()
    login(other, 'plainuser')
    assert other.post('/api/squads', json=_squad_body(app, owner='someone_else')).status_code == 403
    assert other.post('/api/campaigns', json=_campaign_body(owner='someone_else')).status_code == 403
    with app.app_context():
        assert User.query.filter_by(username_lower='someone_else').first() is None
    # no owner / one's own name: the session user
    r = other.post('/api/squads', json=_squad_body(app))
    assert r.status_code == 201 and r.get_json()['squad']['owner']['username'] == 'plainuser'
    r = other.post('/api/squads', json=_squad_body(app, owner='PlainUser'))
    assert r.status_code == 201 and r.get_json()['squad']['owner']['username'] == 'plainuser'


def test_admin_creates_for_existing_and_new_owners(app, client, login):
    from app.models import User
    admin = app.test_client()
    login(admin, 'admin')
    login(app.test_client(), 'author1')
    r = admin.post('/api/squads', json=_squad_body(app, owner='author1'))
    assert r.status_code == 201 and r.get_json()['squad']['owner']['username'] == 'author1'
    r = admin.post('/api/squads', json=_squad_body(app, owner='Brand_New'))
    assert r.status_code == 201 and r.get_json()['squad']['owner']['username'] == 'Brand_New'
    with app.app_context():
        assert User.query.filter_by(username_lower='brand_new').first().status == 'reserved'
    r = admin.post('/api/campaigns', json=_campaign_body(owner='author1'))
    assert r.status_code == 201 and r.get_json()['campaign']['owner']['username'] == 'author1'
    assert admin.post('/api/squads', json=_squad_body(app, owner='bad name!')).status_code == 400
    r = admin.post('/api/squads', json=_squad_body(app))              # default: the admin itself
    assert r.get_json()['squad']['owner']['username'] == 'admin'
