"""Request language + card-text translation overlay.

English in `cards` is canonical. Translations live in `card_translations` and are
applied only when serialising cards for display (see spec/07_i18n.md).
"""
import json
import os
import unicodedata
from datetime import datetime, timezone

from flask import g, has_request_context, request
from flask_login import current_user

from app import db

SUPPORTED_LANGS = ('en', 'es')
DEFAULT_LANG = 'en'
CARD_FIELDS = ('name', 'notes')

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def now_precise():
    """UTC timestamp with microseconds — used as a cache signature for translations."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def normalize_lang(value):
    if not value:
        return None
    code = value.strip().lower().replace('_', '-').split('-')[0]
    return code if code in SUPPORTED_LANGS else None


def get_lang():
    """Language for the current request: ?lang → X-Lang header → user profile → Accept-Language → en."""
    if not has_request_context():
        return DEFAULT_LANG
    if 'lang' in g:
        return g.lang
    lang = (normalize_lang(request.args.get('lang'))
            or normalize_lang(request.headers.get('X-Lang')))
    if not lang and current_user.is_authenticated:
        lang = normalize_lang(current_user.language)
    if not lang and request.accept_languages:
        lang = normalize_lang(request.accept_languages.best_match(SUPPORTED_LANGS))
    g.lang = lang or DEFAULT_LANG
    return g.lang


def is_admin():
    return has_request_context() and current_user.is_authenticated and bool(current_user.is_admin)


# ---------------------------------------------------------------------------
# Card text overlay — whole language loaded once, cached per process,
# reloaded when the table changes (row count / last update differ).
# ---------------------------------------------------------------------------
_cache = {}  # lang -> (signature, {card_number: {field: (value, status, stale)}})


def invalidate_cache():
    _cache.clear()


def _card_texts(lang):
    if lang == DEFAULT_LANG:
        return {}
    if has_request_context() and g.get('_card_tr_lang') == lang:
        return g._card_tr
    sig = tuple(db.session.execute(
        db.text('SELECT COUNT(*), MAX(updated_at) FROM card_translations WHERE lang = :l'),
        {'l': lang},
    ).one())
    hit = _cache.get(lang)
    if not hit or hit[0] != sig:
        data = {}
        rows = db.session.execute(
            db.text('SELECT card_number, field, value, status, stale FROM card_translations WHERE lang = :l'),
            {'l': lang},
        )
        for number, field, value, status, stale in rows:
            data.setdefault(number, {})[field] = (value, status, bool(stale))
        hit = _cache[lang] = (sig, data)
    if has_request_context():
        g._card_tr_lang, g._card_tr = lang, hit[1]
    return hit[1]


def card_text(number, field, english):
    """Translated value of a card field for the request language, or the English value."""
    lang = get_lang()
    if lang == DEFAULT_LANG:
        return english
    row = _card_texts(lang).get(number, {}).get(field)
    return row[0] if row and row[0] else english


def card_status_for_admin(number):
    """'missing' | 'draft' | 'reviewed' for admins viewing a non-English language; None otherwise.
    A card is 'draft' if any of its rows is draft or stale."""
    lang = get_lang()
    if lang == DEFAULT_LANG or not is_admin():
        return None
    rows = _card_texts(lang).get(number)
    if not rows:
        return 'missing'
    if any(status != 'reviewed' or stale for (_, status, stale) in rows.values()):
        return 'draft'
    return 'reviewed'


# ---------------------------------------------------------------------------
# Accent-insensitive matching (registered as a SQLite function in create_app)
# ---------------------------------------------------------------------------
def fold(text):
    """Lower-case and strip accents: 'Hernández' → 'hernandez'."""
    if text is None:
        return None
    decomposed = unicodedata.normalize('NFKD', str(text))
    return ''.join(c for c in decomposed if not unicodedata.combining(c)).lower()


def register_sqlite_functions(dbapi_conn, _record):
    dbapi_conn.create_function('fold', 1, fold, deterministic=True)


# ---------------------------------------------------------------------------
# Server messages — English text is the key; catalogue in app/translations/<lang>.json
# ---------------------------------------------------------------------------
_messages = {}


def _catalogue(lang):
    if lang not in _messages:
        path = os.path.join(_BASE, 'app', 'translations', f'{lang}.json')
        try:
            with open(path, encoding='utf-8') as f:
                _messages[lang] = json.load(f)
        except FileNotFoundError:
            _messages[lang] = {}
    return _messages[lang]


def _(message, **params):
    """Translate a server message for the request language. Params use str.format names."""
    lang = get_lang()
    text = message if lang == DEFAULT_LANG else _catalogue(lang).get(message, message)
    return text.format(**params) if params else text


_ui = {}


def enum_label(ns, value):
    """Display label of an enum value (nation, card_type, …) from static/i18n/<lang>.json."""
    lang = get_lang()
    if not value or lang == DEFAULT_LANG:
        return value
    if lang not in _ui:
        path = os.path.join(_BASE, 'static', 'i18n', f'{lang}.json')
        try:
            with open(path, encoding='utf-8') as f:
                _ui[lang] = json.load(f)
        except FileNotFoundError:
            _ui[lang] = {}
    return _ui[lang].get(f'enum.{ns}.{value}', value)


def localize_validation(validation):
    """Re-render rules.py issue messages in the request language (in place)."""
    from app.rules import MESSAGES
    if get_lang() == DEFAULT_LANG:
        return validation
    for issue in validation.get('errors', []) + validation.get('warnings', []):
        params = dict(issue.get('params') or {})
        if 'nation' in params:
            params['nation'] = enum_label('nation', params['nation'])
        issue['message'] = _(MESSAGES[issue['code']], **params)
    return validation
