"""Admin user management: permissions, status changes, editing, password handling, deletion."""
from conftest import card_id

PW = 'a long unrelated pass phrase 4821'


def _admin(app, login):
    c = app.test_client()
    login(c, 'admin')
    return c


def _make(app, name, **kw):
    from app import db
    from app.models import User, now_utc
    from app.security import hash_password
    with app.app_context():
        u = User.query.filter_by(username=name).first()
        if not u:
            u = User(username=name, email=f'{name}@example.com', password_hash=hash_password(PW),
                     email_verified_at=now_utc(), **kw)
            db.session.add(u)
            db.session.commit()
        return u.id


def test_only_the_admin_can_use_it(app, client, login):
    assert client.get('/api/admin/users').status_code == 401
    uid = _make(app, 'plainuser')
    other = app.test_client()
    login(other, 'plainuser')
    assert other.get('/api/admin/users').status_code == 403
    assert other.put(f'/api/admin/users/{uid}', json={'status': 'disabled'}).status_code == 403
    assert other.delete(f'/api/admin/users/{uid}', json={}).status_code == 403


def test_list_and_detail_never_expose_passwords(app, login):
    uid = _make(app, 'listed')
    admin = _admin(app, login)
    rows = admin.get('/api/admin/users').get_json()['users']
    row = next(r for r in rows if r['username'] == 'listed')
    assert row['status'] == 'enabled' and row['email'] == 'listed@example.com'
    detail = admin.get(f'/api/admin/users/{uid}').get_json()['user']
    assert detail['has_password'] is True
    assert 'password_hash' not in detail and 'password' not in detail and 'scrypt' not in str(detail)


def test_disable_blocks_login_and_sessions_and_enable_restores(app, login):
    uid = _make(app, 'blocked')
    victim = app.test_client()
    login(victim, 'blocked')
    assert victim.get('/api/auth/me').get_json().get('user')
    admin = _admin(app, login)
    r = admin.put(f'/api/admin/users/{uid}', json={'status': 'disabled'})
    assert r.get_json()['user']['status'] == 'disabled'
    me = victim.get('/api/auth/me').get_json()
    assert not me.get('user')                                                    # existing session is dead
    r = app.test_client().post('/api/auth/login', json={'login': 'blocked', 'password': PW})
    assert r.status_code == 403 and r.get_json()['code'] == 'account_disabled'
    admin.put(f'/api/admin/users/{uid}', json={'status': 'enabled'})
    r = app.test_client().post('/api/auth/login', json={'login': 'blocked', 'password': PW})
    assert r.status_code == 200


def test_enable_approves_a_pending_account(app, login):
    from app import db
    from app.models import User
    uid = _make(app, 'waiting')
    with app.app_context():
        db.session.get(User, uid).email_verified_at = None
        db.session.commit()
    admin = _admin(app, login)
    assert admin.get(f'/api/admin/users/{uid}').get_json()['user']['status'] == 'pending'
    assert admin.put(f'/api/admin/users/{uid}', json={'status': 'enabled'}).get_json()['user']['status'] == 'enabled'


def test_edit_fields_and_validation(app, login):
    uid = _make(app, 'editme')
    _make(app, 'taken')
    admin = _admin(app, login)
    r = admin.put(f'/api/admin/users/{uid}', json={'username': 'renamed', 'full_name': 'New Name',
                                                   'email': 'New@Example.com', 'language': 'es'})
    u = r.get_json()['user']
    assert (u['username'], u['full_name'], u['email'], u['language']) == ('renamed', 'New Name', 'new@example.com', 'es')
    assert admin.put(f'/api/admin/users/{uid}', json={'username': 'taken'}).status_code == 409
    assert admin.put(f'/api/admin/users/{uid}', json={'username': 'Admin'}).status_code == 400
    assert admin.put(f'/api/admin/users/{uid}', json={'email': 'taken@example.com'}).status_code == 409
    assert admin.put(f'/api/admin/users/{uid}', json={'email': 'nonsense'}).status_code == 400
    assert admin.put(f'/api/admin/users/{uid}', json={'status': 'bogus'}).status_code == 400


def test_set_password_but_never_read_it(app, login):
    uid = _make(app, 'pwuser')
    admin = _admin(app, login)
    assert admin.put(f'/api/admin/users/{uid}', json={'password': 'short'}).status_code == 400
    r = admin.put(f'/api/admin/users/{uid}', json={'password': 'brand new passphrase 99 zebra'})
    assert r.status_code == 200 and 'passphrase' not in r.get_data(as_text=True)
    ok = app.test_client().post('/api/auth/login', json={'login': 'pwuser', 'password': 'brand new passphrase 99 zebra'})
    old = app.test_client().post('/api/auth/login', json={'login': 'pwuser', 'password': PW})
    assert ok.status_code == 200 and old.status_code == 401


def test_the_admin_account_is_protected(app, login):
    from app.models import User
    admin = _admin(app, login)
    with app.app_context():
        aid = User.query.filter_by(username='admin').one().id
    assert admin.put(f'/api/admin/users/{aid}', json={'status': 'disabled'}).status_code == 400
    assert admin.put(f'/api/admin/users/{aid}', json={'username': 'boss'}).status_code == 400
    assert admin.delete(f'/api/admin/users/{aid}', json={}).status_code == 400
    assert admin.put(f'/api/admin/users/{aid}', json={'full_name': 'The Admin'}).status_code == 200


def test_delete_removes_the_user_and_their_content(app, login):
    from app.models import Squad, User
    uid = _make(app, 'doomed')
    doomed = app.test_client()
    login(doomed, 'doomed')
    r = doomed.post('/api/squads', json={'name': 'Doomed squad', 'mission_card_id': card_id(app, 'S-200'),
                                         'nation': 'US', 'status': 'draft',
                                         'soldiers': [{'card_id': card_id(app, 'S-001'), 'gear': []}]})
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    admin = _admin(app, login)
    assert admin.delete(f'/api/admin/users/{uid}', json={}).status_code == 200
    with app.app_context():
        assert User.query.filter_by(username='doomed').first() is None
        assert Squad.query.filter_by(user_id=uid).count() == 0
    assert admin.delete(f'/api/admin/users/{uid}', json={}).status_code == 404


def test_passwordless_owner_is_reserved(app, login):
    """Imported squad/campaign owners have no password: shown as 'reserved', cannot log in or be registered again;
    the admin giving them a password turns them into a normal account."""
    from app import db
    from app.models import User, now_utc
    with app.app_context():
        u = User(username='ImportedOwner', email='importedowner@community.local', password_hash=None,
                 email_verified_at=now_utc())
        db.session.add(u)
        db.session.commit()
        uid = u.id
    admin = _admin(app, login)
    assert admin.get(f'/api/admin/users/{uid}').get_json()['user']['status'] == 'reserved'
    anon = app.test_client()
    assert anon.post('/api/auth/login', json={'login': 'ImportedOwner', 'password': PW}).status_code == 401
    r = anon.post('/api/auth/register', json={'username': 'importedowner', 'email': 'x@example.com', 'password': PW})
    assert r.status_code == 409
    r = admin.put(f'/api/admin/users/{uid}', json={'password': PW, 'email': 'real@example.com'})
    assert r.get_json()['user']['status'] == 'enabled'
