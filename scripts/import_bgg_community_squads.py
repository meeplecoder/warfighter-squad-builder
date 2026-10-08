#!/usr/bin/env python3
"""
Import the mission squads from "Warfighter WW2 Scenarios and Campaigns" (BGG compilation,
campaigns_scenarios/Warfighter_WW2_Scenarios_and_Campaigns.pdf) as published community squads
owned by user 'PyroDoctor'.

Squads were hand-extracted from the document (its notation is too irregular to parse).
A squad is skipped if any user already has a squad with the same mission card and the
same set of soldier cards. Pre-printed gear/skills (card_associations) are not duplicated.

Run from warfighter-squad-builder/ directory:
    python scripts/import_bgg_community_squads.py [--dry-run]
"""
import os
import re
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app import rules
from app.models import Card, CardAssociation, Squad, SquadSoldier, SquadGear, SquadObjective, User

OWNER_USERNAME = 'PyroDoctor'
OWNER_EMAIL = 'pyrodoctor@community.local'
SOURCE = 'Source: "Warfighter WW2 Scenarios and Campaigns" (BGG compilation by PyroDoctor).'

# ---------------------------------------------------------------------------
# Squad data — (title, nation, mission, [objectives], note, [soldiers])
# soldier = (name, subtype hint P/N/S, [gear]) ; gear = "Name" or "2 Name"
# Generic names (Pistol, Helmet, Web Gear, Cold Weather) resolve per nation.
# ---------------------------------------------------------------------------
TRAINING_OBJ = ['Break Out', 'Tank Hunting', 'Rescue', 'Observation Post']
TRAINING_NOTE = 'Easy objective: Break Out. Hard: Tank Hunting, Rescue, Observation Post.'

