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
    """Derive objective victory mechanic from notes text.

    Returns one of: 'Eliminate Hostiles', 'Keep Clear', 'Destroy Target',
                    'Kill Specified Hostile', 'Escape', or '' (structural objective).

    Structural objectives (Fallback Position / Right Flank) are scenario components
    of Holding Action and Hold the Line missions and have no standard victory mechanic.
    """
    if not notes:
        return 'Eliminate Hostiles'

    text = notes.lower()

    # Structural scenario objectives — no standard victory mechanic
    if 'fallback position' in text or 'right flank' in text:
        return ''

    # Escape mechanic (escape back to mission card)
    if 'escape mission' in text:
        return 'Escape'

    # Kill Specified Hostile: named target capture / escort / delivery
    if re.search(r'capture the .{1,40}?: inflict', text):
        return 'Kill Specified Hostile'
    if re.search(r'\bdeliver\b.{0,50}\bthis objective\b', text):
        return 'Kill Specified Hostile'
    if re.search(r'protecting the (?:vip|fugitive|pilot|general|minister)\b', text):
        return 'Kill Specified Hostile'
    # "Find: Agent Z" type — exclude "Find: 2 RP of Grenades" (starts with digit)
    if re.search(r'find:\s*["\']?[^\d\s]', text):
        return 'Kill Specified Hostile'

    # Line-by-line scan for primary objective statement
    for line in notes.split('\n'):
        ll = line.strip().lower().rstrip('.')
        if not ll:
            continue
        if ll in _SKIP_LINES:
            continue
        if ll.startswith(('environ', 'hostiles', 'cold ', 'hot ', 'fever ', 'nature',
                           '+', 'add ', 'subtract ', 'always ', 'holding action mission',
                           'hold the line mission')):
            continue
        if re.match(r'\d+[-+]', ll):  # hostile table row
            break

        if ll.startswith('keep clear') or ll.startswith('at any time, have no hostiles'):
            return 'Keep Clear'
        if ll.startswith('destroy') or (ll.startswith('clear the ') and ':' in ll):
            return 'Destroy Target'
        if 'defuse' in ll or 'explosives (pick' in ll or 'pumps (pick' in ll:
            return 'Destroy Target'
        if ll.startswith('eliminate present'):
            return 'Kill Specified Hostile'
        if 'eliminate' in ll or 'eliminated' in ll:
            return 'Eliminate Hostiles'
        if 'have no hostiles in play' in ll or 'have no hostiles in this' in ll:
            return 'Eliminate Hostiles'

    return 'Eliminate Hostiles'


# Theater names that only appear in Airborne missions (→ Airborne objective family)
_AIRBORNE_ONLY_THEATERS = frozenset({'Tombola'})


def classify_objective_family(notes: str, raw_type: str, module: str) -> str:
    """Derive objective family from notes, raw_type, and module.

    Returns one of: 'Fallback', 'Right Flank', 'Shore', 'Fortification',
                    'Embedded', 'Airborne', or '' (Standard — no special family).
    """
    text = (notes or '').lower()
    r = (raw_type or '').strip()
    m = (module or '').lower()

    # Notes-based families
    if 'fallback position' in text:
        return 'Fallback'
    if 'right flank' in text:
        return 'Right Flank'

    # Raw-type based families
    if re.search(r'Shore Invasion', r, re.IGNORECASE):
        return 'Shore'
    if re.search(r'Embedded', r, re.IGNORECASE):
        return 'Embedded'

    # Module-based families
    if 'fortif' in m:
        return 'Fortification'

    # Theater-exclusively-Airborne families
    theater = theater_from_raw_type(r)
    if theater in _AIRBORNE_ONLY_THEATERS:
        return 'Airborne'

    return ''


def build_objective_subtype(mechanic: str, family: str) -> str:
    """Combine objective family and mechanic into the canonical card_subtype string.

    Examples:
      ('Eliminate Hostiles', '')        → 'Eliminate Hostiles'
      ('Eliminate Hostiles', 'Shore')   → 'Shore / Eliminate Hostiles'
      ('', 'Fallback')                  → 'Fallback'
      ('Kill Specified Hostile', 'Fortification') → 'Fortification / Kill Specified Hostile'
    """
    if family and mechanic:
        return f"{family} / {mechanic}"
    return family or mechanic or ''


