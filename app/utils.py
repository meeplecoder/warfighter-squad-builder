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
    'US': ['US '],          # "US " prefix prevents matching "USMC"
    'USMC': ['USMC'],
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