SQUADS = [
    # --- American ---------------------------------------------------------
    ('American 1.1 Training — Just Another Day', 'US', 'Just Another Day', TRAINING_OBJ, TRAINING_NOTE, [
        ('McDougall', 'P', ['M1 Rifle', '2 Canteen', '2 Mk2 Grenade']),
        ('Scanlan', 'N', []), ('Taylor', 'S', [])]),
    ('American 1.2 Training — House to House', 'US', 'House to House', TRAINING_OBJ, TRAINING_NOTE, [
        ('McDougall', 'P', ['M1 Rifle', 'Canteen', 'Mk2 Grenade', 'Breaching Charge']),
        ('Kasinski', 'P', ['M1 Rifle', 'Canteen', 'Mk2 Grenade', 'Breaching Charge', 'Panic']),
        ('Scanlan', 'N', []), ('Taylor', 'S', [])]),
    ('American 1.3 Training — Country Stroll', 'US', 'Country Stroll', [], 'Objective: any.', [
        ('McDougall', 'P', ['M1 Rifle', '2 Canteen', 'Mk2 Grenade', 'M9 AT Rifle Grenade', 'M17 Rifle Grenade']),
        ('Kasinski', 'P', ['M1 Rifle', '2 Canteen', '2 Mk2 Grenade', 'Breaching Charge', 'Panic']),
        ('Scanlan', 'N', []), ('Allen', 'N', []), ('Roble', 'S', ['Panic']), ('Taylor', 'S', [])]),
    ('American 1.4 Training — Hard Slog', 'US', 'Hard Slog', [], 'Objective: any.', [
        ('McDougall', 'P', ['M1 Rifle', '2 Canteen', 'Mk2 Grenade', 'M9 AT Rifle Grenade', '2 M17 Rifle Grenade']),
        ('Kasinski', 'P', ['M1 Rifle', '2 Canteen', '3 Mk2 Grenade', 'Breaching Charge', 'Panic']),
        ('Scanlan', 'N', []), ('Allen', 'N', []), ('Roble', 'S', ['Panic']), ('Taylor', 'S', []), ('Smith', 'S', [])]),
    ('American 1.5 Training — Raid', 'US', 'Raid', [], 'Objective: any. Bailey carries 3 rockets.', [
        ('McDougall', 'P', ['M1 Rifle', '2 Canteen', 'Mk2 Grenade', 'Breaching Charge', 'Panic']),
        ('Kasinski', 'P', ['M1 Carbine', '2 Canteen', '2 Mk2 Grenade', 'Breaching Charge', 'Panic']),
        ('Bailey', 'P', ['M3 SMG', 'M1911 Pistol', 'M1A1 Rocket Launcher', 'Panic']),
        ('Scanlan', 'N', ['Panic']), ('Allen', 'N', ['Panic', 'Green']),
        ('Roble', 'S', ['Panic']), ('Smith', 'S', ['Panic'])]),
    ('American 1.6 Training — Limited Support', 'US', 'Limited Support', [],
     'Objective: any. Bailey: M3 SMG or M1911 Pistol, 3 rockets. Alternative: limit to 8 soldiers.', [
        ('McDougall', 'P', ['M1 Carbine', '2 Canteen', 'Mk2 Grenade', 'Breaching Charge', 'Panic']),
        ('Kasinski', 'P', ['M1 Carbine', 'Canteen', '2 Mk2 Grenade', 'Breaching Charge', 'Panic']),
        ('Bailey', 'P', ['M3 SMG', 'M1A1 Rocket Launcher', 'Panic']),
        ('Scanlan', 'N', ['Panic']), ('Allen', 'N', ['Panic']), ('Walsh', 'N', ['Panic']),
        ('Roble', 'S', ['Panic']), ('Taylor', 'S', []), ('Smith', 'S', ['Panic'])]),
    ('American 1.7 Training — Travel Light', 'US', 'Travel Light', [],
     'Objective: any. Hernandez carries 3 rockets. Alternative: limit to 8 soldiers.', [
        ('McDougall', 'P', ['M1 Carbine', 'Canteen', 'Mk2 Grenade', 'Panic', 'Rifleman']),
        ('Kasinski', 'P', ['M1 Carbine', 'Canteen', 'Mk2 Grenade', 'Panic']),
        ('Bailey', 'P', ['M3 SMG', '2 Canteen', '2 Mk2 Grenade', 'Panic', 'Leadership']),
        ('Hernandez', 'P', ['M1911 Pistol', 'M1A1 Rocket Launcher', 'Panic', 'Local Knowledge']),
        ('Scanlan', 'N', ['Panic']), ('Allen', 'N', ['Panic']), ('Pacheco', 'N', ['Panic']), ('Walsh', 'N', ['Panic']),
        ('Roble', 'S', ['Panic']), ('Taylor', 'S', []), ('Smith', 'S', ['Panic'])]),
    ('American 1.8 Training — Long Way', 'US', 'Long Way', [],
     'Objective: any. Alternative: limit to 8 soldiers.', [
        ('McDougall', 'P', ['M1 Carbine', 'Canteen', 'Mk2 Grenade']),
        ('Kasinski', 'P', ['M1 Carbine', 'Canteen', 'Mk2 Grenade', 'Panic', 'Rifleman']),
        ('Bailey', 'P', ['M3 SMG', '2 Canteen', '2 Mk2 Grenade']),
        ('Hernandez', 'P', ['M1911 Pistol', 'M1A1 Rocket Launcher']),
        ('Scanlan', 'N', ['Panic']), ('Allen', 'N', ['Panic']), ('Pacheco', 'N', ['Panic']), ('Walsh', 'N', ['Panic']),
        ('Roble', 'S', ['Panic']), ('Taylor', 'S', []), ('Smith', 'S', ['Panic'])]),
    ('American 2 — Just Another Day to Bust Bunkers', 'US', 'Just Another Day', ['Bunker Clearing'], '', [
        ('McDougall', 'P', ['M1 Carbine', 'Mk2 Grenade', 'Lucky', 'Focus', 'Spotter']),
        ('Stover', 'N', ['M1 Rifle', 'M1919 Tripod', 'Panic']),
        ('Smith', 'S', []), ('Brooks', 'S', ['Panic'])]),
    ('American 3 — Alpha Co 2nd Squad', 'US', 'Tank Support', ['Bridge Capture'], '', [
        ('McDougall', 'P', ['M1 Carbine', 'Mk2 Grenade', 'Panic']),
        ('Anderson', 'P', ['M1 Carbine', 'Mk2 Grenade', 'Lucky', 'Spotter']),
        ('Allen', 'N', ['M1 Carbine', 'Mk2 Grenade', 'Close Combat']),
        ('Smith', 'S', []), ('Taylor', 'S', ['Panic'])]),
    ('American 4 — Easy Air Drop with M1919 MG Weapon Team', 'US', 'Easy Duty', ['Air Drop'],
     'Practice with the big machine gun and tripod. Also plays well vs Elite Germans '
     '(Brooks sacrificing himself for vehicles with His Number Was Up).', [
        ('Kasinski', 'P', ['M1 SMG', 'Binoculars', '2 Canteen', 'Spotter', 'Loader']),
        ('Moore', 'N', ['M1919 Machine Gun', 'Machine Gunner', 'Panic']),
        ('Stover', 'N', ['M1919 Tripod', 'Panic']),
        ('Brooks', 'S', ['Panic', 'His Number Was Up'])]),
    ('American 5 — Easy Duty Supply Convoy', 'US', 'Easy Duty', ['Supply Convoy'], '', [
        ('Biggs', 'P', ['M2 Carbine', '2 Mk2 Grenade', '2 Canteen', 'Satchel Charge', 'Rifleman', 'Marksman']),
        ('Allen', 'N', ['M1 Carbine', 'Mk2 Grenade', 'Close Combat']),
        ('Smith', 'S', []), ('Taylor', 'S', ['Panic'])]),
    ('American 6 — Training Country Stroll', 'US', 'Quick Look', ['Base Under Siege'],
     'McDougall carries 1 extra Ammo.', [
        ('McDougall', 'P', ['M1 Rifle', 'Mk2 Grenade', 'Canteen', 'Rifleman', 'Panic']),
        ('Scanlan', 'N', ['M1918A2 Machine Gun', 'Entrenching Tool']),
        ('Allen', 'N', ['M1 Carbine', 'Mk2 Grenade', 'Close Combat']),
        ('Walsh', 'N', ['M1 Rifle', 'Corpsman', 'First Aid Kit', 'Green'])]),
    ('American 7 — Bridge Capture', 'US', 'Combat Sweep', ['Bridge Capture'], '', [
        ('Hernandez', 'P', ['M1 Carbine', 'Binoculars', '2 Mk2 Grenade', 'Guts', 'Marksman', 'Veteran']),
        ('Kasinski', 'P', ['M1 Rifle', '2 Mk2 Grenade', 'Corpsman', 'First Aid Kit', 'Rifleman']),
        ('Scanlan', 'N', ['M1918A2 Machine Gun', 'Entrenching Tool']),
        ('Roble', 'S', ['Loader']), ('Taylor', 'S', ['Panic'])]),
    ('American 8 — Bunker Clearing with the M1919 MG', 'US', 'Hard Slog', ['Bunker Clearing'], '', [
        ('Bailey', 'P', ['M1 Rifle', 'Corpsman', 'First Aid Kit']),
        ('Biggs', 'P', ['M1 Rifle', '2 Mk2 Grenade', 'Focus', 'Marksman', 'Rifleman']),
        ('Moore', 'N', ['M1919 Machine Gun', 'Machine Gunner', 'Panic']),
        ('Stover', 'N', ['M1 Rifle', 'M1919 Tripod', 'Panic']),
        ('Roble', 'S', ['Loader'])]),
    ('American 9 — Quick Bridge Capture with a Bunch of Rookies', 'US', 'Quick Look', ['Bridge Capture'], '', [
        ('Brown', 'P', ['M1 Rifle', 'Mk2 Grenade', 'Green']),
        ('Turner', 'N', ['M3 SMG']), ('Randall', 'N', ['M1 Rifle', 'His Number Was Up']),
        ('Owens', 'S', ['Spotter', 'Panic']), ('Taylor', 'S', ['Panic']), ('Smith', 'S', []),
        ('Aaker', 'S', ['His Number Was Up', 'Panic'])]),
    ('American 10 — Destroy the Half Track', 'US', 'Tank Support', ['Command Vehicle'],
     'Rockets and M1919 machine gun. Duncan carries 2 rockets.', [
        ('Duncan', 'P', ['M2 Carbine', 'M1A1 Rocket Launcher', 'Entrenching Tool', 'Canteen']),
        ('Moore', 'N', ['M1919 Machine Gun', 'Machine Gunner', 'Panic']),
        ('Stover', 'N', ['M1 Rifle', 'M1919 Tripod', 'Panic'])]),
    ('American 11 — Pegasus Bridge: Bridge Defenders', 'UK', 'Limited Support', ['Bridge Capture'],
     '17 turns, RP 125 (50 defenders / 75 relief), LO -3. Defenders start in the objective and cannot '
     'leave or evade; relief force must link up in time. Moore: Ammo Box holds 3 grenades, fuse, Bren ammo. '
     'Lee +1 XP. Lonsdale carries 2 PIAT rockets. Pairs with "Pegasus Bridge: Relief Force".', [
        ('Moore', 'P', ['Sten SMG', 'PIAT Rocket Launcher', 'Pistol', 'Helmet', 'Web Gear', 'Canteen',
                        'Binoculars', 'Ammo Box', '3 No.36 Mk1 Grenade']),
        ('Lee', 'N', ['Marksman']), ('Lonsdale', 'S', []), ('Adams', 'S', ['Panic']), ('Wright', 'S', []),
        ('Lewis', 'S', ['Loader', 'Panic']), ('Edwards', 'S', ['His Number Was Up', 'Panic']),
        ('Morris', 'S', ['Panic'])]),
    ('American 11 — Pegasus Bridge: Relief Force', 'UK', 'Limited Support', ['Bridge Capture'],
     'Relief force (75 RP) must reach the bridge objective within the time limit and link up with the '
     'defenders. Bagnold: Ammo Box holds 3 grenades, smoke, pistol ammo. Pairs with "Pegasus Bridge: Bridge Defenders".', [
        ('Bagnold', 'P', ['Web Gear', 'Canteen', 'Binoculars', 'Pistol', 'Helmet', 'Ammo Box',
                          '3 No.36 Mk1 Grenade', 'Smoke Grenade', 'Cross Training', 'Spotter', 'Green']),
        ('Fowler', 'P', ['Mk1 BREN Machine Gun', 'Pistol', 'Helmet', 'Machine Gunner', 'Panic']),
        ('Darling', 'N', ['No.4 Mk1 Scoped Rifle']), ('Dixon', 'N', ['No.2 Mk2 Flamethrower']),
        ('Campbell', 'N', ['No.4 Mk1 Rifle', 'First Aid Kit', 'Corpsman']),
        ('Ward', 'S', []), ('Yardley', 'S', ['Panic']), ('Burton', 'S', ['Panic'])]),
    ('American 12 — Russian Intel Mission', 'US', 'Enemy Territory', ['Retrieve Intel'], 'Region: Russia.', [
        ('McDougall', 'P', ['M1 SMG', 'Mk2 Grenade', 'Panic']),
        ('Bailey', 'P', ['M1 Carbine', 'M17 Rifle Grenade']),
        ('Donavan', 'N', ['M1 SMG', 'His Number Was Up']),
        ('Mitchell', 'S', ['Panic']), ('Nielsen', 'S', [])]),
    ('Operation Market Garden — US Paras 1st Squad', 'US', 'Limited Support', ['Bridge Capture'],
     '3-scenario campaign (Eindhoven → Nijmegen → Arnhem), 17 turns, RP 125, LO -3. Anderson +2 XP, '
     'BAR ammo (4 mags). Squads split into bridge defenders and relief force. XP carries over.', [
        ('Anderson', 'P', ['Spotter', 'Lucky', 'Binoculars', 'Mk2 Grenade', 'Helmet', 'Pistol',
                           'M1 Carbine', 'Loader']),
        ('Randall', 'N', []), ('Kerr', 'S', []), ('Scanlan', 'N', ['M1918A2 Machine Gun', 'Entrenching Tool']),
        ('Baker', 'N', []), ('Mitchell', 'S', []), ('Fielding', 'S', []), ('Orwell', 'S', [])]),
    ('Operation Market Garden — US Paras 2nd Squad', 'US', 'Limited Support', ['Bridge Capture'],
     '3-scenario campaign (Eindhoven → Nijmegen → Arnhem), 17 turns, RP 125, LO -3. McDougall carries '
     'MMG ammo. Squads split into bridge defenders and relief force. XP carries over.', [
        ('McDougall', 'P', ['M1 Carbine', 'Binoculars', 'Canteen', 'Helmet', 'Pistol', '2 Mk2 Grenade',
                            '2 M9 AT Rifle Grenade', 'Web Gear']),
        ('Stover', 'N', []), ('Moore', 'N', []), ('Roble', 'S', []), ('Owens', 'S', []), ('Smith', 'S', []),
        ('Taylor', 'S', []), ('Abbott', 'S', ['Panic'])]),
    # --- British ----------------------------------------------------------
    ('British 1 — Easy Duty Convoy Escort', 'UK', 'Easy Duty', ['Convoy Escort'], '', [
        ('Turner', 'P', ['Sten SMG', 'Corpsman']),
        ('Patel', 'P', ['No.4 Mk1 Rifle', 'Focus', 'Marksman']),
        ('Lee', 'N', ['Mk1 Machine Gun', 'Marksman'])]),
    ('British 2 — Village Fighting', 'UK', 'House to House', ['Observation Post'], '', [
        ('Turner', 'P', ['No.4 Mk1 Rifle', 'Rifleman']),
        ('Patel', 'P', ['No.4 Mk1 Rifle', 'No.36 Mk1 Grenade', 'Focus', 'Marksman']),
        ('Lee', 'N', ['Mk1 Machine Gun', 'Marksman'])]),
    ("British 3 — Turner's Next Convoy Escort with PIAT Rockets", 'UK', 'Country Stroll', ['Convoy Escort'], '', [
        ('Turner', 'P', ['No.4 Mk1 Rifle', 'Sten SMG', 'No.36 Mk1 Grenade', 'Corpsman', 'First Aid Kit']),
        ('Hastings', 'P', ['No.4 Mk1 Rifle', 'PIAT Rocket Launcher', 'Close Combat', 'Spotter']),
        ('Lee', 'N', ['Mk1 Machine Gun', 'Marksman']),
        ('Adams', 'S', ['Panic']), ('Lewis', 'S', ['Loader', 'Panic'])]),
    ('British 4 — City Combat', 'UK', 'City Combat', ['Command Vehicle'], 'Turner carries 1 extra Ammo.', [
        ('Turner', 'P', ['No.4 Mk1 Rifle', 'No.36 Mk1 Grenade', 'Bolt Action', 'Rifleman']),
        ('Patel', 'P', ['No.4 Mk1 Rifle', 'No.36 Mk1 Grenade', 'Bolt Action', 'Focus', 'Marksman']),
        ('Moore', 'P', ['M1 SMG', 'PIAT Rocket Launcher', 'No.36 Mk1 Grenade']),
        ('Hastings', 'P', ['M1 SMG', 'No.36 Mk1 Grenade', 'Smoke Grenade', 'Binoculars', 'Close Combat', 'Spotter']),
        ('Lee', 'N', ['Mk1 Machine Gun', 'Marksman']),
        ('Campbell', 'N', ['No.4 Mk1 Rifle', 'Corpsman', 'First Aid Kit']),
        ('Lewis', 'S', ['Loader', 'Panic'])]),
    # --- German -----------------------------------------------------------
    ('German 2 — Bridge Capture', 'German', 'Long Patrol', ['Bridge Capture'], 'Simon carries 2 extra Ammo counters.', [
        ('Meier', 'P', ['98k Rifle', 'Focus', 'Marksman', 'Panic']),
        ('Bittner', 'P', ['98k Rifle', 'Overland', 'Cross Training', 'Panic']),
        ('Wahl', 'P', ['MP 40 SMG', 'Corpsman', 'Guts']),
        ('Fink', 'N', ['MP 40 SMG', 'Model 24 Grenade']), ('Simon', 'N', ['MG 42 Machine Gun']),
        ('Cramm', 'N', ['StG 44 Rifle', 'Panzerwurfmine Grenade']),
        ('Otto', 'S', ['His Number Was Up']), ('Drossel', 'S', []), ('Richter', 'S', ['2 Model 24 Grenade', 'Panic'])]),
    ('German 3 — Get the Tank in Russia', 'German', 'City Fight', ['Enemy Tank'], 'Region: Russia.', [
        ('Meier', 'P', ['StG 44 Rifle', 'Model 24 Grenade', 'Focus', 'Marksman', 'Panic']),
        ('Dehmelt', 'P', ['Panzerschreck Rocket Launcher', 'Green']),
        ('Martin', 'N', ['MP 40 SMG', 'Model 24 Grenade']), ('Stein', 'N', ['98k Rifle', 'Panic']),
        ('Otto', 'S', ['His Number Was Up']), ('Schulz', 'S', ['Focus']), ('Richter', 'S', ['2 Model 24 Grenade', 'Panic'])]),
    ('German 4 — MG 42 Machine Gun Team', 'German', 'Hard Slog', ['Break Out'],
     'Werner ("Wehner" in the source) carries 1 extra Ammo.', [
        ('Werner', 'P', ['MG 42 Machine Gun', 'Machine Gunner']),
        ('Wahl', 'P', ['StG 44 Rifle', 'Model 24 Grenade', 'Binoculars', 'Corpsman', 'First Aid Kit', 'Guts']),
        ('Neumann', 'N', ['StG 44 Rifle', 'Smoke Grenade']), ('Noak', 'N', ['98k Rifle', 'Loader', 'Spotter']),
        ('Frank', 'S', [])]),
    ('German 5 — MG 42 Machine Gun Bridge Capture', 'German', 'Limited Support', ['Bridge Capture'],
     'Werner is "Wehner" in the source.', [
        ('Werner', 'P', ['98k Rifle', 'Bolt Action']),
        ('Wahl', 'P', ['MP 40 SMG', 'Corpsman', 'Guts']),
        ('Bittner', 'P', ['MG 42 Machine Gun', 'Cross Training', 'Overland', 'Panic']),
        ('Cramm', 'N', ['StG 44 Rifle', 'Panzerwurfmine Grenade']), ('Noak', 'N', ['98k Rifle', 'Loader', 'Spotter']),
        ('Drossel', 'S', []), ('Richter', 'S', ['2 Model 24 Grenade', 'Panic']), ('Fuchsberger', 'S', ['Overland', 'Loader'])]),
    ('German 6 — Battle for Bastogne', 'German', 'Priority Mission', ['Break Out'],
     'RP 125. Germans breaking into Bastogne vs Elite US 101st Airborne; mix Europe and Russia locations '
     'for winter. Winter clothing (2 cold markers each) and artillery support. Schmidt +1 CX. '
     'Build around the MG42 (Machine Gunner + Spotter + Loader) and keep a spare magazine.', [
        ('Schmidt', 'P', ['Hunter', 'Spotter', 'Web Gear', '2 Model 24 Grenade', 'Helmet', 'Pistol', 'Canteen',
                          'Binoculars', 'Panzerfaust Rocket Launcher', 'StG 44 Rifle']),
        ('Wulf', 'P', ['Machine Gunner', 'Leadership', 'Cross Training', 'Web Gear', '2 Model 24 Grenade', 'Helmet',
                       'Pistol', 'MG 42 Machine Gun', 'First Aid Kit']),
        ('Vogel', 'N', []), ('Kraus', 'N', []),
        ('Schulz', 'S', []), ('Fuchsberger', 'S', []), ('Vogt', 'S', [])]),
    ('German 7 — Operation Winter Storm: Relief Force', 'German', 'Raid', ['Encircled'],
     'Breakout Stalingrad, Jan 1943. Raid, 22 turns, RP 125 (80 relief / 45 defenders), LO -2, Russia. '
     'Encircled objective at location 7, then Escape. Relief force has cold weather clothing. '
     'Bittner: Ammo Box (2 grenades, 4 ammo). Dehmelt: Ammo Box (2 grenades, pistol ammo). Neumann +1 XP. '
     'Pairs with "Operation Winter Storm: Stalingrad Defenders".', [
        ('Bittner', 'P', ['Cross Training', 'Overland', 'Panic', 'Pistol', 'Helmet', 'MG 42 Machine Gun', 'Web Gear',
                          'Ammo Box', '2 Model 24 Grenade', 'Machine Gunner', 'Cold Weather']),
        ('Dehmelt', 'P', ['Green', 'Web Gear', 'Helmet', 'Pistol', 'Binoculars', 'Ammo Box', '2 Model 24 Grenade',
                          'Satchel Charge', 'Canteen', 'Panic', 'Cold Weather']),
        ('Fuchsberger', 'S', ['Overland', 'Loader']), ('Ohrloff', 'S', ['Spotter', 'Panic']),
        ('Vogel', 'N', ['98k Rifle', 'Breaching Charge', 'His Number Was Up', 'Panic', 'Green']),
        ('Neumann', 'N', ['StG 44 Rifle', 'Smoke Grenade', 'Green']),
        ('Classen', 'S', []), ('Winkler', 'S', ['His Number Was Up', 'Panic'])]),
    ('German 7 — Operation Winter Storm: Stalingrad Defenders', 'German', 'Raid', ['Encircled'],
     'Defenders (45 RP) hold the Encircled objective until the relief force links up, then escape together. '
     'Wahl: Ammo Box (3 grenades, 2 fuses, pistol ammo). Simon carries 2 ammo. '
     'Pairs with "Operation Winter Storm: Relief Force".', [
        ('Wahl', 'P', ['Corpsman', 'Guts', 'Ammo Box', '3 Model 24 Grenade', 'Canteen', 'Helmet', 'Pistol',
                       'First Aid Kit', 'Binoculars']),
        ('Simon', 'N', ['MG 42 Machine Gun']), ('Noak', 'N', ['Spotter', 'Loader', 'Green']), ('Frank', 'S', []),
        ('Richter', 'S', ['2 Model 24 Grenade', 'Panic']), ('Martin', 'N', ['MP 40 SMG', '3 Model 24 Grenade']),
        ('Drossel', 'S', []), ('Beckmann', 'S', [])]),
    ('German 8 — German vs Russian City Fight: Grenadiers', 'German', 'City Fight', ['Vital Factory'],
     'Stalingrad winter city fight, 13 turns, 6-location objective, no Nature locations. Grenade-heavy '
     'assault team; use the NPS/SqS for the heavy lifting. Braun wears great coats (1 Hardy each).', [
        ('Braun', 'P', ['Panic', '98k Rifle', '4 Model 24 Grenade', 'Canteen', 'Cold Weather', 'Breaching Charge']),
        ('Werner', 'P', ['Panic', '98k Rifle', '4 Model 24 Grenade', 'Canteen', 'Breaching Charge']),
        ('Martin', 'N', ['Panic']), ('Winkler', 'S', ['Panic']), ('Sommer', 'S', []), ('Ludwig', 'S', [])]),
    ('German 8 — German vs Russian City Fight: Pioneers', 'German', 'City Fight', ['Vital Factory'],
     'Alternative Pioneers team for the Stalingrad city fight (flamethrower). Braun wears great coats.', [
        ('Braun', 'P', ['Panic', '98k Rifle', '2 Model 24 Grenade', 'Canteen', 'Cold Weather']),
        ('Hoffman', 'P', ['Panic', 'Green', 'Flammenwerfer 41 Flamethrower', 'Pistol', 'Canteen']),
        ('Martin', 'N', ['Panic']), ('Winkler', 'S', ['Panic']), ('Sommer', 'S', []), ('Ludwig', 'S', [])]),
    # --- Russian ----------------------------------------------------------
    ('Russian 1 — Flamethrower Team', 'Russian', 'Wilderness Trek', ['Enemy Tank'], '', [
        ('Vatutin', 'P', ['SVT-40 Rifle', 'F1 Grenade', 'Binoculars', 'Close Combat', 'Marksman', 'Cold Weather']),
        ('Mikhalev', 'P', ['SVT-40 Rifle', 'F1 Grenade', 'Corpsman', 'First Aid Kit', 'Rifleman', 'Cold Weather']),
        ('Petrov', 'N', ['ROKS-3 Flamethrower', 'Zippo', 'Panic']), ('Chuikov', 'N', ['M1928 Machine Gun', 'Green']),
        ('Loladze', 'S', []), ('Litvyak', 'S', ['Loader'])]),
    ('Russian 2 — Vital Factory', 'Russian', 'City Fight', ['Vital Factory'], '', [
        ('Vatutin', 'P', ['SVT-40 Rifle', 'F1 Grenade', 'Close Combat', 'Marksman']),
        ('Mikhalev', 'P', ['SVT-40 Rifle', 'F1 Grenade', 'Rifleman', 'Local Knowledge']),
        ('Tupolev', 'P', ['PPSh-43 SMG', 'F1 Grenade', 'Pitcher', 'Hunter', 'Panic']),
        ('Isakov', 'N', ['PPSh-41 SMG', 'Marksman'])]),
    ('Russian 3 — Stalingrad Supply Run', 'Russian', 'Enemy Territory', ['Vital Factory'],
     'Supply run to the Tractor Plant in a snowstorm, vs German Elite. Fixed Location deck; roll Environment '
     'twice; all soldiers -2 Loadout and -1 Move; +5 RP, +3 turns. Win: clear hostiles and get 4 soldiers '
     'into the Vital Factory. Warm weather gear.', [
        ('Tupolev', 'P', ['Jitters', 'Panic', 'Web Gear', 'M1891/30 Rifle', '2 F1 Grenade']),
        ('Vatutin', 'P', ['Jitters', 'Panic', 'Web Gear', 'M1891/30 Rifle', 'Binoculars', 'Breaching Charge']),
        ('Petrov', 'N', ['Green']), ('Saburov', 'S', ['Panic']), ('Chuikov', 'N', ['Panic']),
        ('Litvyak', 'S', ['Panic'])]),
    # --- Polish -----------------------------------------------------------
    *[(f'Polish 1 — Warsaw will not Fall: Squad {n}', 'Poland', 'Hard Slog', [],
       'Warsaw 1939: three squads (one battle each) retake a bridge. Hard Slog, 11 turns, RP 125, LO 0, '
       '+2 hostiles in locations and objective; objective at location 5 drawn at random (not Escape, Rescue '
       f'or Base Under Siege). Battles affect each other through reinforcements. {extra}', soldiers)
      for n, extra, soldiers in [
        (1, 'Mazur: 2 ammo (8 mags). Ammo Boxes hold grenades/smoke/ammo. Zalewski +2 XP.', [
            ('Mazur', 'N', ['wz.1928 Machine Gun', 'Cavalry Horse']),
            ('Zielinski', 'P', ['Green', 'Pistol', 'wz.98a Rifle', 'Ammo Box', '3 wz.33 Grenade', 'Binoculars', 'Loader']),
            ('Wisniewski', 'P', ['Pistol', 'wz.98a Rifle', 'Ammo Box', '3 wz.33 Grenade', 'Smoke Grenade',
                                 'Breaching Charge', 'Leadership', 'Cross Training']),
            ('Drozdz', 'P', ['Pistol', 'wz.98a Rifle', 'Ammo Box', '3 wz.33 Grenade', 'Smoke Grenade',
                             'First Aid Kit', 'Lucky']),
            ('Adamczak', 'S', []), ('Flis', 'S', ['Spotter', 'His Number Was Up']),
            ('Ewy', 'S', ['Panic', '2 wz.33 Grenade']), ('Zalewski', 'N', ['wz.35 AT Rifle']),
            ('Zajac', 'N', ['wz.29 Rifle', 'Marksman'])]),
        (2, 'Ammo Boxes hold grenades/smoke/ammo. Tylutki +1 XP, Nowak +2 XP.', [
            ('Dabrowski', 'P', ['Pistol', 'wz.29 Rifle', 'Ammo Box', '3 wz.33 Grenade', 'Smoke Grenade',
                                'First Aid Kit', 'Cross Training', 'Loader']),
            ('Tylutki', 'P', ['Pistol', 'wz.29 Rifle', 'Ammo Box', '3 wz.33 Grenade', 'Smoke Grenade',
                              'Binoculars', 'Focus', 'Spotter']),
            ('Napiorkowski', 'P', ['Pistol', 'wz.1928 Machine Gun', 'Ammo Box', '2 wz.33 Grenade', 'Machine Gunner',
                                   'Marksman', 'Overland', 'Local Knowledge']),
            ('Mazurek', 'N', ['wz.35 AT Rifle', 'His Number Was Up', 'Panic']),
            ('Nowak', 'N', ['wz.98a Rifle', '2 wz.33 Grenade', 'Green']), ('Baran', 'N', ['wz.29 Rifle']),
            ('Jankowski', 'S', ['Panic']), ('Chlebek', 'S', []), ('Szymanski', 'S', [])]),
        (3, 'Lewandowski: 2 ammo (12 mags). Kaczkan: 3 ammo. Wojcik +3 XP, Bach +1 XP.', [
            ('Lewandowski', 'N', ['wz.29 Rifle', 'Bayonet', 'Cavalry Horse']),
            ('Wojcik', 'P', ['Pistol', 'wz.29 Rifle', 'Ammo Box', '3 wz.33 Grenade', 'Smoke Grenade',
                             'Binoculars', 'Loader']),
            ('Kaminski', 'P', ['Pistol', 'wz.98a Rifle', 'Ammo Box', '3 wz.33 Grenade', 'Smoke Grenade', 'Leadership']),
            ('Kaczkan', 'P', ['Pistol', 'wz.1928 Machine Gun', 'First Aid Kit', 'Breaching Charge', 'Cavalry Saber',
                              'Machine Gunner']),
            ('Wisniewski', 'N', ['wz.35 AT Rifle']), ('Bach', 'S', []), ('Janek', 'S', ['Spotter']),
            ('Galaska', 'S', ['His Number Was Up'])]),
      ]],
]

