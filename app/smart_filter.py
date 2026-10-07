"""Smart card search syntax for /api/cards?q= (see spec/08_squad_tools.md §1).

    t:arma rp<5 n:us "x:hand to hand" l>=2 hardy
    t:skill|equipment   → OR inside one key
    t!=soldier          → negation (also n!=, x!=, …)
    plain words         → name or notes contain the word

Enum keys (t, s, n, m) match the stored English value or its label in the
request language, by substring, accent/case-insensitive.
"""
import re

from sqlalchemy import or_, not_, func, false

from app import db, i18n
from app.models import Card, CardTranslation

# key -> (kind, column attribute name / enum namespace)
KEYS = {
    't':    ('enum', 'card_type'),
    's':    ('enum', 'card_subtype'),
    'n':    ('enum', 'nation'),
    'm':    ('enum', 'module'),
    'x':    ('text', 'notes'),
    'name': ('text', 'name'),
    '#':    ('number', 'number'),
    'rp':   ('int', 'resource_cost'),
    'l':    ('int', 'loadout'),
    'h':    ('int', 'health'),
    'mv':   ('int', 'movement'),
    'cv':   ('int', 'cover'),
    'hth':  ('int', 'hth'),
    'a':    ('int', 'actions'),
    'cx':   ('int', 'cx'),
    'xp':   ('int', 'xp'),
    'b':    ('int', 'resources'),
    'tu':   ('int', 'time'),
}

TOKEN_RE = re.compile(
    r'(?:"([^"]*)"|(\S+))'  # quoted or bare token
)
COND_RE = re.compile(r'^([a-z]+|#)(!=|>=|<=|:|=|>|<)(.+)$', re.IGNORECASE)


def tokenize(q):
    for quoted, bare in TOKEN_RE.findall(q):
        tok = quoted if quoted else bare
        if tok:
            yield tok


def _text_cond(field, value, lang):
    like = f'%{i18n.fold(value)}%'
    col = getattr(Card, field)
    conds = [func.fold(col).like(like)]
    if lang != i18n.DEFAULT_LANG:
        conds.append(Card.number.in_(
            db.session.query(CardTranslation.card_number).filter(
                CardTranslation.lang == lang,
                CardTranslation.field == field,
                func.fold(CardTranslation.value).like(like),
            )))
    return or_(*conds)


def _free_text(value, lang):
    return or_(_text_cond('name', value, lang), _text_cond('notes', value, lang))


_enum_cache = {}


def _enum_values(attr):
    if attr not in _enum_cache:
        _enum_cache[attr] = [v for (v,) in db.session.query(getattr(Card, attr)).distinct() if v]
    return _enum_cache[attr]


def _enum_cond(attr, value):
    """Stored values whose code or translated label contains `value`."""
    needle = i18n.fold(value)
    matches = [v for v in _enum_values(attr)
               if needle in i18n.fold(v) or needle in i18n.fold(i18n.enum_label(attr, v) or '')]
    return getattr(Card, attr).in_(matches) if matches else None


def _int_cond(attr, op, value):
    try:
        n = int(value)
    except ValueError:
        return None
    col = getattr(Card, attr)
    return {':': col == n, '=': col == n, '!=': col != n, '>': col > n,
            '<': col < n, '>=': col >= n, '<=': col <= n}[op]


def apply(query, q, lang):
    """Return (query, errors). Unknown keys / bad values are reported, not fatal."""
    errors = []
    for tok in tokenize(q):
        if tok.startswith('#') and len(tok) > 1 and not COND_RE.match(tok):
            tok = '#:' + tok[1:]  # '#W-001' shorthand
        m = COND_RE.match(tok)
        if not m or m.group(1).lower() not in KEYS:
            query = query.filter(_free_text(tok, lang))
            continue
        key, op, raw = m.group(1).lower(), m.group(2), m.group(3)
        kind, attr = KEYS[key]
        negate = op == '!='
        if kind != 'int' and op not in (':', '=', '!='):
            errors.append({'token': tok, 'reason': 'operator'})
            continue
        conds = []
        for value in raw.split('|'):
            if kind == 'int':
                c = _int_cond(attr, op, value)
                negate = False  # != handled inside
            elif kind == 'enum':
                c = _enum_cond(attr, value)
            elif kind == 'number':
                c = Card.number.ilike(f'%{value}%')
            else:
                c = _text_cond(attr, value, lang)
            if c is None:
                errors.append({'token': tok, 'reason': 'value'})
            else:
                conds.append(c)
        if not conds and kind == 'int':
            continue  # unparseable number → ignore the token (reported in errors)
        if not conds:
            # Nothing matched the value (e.g. t:xyz) → no results rather than ignoring the filter
            if not negate:
                query = query.filter(false())
            continue
        cond = or_(*conds) if len(conds) > 1 else conds[0]
        if negate:
            cond = or_(not_(cond), getattr(Card, attr).is_(None))
        query = query.filter(cond)
    return query, errors
