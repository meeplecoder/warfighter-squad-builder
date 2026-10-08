"""Card mentions in free text: [[W-001]] or [[Card name]] (English or translated name).

resolve() returns {raw_text: light card object} for every mention it can match;
the frontend turns them into card links. See spec/08_squad_tools.md §4.
"""
import re

from sqlalchemy import func

from app import i18n
from app.models import Card, CardTranslation

MENTION_RE = re.compile(r'\[\[([^\[\]\n]{1,80})\]\]')
MAX_MENTIONS = 50


def _find(raw):
    key = raw.strip()
    card = Card.catalog().filter_by(number=key).first()
    if card:
        return card
    folded = i18n.fold(key)
    card = Card.catalog().filter(func.fold(Card.name) == folded).order_by(Card.number).first()
    if card:
        return card
    row = (CardTranslation.query.filter(CardTranslation.field == 'name', func.fold(CardTranslation.value) == folded)
           .order_by(CardTranslation.card_number).first())
    return Card.catalog().filter_by(number=row.card_number).first() if row else None


def resolve(*texts):
    raws = []
    for text in texts:
        for raw in MENTION_RE.findall(text or ''):
            if raw not in raws:
                raws.append(raw)
    out = {}
    for raw in raws[:MAX_MENTIONS]:
        card = _find(raw)
        if card:
            obj = card.to_card_object()
            out[raw] = {k: obj[k] for k in ('id', 'number', 'name', 'card_type', 'image_url')}
    return out
