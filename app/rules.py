"""
Squad-building validation rules. No Flask imports — pure Python.
"""

GEAR_LOADOUT_CATEGORIES = {'Weapon', 'Equipment'}
SKILL_CATEGORIES = {'Skill'}
NO_LOADOUT_CATEGORIES = {'Skill', 'Service Record'}

PS_SUBTYPE = 'Player'
NPS_SUBTYPE = 'NPS'
SQUAD_SUBTYPE = 'Squad'
VEHICLE_SUBTYPE = 'Vehicle'

NON_BUDGET_SUBTYPES = {NPS_SUBTYPE, SQUAD_SUBTYPE, VEHICLE_SUBTYPE}


def gear_loadout_weight(gear_card):
    """Loadout weight of a single gear card."""
    if gear_card['card_category'] in NO_LOADOUT_CATEGORIES:
        return 0
    if gear_card.get('loadout') is not None:
        return gear_card['loadout']
    return gear_card.get('resource_cost') or 0


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
        errors.append({'code': 'NO_PLAYER_SOLDIER', 'message': 'At least one Player Soldier is required.'})

    # 2. Nation check on all soldier + gear cards
    for s in soldiers_data:
        c = s['card']
        c_nation = c.get('nation')
        if c_nation and c_nation != nation:
            errors.append({
                'code': 'NATION_MISMATCH',
                'message': f"{c['name']} is restricted to {c_nation} soldiers.",
            })
        for g in s['gear']:
            gc = g['card']
            gc_nation = gc.get('nation')
            if gc_nation and gc_nation != nation:
                errors.append({
                    'code': 'NATION_MISMATCH',
                    'message': f"{gc['name']} is restricted to {gc_nation} soldiers.",
                })

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
        errors.append({
            'code': 'OVER_BUDGET',
            'message': f'Squad costs {rp_total} RP but mission budget is {budget} RP.',
        })

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
                if g['card']['card_category'] in GEAR_LOADOUT_CATEGORIES
            )
            loadout_remaining = effective_loadout - gear_loadout_used
            if gear_loadout_used > effective_loadout:
                errors.append({
                    'code': 'OVER_LOADOUT',
                    'message': (
                        f"{card['name']} exceeds Loadout: "
                        f"carrying {gear_loadout_used}, max {effective_loadout}."
                    ),
                })

            # Duplicate skill names
            skill_names = []
            for g in s['gear']:
                if g['card']['card_category'] == 'Skill':
                    sname = g['card']['name']
                    if sname in skill_names:
                        errors.append({
                            'code': 'DUPLICATE_SKILL',
                            'message': f"{card['name']} already has {sname}.",
                        })
                    else:
                        skill_names.append(sname)

            # Specialist skill warning
            for g in s['gear']:
                if g['card'].get('card_subtype') == 'Specialist':
                    warnings.append({
                        'code': 'SPECIALIST_PREREQ',
                        'message': (
                            f"{g['card']['name']} has prerequisites. "
                            'Verify them in the card Notes.'
                        ),
                    })

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
            warnings.append({
                'code': 'LOW_SOLDIER_COUNT',
                'message': f"This mission's budget suggests using {recommended} Player Soldiers.",
            })

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