# Per-nation resolution of generic gear names
NATION_PREFIX = {'US': 'US', 'UK': 'UK', 'German': 'GE', 'Russian': 'RU', 'Poland': 'PO'}
NATION_PISTOL = {'US': 'M1911 Pistol', 'UK': 'Mk4 Pistol', 'German': 'P38 Pistol', 'Poland': 'wz.35 Pistol',
                 'Russian': 'TT-33 Pistol'}


def resolve_gear_name(name, nation):
    p = NATION_PREFIX.get(nation)
    if name == 'Pistol':
        return NATION_PISTOL[nation]
    if name in ('Helmet', 'Web Gear') and p:
        return f'{p}-Lucky Helmet' if name == 'Helmet' else f'{p}-Web Gear'
    if name == 'Cold Weather' and nation in ('German', 'Russian'):
        return f'{p}-Cold Weather'
    if name == 'Cavalry Horse' and nation == 'Poland':
        return 'PO-Cavalry Horse'
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        soldiers = {}
        for c in Card.query.filter_by(card_type='Soldier').all():
            soldiers.setdefault((c.name.lower(), c.nation), []).append(c)
        gear = {}
        for c in Card.query.filter(Card.card_type.in_(['Weapon', 'Equipment', 'Skill'])).all():
            gear.setdefault(c.name.lower(), []).append(c)
        missions = {}
        for c in Card.query.filter_by(card_type='Mission').order_by(Card.id).all():
            missions.setdefault(c.name.lower(), c)
        objectives = {}
        for c in Card.query.filter_by(card_type='Objective').order_by(Card.id).all():
            objectives.setdefault(c.name.lower(), c)

        def find_soldier(name, hint, nation):
            cands = soldiers.get((name.lower(), nation), [])
            sub = {'P': 'Player', 'N': 'NPS', 'S': 'Squad'}[hint]
            typed = [c for c in cands if c.card_subtype == sub]
            return (typed or cands or [None])[0]

        def find_gear(name, nation):
            cands = gear.get(resolve_gear_name(name, nation).lower(), [])
            pool = [c for c in cands if c.nation == nation] or [c for c in cands if not c.nation]
            pool.sort(key=lambda c: (c.module != 'Core Europe', c.id))
            return pool[0] if pool else None

        # Existing squads: (mission_card_id, frozenset(soldier ids)) → squad
        existing = {}
        for s in Squad.query.all():
            existing.setdefault((s.mission_card_id, frozenset(ss.card_id for ss in s.soldiers)), s)

        owner = User.query.filter_by(username=OWNER_USERNAME).first()
        if not owner:
            owner = User(username=OWNER_USERNAME, email=OWNER_EMAIL, password_hash=None, full_name='PyroDoctor')
            if not args.dry_run:
                db.session.add(owner)
                db.session.flush()
            print(f'Owner user created: {OWNER_USERNAME}')

        created = skipped = 0
        problems = []
        for title, nation, mission_name, obj_names, note, roster in SQUADS:
            mission = missions.get(mission_name.lower())
            if not mission:
                problems.append(f'{title}: mission not found {mission_name!r}')
                continue
            objs = []
            for on in obj_names:
                oc = objectives.get(on.lower())
                if oc:
                    objs.append(oc)
                else:
                    problems.append(f'{title}: objective not found {on!r}')

            entries = []
            for name, hint, items in roster:
                card = find_soldier(name, hint, nation)
                if not card:
                    problems.append(f'{title}: soldier not found {name!r} ({nation})')
                    continue
                preprinted = {a.child_card.name.lower() for a in
                              CardAssociation.query.filter_by(parent_card_id=card.id).all()}
                g_out = []
                for item in items:
                    m = re.match(r'^(\d+)\s+(.+)$', item)
                    qty, gname = (int(m.group(1)), m.group(2)) if m else (1, item)
                    gc = find_gear(gname, nation)
                    if not gc:
                        problems.append(f'{title}: gear not found {gname!r} for {name}')
                        continue
                    if gc.name.lower() in preprinted:
                        continue
                    g_out.append((gc, qty))
                entries.append((card, g_out))

            key = (mission.id, frozenset(c.id for c, _ in entries))
            if key in existing:
                ex = existing[key]
                print(f'  EXISTS  {title}  →  #{ex.id} {ex.name!r} ({ex.owner.username})')
                skipped += 1
                continue

            soldiers_data = [{'card': c.to_card_detail(),
                              'gear': [{'card': gc.to_card_detail(), 'quantity': q} for gc, q in g]}
                             for c, g in entries]
            v = rules.validate_squad({'nation': nation}, mission.to_card_detail(), soldiers_data)
            flags = '' if v['valid'] else '  [invalid: ' + '; '.join(e['message'] for e in v['errors']) + ']'
            print(f'  CREATE  {title}  ({mission.name}, {v["computed"]["rp_total"]} RP, '
                  f'{len(entries)} soldiers){flags}')

            if not args.dry_run:
                squad = Squad(user_id=owner.id, name=title, mission_card_id=mission.id, nation=nation,
                              notes=' '.join(x for x in (note, SOURCE) if x),
                              rp_total=v['computed']['rp_total'], is_valid=1 if v['valid'] else 0,
                              status='published')
                db.session.add(squad)
                db.session.flush()
                for i, oc in enumerate(objs):
                    db.session.add(SquadObjective(squad_id=squad.id, card_id=oc.id, sort_order=i))
                for i, (card, g) in enumerate(entries):
                    ss = SquadSoldier(squad_id=squad.id, card_id=card.id, sort_order=i)
                    db.session.add(ss)
                    db.session.flush()
                    for gc, q in g:
                        db.session.add(SquadGear(squad_soldier_id=ss.id, card_id=gc.id, quantity=q))
                existing[key] = squad
            created += 1

        if not args.dry_run:
            db.session.commit()
        print(f'\n{"DRY RUN — " if args.dry_run else ""}created {created}, already existing {skipped}')
        for p in problems:
            print('  PROBLEM', p)


if __name__ == '__main__':
    main()
