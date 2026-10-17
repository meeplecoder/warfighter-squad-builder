"""
Squad-building validation rules. No Flask imports — pure Python.
"""

from app.utils import normalize_nation

GEAR_LOADOUT_CATEGORIES = {'Weapon', 'Equipment'}
SKILL_CATEGORIES = {'Skill'}
NO_LOADOUT_CATEGORIES = {'Skill', 'Service Record'}

PS_SUBTYPE = 'Player'
NPS_SUBTYPE = 'NPS'
SQUAD_SUBTYPE = 'Squad'
VEHICLE_SUBTYPE = 'Vehicle'

NON_BUDGET_SUBTYPES = {NPS_SUBTYPE, SQUAD_SUBTYPE, VEHICLE_SUBTYPE}

# Message templates by code (English). Params are also returned so callers can localise
# (squads.py → i18n.localize_validation). `nation` params are raw enum values.
MESSAGES = {
    'NO_PLAYER_SOLDIER': 'At least one Player Soldier is required.',
    'NATION_MISMATCH': '{name} is restricted to {nation} soldiers.',
    'OVER_BUDGET': 'Squad costs {rp_total} RP but mission budget is {budget} RP.',
    'OVER_LOADOUT': '{name} exceeds Loadout: carrying {used}, max {max}.',
    'DUPLICATE_SKILL': '{name} already has {skill}.',
    'SPECIALIST_PREREQ': '{name} has prerequisites. Verify them in the card Notes.',
    'LOW_SOLDIER_COUNT': "This mission's budget suggests using {recommended} Player Soldiers.",
}


def _issue(code, **params):
    return {'code': code, 'params': params, 'message': MESSAGES[code].format(**params)}


def gear_loadout_weight(gear_card):
    """Loadout weight of a single gear card."""
    if gear_card['card_type'] in NO_LOADOUT_CATEGORIES:
        return 0
    return gear_card.get('loadout') or 0


def validate_squad(payload, mission_card, soldiers_data):
    """
    payload: dict with name, nation, etc.
    mission_card: Card dict (to_card_detail result)
    soldiers_data: list of dicts:
        {card: Card dict, subtype: str, gear: [{card: Card dict, quantity: int}]}
    Returns {valid, errors, warnings, computed}
    """
    errors = []
    warnings = []
    nation = payload.get('nation', '')
    lm = mission_card.get('loadout_modifier') or 0
    budget = mission_card.get('resources') or 0

    # 1. At least one Player Soldier
    ps_soldiers = [s for s in soldiers_data if s['card'].get('card_subtype') == PS_SUBTYPE]
    if not ps_soldiers:
        errors.append(_issue('NO_PLAYER_SOLDIER'))

    # 2. Nation check on all soldier + gear cards. The squad nation is a base nation
    # (e.g. 'US') and cards may carry a variant of it ('US Airborne', 'USMC'), so compare
    # on the normalized base — the same grouping the card picker uses.
    squad_base = normalize_nation(nation)
    for s in soldiers_data:
        c = s['card']
        c_nation = c.get('nation')
        if c_nation and normalize_nation(c_nation) != squad_base:
            errors.append(_issue('NATION_MISMATCH', name=c['name'], nation=c_nation))
        for g in s['gear']:
            gc = g['card']
            gc_nation = gc.get('nation')
            if gc_nation and normalize_nation(gc_nation) != squad_base:
                errors.append(_issue('NATION_MISMATCH', name=gc['name'], nation=gc_nation))

    # 3. RP budget (PS soldiers + PS gear only)
    rp_total = 0
    for s in soldiers_data:
        rc = s['card'].get('resource_cost') or 0
        rp_total += rc
        subtype = s['card'].get('card_subtype')
        if subtype == PS_SUBTYPE:
            for g in s['gear']:
                rp_total += (g['card'].get('resource_cost') or 0) * g['quantity']

    if budget and rp_total > budget:
        warnings.append(_issue('OVER_BUDGET', rp_total=rp_total, budget=budget))   # allowed: shown, never blocks

    # 4. Loadout per PS + duplicate skills
    soldier_computed = []
    for s in soldiers_data:
        card = s['card']
        subtype = card.get('card_subtype')

        if subtype == PS_SUBTYPE:
            base_loadout = card.get('loadout') or 0
            effective_loadout = base_loadout + lm
            gear_loadout_used = sum(
                gear_loadout_weight(g['card']) * g['quantity']
                for g in s['gear']
                if g['card']['card_type'] in GEAR_LOADOUT_CATEGORIES
            )
            loadout_remaining = effective_loadout - gear_loadout_used
            if gear_loadout_used > effective_loadout:
                warnings.append(_issue('OVER_LOADOUT', name=card['name'],       # allowed: shown, never blocks
                                       used=gear_loadout_used, max=effective_loadout))

            # Duplicate skill names (compared on the canonical English name)
            skill_names = []
            for g in s['gear']:
                if g['card']['card_type'] == 'Skill':
                    sname = g['card'].get('name_en') or g['card']['name']
                    if sname in skill_names or g['quantity'] > 1:
                        errors.append(_issue('DUPLICATE_SKILL', name=card['name'], skill=g['card']['name']))
                    else:
                        skill_names.append(sname)

            # Specialist skill warning
            for g in s['gear']:
                if g['card'].get('card_subtype') == 'Specialist':
                    warnings.append(_issue('SPECIALIST_PREREQ', name=g['card']['name']))

            soldier_computed.append({
                'card_id': card['id'],
                'name': card['name'],
                'effective_loadout': effective_loadout,
                'gear_loadout_used': gear_loadout_used,
                'loadout_remaining': loadout_remaining,
            })
        else:
            soldier_computed.append({
                'card_id': card['id'],
                'name': card['name'],
                'effective_loadout': None,
                'gear_loadout_used': None,
                'loadout_remaining': None,
            })

    # 5. Soldier count recommendation
    if budget:
        recommended = 1 if budget < 40 else (2 if budget < 80 else (3 if budget < 120 else 4))
        actual_ps = len(ps_soldiers)
        if actual_ps < recommended:
            warnings.append(_issue('LOW_SOLDIER_COUNT', recommended=recommended))

    rp_remaining = budget - rp_total if budget else None

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'computed': {
            'rp_total': rp_total,
            'rp_remaining': rp_remaining,
            'budget': budget,
            'soldiers': soldier_computed,
        },
    }