def classify_mission_type(notes: str, raw_type: str = '') -> str:
    """Derive mission structure type from notes and raw_type.

    Notes-based types take precedence (they define the primary game mechanic).
    Returns one of: 'Raid', 'Holding Action', 'Hold the Line', 'Escape',
                    'Airborne', 'Shore Invasion', 'Standard'.
    """
    if notes:
        t = notes.lower()
        if 'raid mission' in t:
            return 'Raid'
        if 'holding action mission' in t:
            return 'Holding Action'
        if 'hold the line mission' in t:
            return 'Hold the Line'
        if 'escape mission' in t:
            return 'Escape'
    r = (raw_type or '').strip()
    if re.match(r'Airborne Mission', r, re.IGNORECASE):
        return 'Airborne'
    if re.match(r'Mission[-\s]Shore Invasion', r, re.IGNORECASE):
        return 'Shore Invasion'
    return 'Standard'


def theater_from_raw_type(raw_type: str) -> str:
    """Extract the theater/campaign label from a card's raw_type string.

    Objective examples:
      'Objective Europe'                → 'Europe'
      'Objective - Assault - Europe'    → 'Assault'
      'Objective-Shore Invasion Europe' → 'Shore Invasion'
      'Objective Embedded ...'          → 'Embedded'

    Mission examples:
      'Mission Europe'                  → 'Europe'
      'Mission Castle Frankestein'      → 'Castle Frankestein'
      'Airborne Mission Europe'         → 'Europe'
      'Mission-Shore Invasion Europe'   → 'Europe'
    """
    if not raw_type:
        return ''
    r = raw_type.strip()
    # Objective patterns
    if re.match(r'Objective\s*-\s*Assault', r, re.IGNORECASE):
        return 'Assault'
    if re.match(r'Objective Embedded', r, re.IGNORECASE):
        return 'Embedded'
    if re.match(r'Objective[-\s]Shore Invasion', r, re.IGNORECASE):
        return 'Shore Invasion'
    m = re.match(r'Objective\s+(.+)', r, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Mission patterns
    m = re.match(r'Airborne Mission\s+(.+)', r, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.match(r'Mission[-\s]Shore Invasion\s+(.+)', r, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.match(r'Mission\s+(.+)', r, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ''


# ---------------------------------------------------------------------------
# Hostile spawn table
# ---------------------------------------------------------------------------

def parse_hostile_spawn_table(notes: str) -> list | None:
    """Extract the Hostiles spawn table from card notes.

    Looks for a line containing only 'Hostiles' then reads subsequent
    lines of the form '<range> <count>' (e.g. '29-  4', '30-49  5', '125+  12').

    Returns a list of {'range': str, 'count': int} dicts, or None if not found.
    """
    if not notes:
        return None
    lines = notes.split('\n')
    rows = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped == 'Hostiles':
            in_table = True
            continue
        if not in_table:
            continue
        if not stripped:
            if rows:
                break
            continue
        # Match patterns: '29-', '30-49', '125+'  followed by whitespace and a digit
        m = re.match(r'^(\d+[-+]\d*)\s+(\d+)$', stripped)
        if m:
            rows.append({'range': m.group(1), 'count': int(m.group(2))})
        elif rows:
            break  # non-matching line after we've started = end of table
    return rows if rows else None


def strip_hostile_spawn_table(notes: str) -> str:
    """Remove the Hostiles spawn table block from notes text.

    Strips the 'Hostiles' header line and all following range-count rows,
    then cleans up extra blank lines left behind.
    Returns the cleaned notes string (or original if no table found).
    """
    if not notes or 'Hostiles' not in notes:
        return notes
    lines = notes.split('\n')
    result = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped == 'Hostiles':
            skip = True
            continue
        if skip:
            if re.match(r'^(\d+[-+]\d*)\s+(\d+)$', stripped) or (not stripped):
                continue  # drop table rows and blank lines inside the block
            else:
                skip = False  # non-table line resumes normal output
        result.append(line)
    cleaned = '\n'.join(result).strip()
    return cleaned or None


# ---------------------------------------------------------------------------
# Health/Actions table (NPS / Squad soldiers)
# ---------------------------------------------------------------------------

def parse_health_actions_table(notes: str) -> dict | None:
    """Extract health/actions table from NPS/Squad soldier card notes.

    Header line starts with 'Health' and contains 'Actions', optionally
    followed by Range columns (Range2, Range1, Range0).
    Data rows are all-integer lines with the same column count as the header.

    Returns {'headers': [...], 'rows': [[int, ...], ...]} or None.
    """
    if not notes:
        return None
    lines = notes.split('\n')
    header_idx = None
    headers = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r'Health', stripped, re.IGNORECASE) and 'Actions' in stripped:
            parts = [p for p in re.split(r'\s{2,}|\t', stripped) if p.strip()]
            headers = [p.strip() for p in parts]
            header_idx = i
            break
    if header_idx is None:
        return None
    rows = []
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = re.split(r'\s+', stripped)
        if len(parts) == len(headers) and all(re.match(r'^\d+$', p) for p in parts):
            rows.append([int(p) for p in parts])
        else:
            break
    return {'headers': headers, 'rows': rows} if rows else None


def strip_health_actions_table(notes: str) -> str | None:
    """Remove the health/actions table block from notes text.

    Removes the header line and all following all-integer rows,
    then strips extra blank lines. Returns cleaned string or None.
    """
    if not notes or 'Health' not in notes:
        return notes
    lines = notes.split('\n')
    result = []
    skip = False
    n_cols = 0
    for line in lines:
        stripped = line.strip()
        if not skip and re.match(r'Health', stripped, re.IGNORECASE) and 'Actions' in stripped:
            parts = [p for p in re.split(r'\s{2,}|\t', stripped) if p.strip()]
            n_cols = len(parts)
            skip = True
            continue
        if skip:
            if not stripped:
                continue
            parts = re.split(r'\s+', stripped)
            if len(parts) == n_cols and all(re.match(r'^\d+$', p) for p in parts):
                continue
            skip = False
        result.append(line)
    cleaned = '\n'.join(result).strip()
    return cleaned or None


# ---------------------------------------------------------------------------
# Hardy markers
# ---------------------------------------------------------------------------

_HARDY_RE = re.compile(
    r'^(\+?\d*)\s*Hardy\s*\((\w+)\)\.?$',
    re.IGNORECASE,
)


def parse_hardy_markers(notes: str) -> list | None:
    """Extract Hardy marker lines from soldier notes.

    Handles:
      '2 Hardy (Cold).'   → {'count': 2, 'type': 'Cold'}
      'Hardy (Hot).'      → {'count': 1, 'type': 'Hot'}
      '+4 Hardy (Hot).'   → {'count': 4, 'type': 'Hot', 'modifier': '+'}

    Returns a list of dicts, or None if none found.
    """
    if not notes or 'Hardy' not in notes:
        return None
    results = []
    for line in notes.split('\n'):
        m = _HARDY_RE.match(line.strip())
        if not m:
            continue
        raw_count, env_type = m.group(1), m.group(2)
        entry = {'type': env_type.capitalize()}
        if raw_count.startswith('+'):
            entry['count'] = int(raw_count[1:]) if raw_count[1:] else 1
            entry['modifier'] = '+'
        else:
            entry['count'] = int(raw_count) if raw_count else 1
        results.append(entry)
    return results if results else None


def strip_hardy_markers(notes: str) -> str | None:
    """Remove Hardy marker lines from notes text."""
    if not notes or 'Hardy' not in notes:
        return notes
    kept = [l for l in notes.split('\n') if not _HARDY_RE.match(l.strip())]
    cleaned = '\n'.join(kept).strip()
    return cleaned or None
