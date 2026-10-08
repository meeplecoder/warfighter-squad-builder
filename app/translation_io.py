"""Import / export / staleness for card translations.

Shared by scripts/import_translations.py and the admin API. Import contract is
documented in spec/07_i18n.md §4.5.
"""
import hashlib

from app import db, i18n
from app.models import Card, CardTranslation

STATUSES = ('draft', 'reviewed')


def source_hash(text):
    return hashlib.sha1((text or '').encode('utf-8')).hexdigest()


def _english(card, field):
    return getattr(card, field)


def upsert(card, lang, field, value, status, user_id=None, overwrite_reviewed=True):
    """Insert/update one translation row. Empty value deletes the row.
    Returns 'inserted' | 'updated' | 'unchanged' | 'deleted' | 'kept_reviewed'."""
    row = CardTranslation.query.filter_by(card_number=card.number, lang=lang, field=field).first()
    value = (value or '').strip()
    if not value:
        if row:
            db.session.delete(row)
            return 'deleted'
        return 'unchanged'
    if row and row.status == 'reviewed' and not overwrite_reviewed:
        return 'kept_reviewed'
    h = source_hash(_english(card, field))
    if row and row.value == value and row.status == status and row.source_hash == h and not row.stale:
        return 'unchanged'
    result = 'updated' if row else 'inserted'
    if not row:
        row = CardTranslation(card_number=card.number, lang=lang, field=field)
        db.session.add(row)
    row.value = value
    row.status = status
    row.stale = 0
    row.source_hash = h
    row.updated_by = user_id
    row.updated_at = i18n.now_precise()
    return result


def import_entries(entries, overwrite_reviewed=False, dry_run=False, user_id=None):
    """entries: [{number, lang, field, value, status?}]. Returns a report dict."""
    report = {'inserted': 0, 'updated': 0, 'unchanged': 0, 'deleted': 0,
              'kept_reviewed': [], 'unknown_numbers': [], 'invalid': []}
    cards = {c.number: c for c in Card.catalog().all()}
    for i, e in enumerate(entries):
        number = (e.get('number') or '').strip()
        lang = i18n.normalize_lang(e.get('lang'))
        field = (e.get('field') or '').strip()
        status = (e.get('status') or 'reviewed').strip().lower()
        if not number or not lang or lang == i18n.DEFAULT_LANG or field not in i18n.CARD_FIELDS or status not in STATUSES:
            report['invalid'].append({'index': i, 'entry': e})
            continue
        card = cards.get(number)
        if not card:
            report['unknown_numbers'].append(number)
            continue
        res = upsert(card, lang, field, e.get('value'), status,
                     user_id=user_id, overwrite_reviewed=overwrite_reviewed)
        if res == 'kept_reviewed':
            report['kept_reviewed'].append(f'{number}/{field}')
        else:
            report[res] += 1
    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
        i18n.invalidate_cache()
    return report


def export_entries(lang, status=None):
    q = CardTranslation.query.filter_by(lang=lang)
    if status in STATUSES:
        q = q.filter_by(status=status)
    rows = q.order_by(CardTranslation.card_number, CardTranslation.field).all()
    return [{'number': r.card_number, 'lang': r.lang, 'field': r.field, 'value': r.value,
             'status': r.status, 'stale': bool(r.stale)} for r in rows]


def rehash():
    """Recompute staleness against the current English text.
    Rows with an empty source_hash (direct DB writes) are adopted as up to date.
    Returns {'stale': n, 'fresh': n, 'adopted': n, 'orphaned': [numbers]}."""
    cards = {c.number: c for c in Card.catalog().all()}
    out = {'stale': 0, 'fresh': 0, 'adopted': 0, 'orphaned': []}
    for row in CardTranslation.query.all():
        card = cards.get(row.card_number)
        if not card:
            out['orphaned'].append(row.card_number)
            continue
        h = source_hash(_english(card, row.field))
        if not row.source_hash:
            row.source_hash, row.stale = h, 0
            row.updated_at = i18n.now_precise()
            out['adopted'] += 1
        elif row.source_hash != h:
            if not row.stale:
                row.stale = 1
                row.updated_at = i18n.now_precise()
            out['stale'] += 1
        else:
            if row.stale:
                row.stale = 0
                row.updated_at = i18n.now_precise()
            out['fresh'] += 1
    db.session.commit()
    i18n.invalidate_cache()
    return out
