"""Shared utilities — nation normalization."""

import re

# Map from base nation name → prefix patterns used in DB
# Each entry means: when user filters by KEY, match card.nation values starting with VALUE.
_NATION_PREFIXES: dict[str, list[str]] = {
    'Australian': ['Australian'],
    'Austria': ['Austria'],
    'Canada': ['Canada'],
    'China': ['China'],
    'Commonwealth': ['Commonwealth'],
    'Finland': ['Finland'],
    'France': ['France', 'Free French', 'Vichy French'],
    'German': ['German'],
    'Greece': ['Greece'],
    'Italian': ['Italian'],
    'Japan': ['Japan'],
    'New Zealand': ['New Zealand'],
    'North Korean': ['North Korean'],
    'Norway': ['Norway'],
    'Poland': ['Poland', 'PO '],
    'Russian': ['Russian', 'RU '],
    'South Korean': ['South Korean'],
    'UK': ['UK'],
    'United Nations': ['United Nations'],
    'US': ['US ', 'USMC'],  # "US " prefix prevents false-matching; USMC is US Marines
}

# Reverse: raw nation string → canonical base nation
_RAW_TO_BASE: dict[str, str] = {}

def _build_reverse():
    for base, prefixes in _NATION_PREFIXES.items():
        for p in prefixes:
            # Key = stripped prefix (no trailing space used as sentinel)
            _RAW_TO_BASE[p.strip()] = base

_build_reverse()


def normalize_nation(raw: str) -> str:
    """Return the canonical base nation for any raw nation string from the DB."""
    if not raw:
        return raw
    # Try direct lookup
    if raw in _RAW_TO_BASE:
        return _RAW_TO_BASE[raw]
    # Try prefix match
    for base, prefixes in _NATION_PREFIXES.items():
        for p in prefixes:
            if raw.startswith(p):
                return base
    # Fallback: return first word
    return raw.split()[0]


def nation_filter_clause(nation_base: str, nation_col):
    """Return a SQLAlchemy OR filter clause matching all variants of a base nation.

    Parameters
    ----------
    nation_base : str
        The canonical base nation (as returned by normalize_nation or the /nations API).
    nation_col : SQLAlchemy column
        The column to filter on, e.g. Card.nation.

    Returns
    -------
    SQLAlchemy filter expression or None if nation_base is empty.
    """
    if not nation_base:
        return None
    from sqlalchemy import or_

    prefixes = _NATION_PREFIXES.get(nation_base)
    if not prefixes:
        # Unknown base — fall back to exact match
        return nation_col == nation_base

    clauses = []
    for p in prefixes:
        if p.endswith(' '):
            # Prefix sentinel (e.g. 'US ') — match exactly OR starts with prefix
            exact = p.strip()
            clauses.append(nation_col == exact)
            clauses.append(nation_col.startswith(p))
        else:
            # Match exact value OR "prefix + space + anything"
            clauses.append(nation_col == p)
            clauses.append(nation_col.startswith(p + ' '))

    return or_(*clauses)


# Objective type classification from notes text
_SKIP_LINES = frozenset({
    'structure', 'nature', 'elevated', 'isolated', 'on site',
    'collateral damage', 'close quarters combat', 'fallback position',
    'right flank', 'always reinforces', 'protected', 'fearless',
    'wire', 'inanimate',
})

def classify_objective_type(notes: str) -> str:
    """Derive objective mission type from notes text.
    Returns one of: 'Escape', 'Hold', 'Destroy', 'Rescue', 'Eliminate'.
    """
    if not notes:
        return 'Eliminate'

    text = notes.lower()

    # Escape Mission (highest priority)
    if 'escape mission' in text:
        return 'Escape'

    # Holding / Hold the Line missions
    if 'holding action mission' in text or 'hold the line mission' in text:
        return 'Hold'

    # Rescue: capture VIP via HtH
    if re.search(r'capture the .{1,40}?: inflict', text):
        return 'Rescue'
    # Rescue: deliver item/person to objective
    if re.search(r'\bdeliver\b.{0,50}\bthis objective\b', text):
        return 'Rescue'
    # Rescue: escort/protect a specific person
    if re.search(r'protecting the (?:vip|fugitive|pilot|general|minister)\b', text):
        return 'Rescue'
    # Rescue: find named item/person ("Find: Agent Z", "Find: 'Manuscript'")
    # Exclude "Find: 2 RP of Grenades" (gear rewards that start with a digit)
    if re.search(r'find:\s*["\']?[^\d\s]', text):
        return 'Rescue'

    # Line-by-line scan for primary objective
    for line in notes.split('\n'):
        ll = line.strip().lower().rstrip('.')
        if not ll:
            continue
        if ll in _SKIP_LINES:
            continue
        if ll.startswith(('environ', 'hostiles', 'cold ', 'hot ', 'fever ', '+', 'add ', 'subtract ', 'always ')):
            continue
        if re.match(r'\d+[-+]', ll):  # hostile table
            break

        if ll.startswith('keep clear'):
            return 'Hold'
        if ll.startswith('at any time, have no hostiles'):
            return 'Hold'
        if ll.startswith('destroy') or (ll.startswith('clear the ') and ':' in ll):
            return 'Destroy'
        if 'defuse' in ll or 'explosives (pick' in ll or 'pumps (pick' in ll:
            return 'Destroy'
        if 'eliminate' in ll or 'eliminated' in ll:
            return 'Eliminate'
        if 'have no hostiles in play' in ll or 'have no hostiles in this' in ll:
            return 'Eliminate'

    return 'Eliminate'


def theater_from_raw_type(raw_type: str) -> str:
    """Extract the theater/campaign label from an objective raw_type string.

    Examples:
      'Objective Europe'                → 'Europe'
      'Objective - Assault - Europe'    → 'Assault'
      'Objective-Shore Invasion Europe' → 'Shore Invasion'
      'Objective Embedded ...'          → 'Embedded'
    """
    if not raw_type:
        return ''
    r = raw_type.strip()
    if re.match(r'Objective\s*-\s*Assault', r, re.IGNORECASE):
        return 'Assault'
    if re.match(r'Objective Embedded', r, re.IGNORECASE):
        return 'Embedded'
    if re.match(r'Objective[-\s]Shore Invasion', r, re.IGNORECASE):
        return 'Shore Invasion'
    m = re.match(r'Objective\s+(.+)', r, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ''
