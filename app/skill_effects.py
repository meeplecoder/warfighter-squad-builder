"""
Curated effects of the skills and equipment the metrics understand (spec 12 / TODO A2).

Only effects that change the numbers the metrics compute are listed — attack and Defeat Cover bonuses,
extra dice, Movement, Actions, XP, Health and the Hostile's Defeat Cover roll. Everything else (skills that
need a decision during play, Upgun [brackets], Screening, XP payments …) is ignored on purpose.
Skill / equipment names are the English card names.
"""
import re

# bonus targets: 'ranged' | 'rifle' | 'smg' | 'pistol' | 'thrown' | 'indirect' | 'rocket' | 'satchel' |
#                'range0' (any attack at Range 0) | 'all'
SKILL_EFFECTS = {
    'Marksman':      {'hit': {'ranged': 1}},
    'Rifleman':      {'hit': {'rifle': 1}},
    'Gunman':        {'hit': {'smg': 1}},
    'Pistol & SMG':  {'hit': {'smg': 1, 'pistol': 2}},
    'Pitcher':       {'hit': {'thrown': 1}},
    'Ballistics':    {'hit': {'indirect': 1}},
    'Rocketeer':     {'hit': {'rocket': 2}},
    'Close Combat':  {'hit': {'range0': 1}},
    'Shooter':       {'cover': {'ranged': 1}},
    'Zeroed':        {'hit': {'all': 1}, 'cover': {'all': 1}},
    'Hose':          {'auto_dice': 1},                       # one extra die on Auto attacks
    'Demolitions':   {'satchel_dice': 1, 'cover': {'satchel': 1}},
    'Knife Fighter': {'hth': 1},
    'Striker':       {'hth': 1},
    'Agile':         {'move': 1},
    'Leadership':    {'squad_move': 1},                      # +1 Movement to every soldier (limit 1 per mission)
    'Squad Leader':  {'support_move': 2},                    # +2 Movement to NPS / Squad Soldiers (limit 1)
    'Veteran':       {'actions': 1, 'xp': 2},
    'Spotter':       {'spotter': 1},                         # +1 to another soldier's ranged attack rolls
    'Survivor':      {'hostile_cover': -1},                  # the Hostile's Defeat Cover roll is 1 lower
}

# Equipment by name; a name ending in the key also matches ("US-Lucky Helmet")
EQUIPMENT_EFFECTS = {
    'Body Armor':   {'hp_mult': 1.6},    # 7+ on a roll stops a Wound (≈ 40 %) → 1 / 0.6 effective Health
    'Lucky Helmet': {'hp_add': 1},       # expend once: one Attack has no effect
}

# limit-1-per-mission skills: only the first copy counts for the squad
SQUAD_WIDE_ONCE = ('Leadership', 'Squad Leader')

_ZERO = {'auto_dice': 0, 'satchel_dice': 0, 'hth': 0, 'move': 0, 'squad_move': 0, 'support_move': 0,
         'actions': 0, 'xp': 0, 'spotter': 0, 'hostile_cover': 0, 'hp_add': 0}


def weapon_tags(w):
    """Which skill targets a parsed metrics.Weapon matches."""
    n = (w.name or '').lower()
    sub = (w.subtype or '').lower()
    tags = set()
    if 'thrown' in sub:
        tags.add('thrown')
    elif 'indirect' in sub:
        tags.add('indirect')
    elif not w.melee:
        tags.add('ranged')
    if 'smg' in n or 'submachine' in n:
        tags.add('smg')
    if 'pistol' in n or 'revolver' in n:
        tags.add('pistol')
    if re.search(r'rifle|carbine', n) and not re.search(r'grenade|anti-tank|\bat\b', n):
        tags.add('rifle')
    if 'rocket' in n or 'panzerfaust' in n or 'bazooka' in n:
        tags.add('rocket')
    if 'satchel' in n:
        tags.add('satchel')
    return tags


def soldier_mods(skill_names, equipment_names):
    """Merge the effects of one soldier's skills and equipment into a single dict."""
    mods = {'hit': {}, 'cover': {}, 'hp_mult': 1.0, **_ZERO}
    for name in skill_names:
        eff = SKILL_EFFECTS.get(name)
        if not eff:
            continue
        for key, val in eff.items():
            if key in ('hit', 'cover'):
                for tag, n in val.items():
                    mods[key][tag] = mods[key].get(tag, 0) + n
            else:
                mods[key] += val
    for name in equipment_names:
        for key, eff in EQUIPMENT_EFFECTS.items():
            if name == key or name.endswith('-' + key) or name.endswith(' ' + key):
                for k, v in eff.items():
                    if k == 'hp_mult':
                        mods['hp_mult'] *= v
                    else:
                        mods[k] += v
    return mods


def bonuses(mods, tags, rng):
    """(attack-roll bonus, Defeat Cover bonus) of a soldier for a weapon with `tags` used at range `rng`."""
    hit = cover = 0
    for tag in set(tags) | {'all'} | ({'range0'} if rng == 0 else set()):
        hit += mods['hit'].get(tag, 0)
        cover += mods['cover'].get(tag, 0)
    return hit, cover
