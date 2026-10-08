from datetime import datetime, timezone
from flask_login import UserMixin
from app import db
import json
from app.utils import classify_objective_type, classify_objective_family, theater_from_raw_type
from app import i18n


def now_utc():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


CUSTOM_MODULE = 'Custom'


class Card(db.Model):
    __tablename__ = 'cards'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    number = db.Column(db.Text, unique=True, nullable=False)
    name = db.Column(db.Text, nullable=False)
    raw_type = db.Column(db.Text, nullable=False)
    card_type = db.Column(db.Text, nullable=False, index=True)
    card_subtype = db.Column(db.Text)
    nation = db.Column(db.Text, index=True)
    module = db.Column(db.Text, nullable=False, index=True)
    notes = db.Column(db.Text)
    resource_cost = db.Column(db.Integer)
    movement = db.Column(db.Integer)
    cover = db.Column(db.Integer)
    health = db.Column(db.Integer)
    loadout = db.Column(db.Integer)
    hth = db.Column(db.Integer)
    actions = db.Column(db.Integer)
    entrance_cost = db.Column(db.Integer)
    resources = db.Column(db.Integer)
    time = db.Column(db.Integer)
    objective_position = db.Column(db.Integer)
    loadout_modifier = db.Column(db.Integer)
    reinforcements = db.Column(db.Text)
    xp_value = db.Column(db.Integer)
    hostile_count = db.Column(db.Text)
    noise = db.Column(db.Integer)
    action_cost_hth = db.Column(db.Integer)
    support_cost = db.Column(db.Integer)
    covert_cost = db.Column(db.Integer)
    gain = db.Column(db.Integer)
    loss = db.Column(db.Integer)
    objective_family = db.Column(db.Text)
    hostile_spawn_table = db.Column(db.Text)   # JSON: [{'range': str, 'count': int}]
    health_actions_table = db.Column(db.Text)  # JSON: {'headers': [...], 'rows': [[int,...],..]}
    hardy_markers = db.Column(db.Text)         # JSON: [{'type': str, 'count': int, 'modifier'?}]
    weapon_range_table = db.Column(db.Text)   # JSON: {'headers': [...], 'rows': [...]}
    weapon_mode_table = db.Column(db.Text)    # JSON: {'headers': [...], 'rows': [...]}
    vassal_module = db.Column(db.Text)
    has_image = db.Column(db.Integer, nullable=False, default=0)
    cx = db.Column('combat_xp', db.Integer, nullable=False, default=0)  # CX = Combat Experience (pre-printed)
    xp = db.Column('soldier_xp', db.Integer, nullable=False, default=0)  # XP = Experience Points (pre-printed)
    # Custom (user-made) cards — module CUSTOM_MODULE, number 'CM-<id>'. Excluded from the catalog.
    owner_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True)

    @classmethod
    def catalog(cls):
        """Printed cards only — every list/search/resolver uses this instead of Card.query."""
        return cls.query.filter(cls.module != CUSTOM_MODULE)

    def _objective_mechanic(self) -> str:
        """Extract mechanic from combined card_subtype, e.g. 'Shore / Eliminate Hostiles' → 'Eliminate Hostiles'."""
        family = self.objective_family or ''
        combined = self.card_subtype or ''
        if family and combined.startswith(family + ' / '):
            return combined[len(family) + 3:]
        if not family:
            return combined
        return ''  # structural (Fallback / Right Flank — no mechanic)

    def display_name(self):
        """Card name in the request language (falls back to English)."""
        return i18n.card_text(self.number, 'name', self.name)

    def to_card_object(self):
        prefix = self.number.split('-')[0]
        image_url = f'/api/cards/images/{prefix}/{self.number}.jpg' if self.has_image else None
        d = {
            'id': self.id,
            'number': self.number,
            'name': self.display_name(),
            'name_en': self.name,
            'card_type': self.card_type,
            'card_subtype': self.card_subtype,
            'nation': self.nation,
            'module': self.module,
            'resource_cost': self.resource_cost,
            'health': self.health,
            'loadout': self.loadout,
            'loadout_modifier': self.loadout_modifier,
            'movement': self.movement,
            'cover': self.cover,
            'hth': self.hth,
            'actions': self.actions,
            'resources': self.resources,
            'time': self.time,
            'objective_position': self.objective_position,
            'entrance_cost': self.entrance_cost,
            'action_cost_hth': self.action_cost_hth,
            'objective_family': self.objective_family,
            'image_url': image_url,
            'cx': self.cx or 0,
            'xp': self.xp or 0,
        }
        tr_status = i18n.card_status_for_admin(self.number)
        if tr_status is not None:
            d['translation_status'] = tr_status
        if self.card_type == 'Mission':
            d['mission_type'] = self.card_subtype
        elif self.card_type == 'Objective':
            d['objective_mechanic'] = self._objective_mechanic()
        return d

    def to_card_detail(self):
        d = self.to_card_object()
        if self.card_type == 'Objective':
            d['objective_mechanic'] = self._objective_mechanic()
            d['objective_family'] = self.objective_family or ''
            d['theater'] = theater_from_raw_type(self.raw_type or '')
        elif self.card_type == 'Mission':
            d['mission_type'] = self.card_subtype
            d['theater'] = theater_from_raw_type(self.raw_type or '')
        d.update({
            'notes': i18n.card_text(self.number, 'notes', self.notes),
            'notes_en': self.notes,
            'raw_type': self.raw_type,
            'loadout_modifier': self.loadout_modifier,
            'resources': self.resources,
            'time': self.time,
            'objective_position': self.objective_position,
            'entrance_cost': self.entrance_cost,
            'action_cost_hth': self.action_cost_hth,
            'reinforcements': self.reinforcements,
            'xp_value': self.xp_value,
            'hostile_count': self.hostile_count,
            'hostile_spawn_table': json.loads(self.hostile_spawn_table) if self.hostile_spawn_table else None,
            'health_actions_table': json.loads(self.health_actions_table) if self.health_actions_table else None,
            'hardy_markers': json.loads(self.hardy_markers) if self.hardy_markers else None,
            'weapon_range_table': json.loads(self.weapon_range_table) if self.weapon_range_table else None,
            'weapon_mode_table': json.loads(self.weapon_mode_table) if self.weapon_mode_table else None,
            'noise': self.noise,
            'support_cost': self.support_cost,
            'covert_cost': self.covert_cost,
            'gain': self.gain,
            'loss': self.loss,
            'vassal_module': self.vassal_module,
        })
        return d


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.Text, unique=True, nullable=False)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=True)
    full_name = db.Column(db.Text)
    avatar_url = db.Column(db.Text)
    created_at = db.Column(db.Text, nullable=False, default=now_utc)
    language = db.Column(db.Text)                                  # preferred UI language; NULL = browser default
    is_admin = db.Column(db.Integer, nullable=False, default=0)    # set manually; grants translation editor

    modules = db.relationship('UserModule', backref='user', cascade='all, delete-orphan')
    squads = db.relationship('Squad', foreign_keys='Squad.user_id', backref='owner', cascade='all, delete-orphan')
    likes = db.relationship('SquadLike', backref='user', cascade='all, delete-orphan')
    comments = db.relationship('SquadComment', backref='author', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'avatar_url': self.avatar_url,
            'created_at': self.created_at,
            'language': self.language,
            'is_admin': bool(self.is_admin),
        }


class UserModule(db.Model):
    __tablename__ = 'user_modules'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    module = db.Column(db.Text, nullable=False)
    owned = db.Column(db.Integer, nullable=False, default=1)

    __table_args__ = (db.UniqueConstraint('user_id', 'module'),)


class Squad(db.Model):
    __tablename__ = 'squads'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.Text, nullable=False)
    mission_card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    objective_card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=True)
    situation_card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=True)
    nation = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    rp_total = db.Column(db.Integer, nullable=False, default=0)
    is_valid = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.Text, nullable=False, default='draft')
    likes_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.Text, nullable=False, default=now_utc)
    updated_at = db.Column(db.Text, nullable=False, default=now_utc)
    parent_squad_id = db.Column(db.Integer, db.ForeignKey('squads.id', ondelete='SET NULL'))  # "based on"

    parent = db.relationship('Squad', remote_side=[id], foreign_keys=[parent_squad_id])
    mission_card = db.relationship('Card', foreign_keys=[mission_card_id])
    objective_card = db.relationship('Card', foreign_keys=[objective_card_id])
    situation_card = db.relationship('Card', foreign_keys=[situation_card_id])
    soldiers = db.relationship('SquadSoldier', backref='squad', cascade='all, delete-orphan', order_by='SquadSoldier.sort_order')
    objectives = db.relationship('SquadObjective', cascade='all, delete-orphan', order_by='SquadObjective.sort_order', foreign_keys='SquadObjective.squad_id')
    squad_likes = db.relationship('SquadLike', backref='squad', cascade='all, delete-orphan')
    squad_comments = db.relationship('SquadComment', backref='squad', cascade='all, delete-orphan')

    def to_summary(self, liked_by_me=False):
        return {
            'id': self.id,
            'name': self.name,
            'nation': self.nation,
            'rp_total': self.rp_total,
            'is_valid': bool(self.is_valid),
            'status': self.status,
            'likes_count': self.likes_count,
            'liked_by_me': liked_by_me,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'owner': {'id': self.owner.id, 'username': self.owner.username},
            'mission': {
                'id': self.mission_card.id,
                'name': self.mission_card.display_name(),
                'resources': self.mission_card.resources,
            },
            'objectives': [
                {'id': so.card.id, 'name': so.card.display_name()}
                for so in self.objectives
            ],
            'soldier_count': len(self.soldiers),
            'parent': self._parent_summary(),
        }

    def _parent_summary(self):
        """The squad this one was copied from, if it still exists and the viewer may see it."""
        p = self.parent
        if not p:
            return None
        from flask_login import current_user
        if p.status != 'published' and not (current_user.is_authenticated and current_user.id == p.user_id):
            return None
        return {'id': p.id, 'name': p.name, 'owner': {'id': p.owner.id, 'username': p.owner.username}}


class SquadSoldier(db.Model):
    __tablename__ = 'squad_soldiers'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squads.id', ondelete='CASCADE'), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    card = db.relationship('Card')
    gear = db.relationship('SquadGear', backref='soldier', cascade='all, delete-orphan')

    __table_args__ = (db.UniqueConstraint('squad_id', 'card_id'),)


class SquadGear(db.Model):
    __tablename__ = 'squad_gear'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    squad_soldier_id = db.Column(db.Integer, db.ForeignKey('squad_soldiers.id', ondelete='CASCADE'), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    card = db.relationship('Card')

    __table_args__ = (db.UniqueConstraint('squad_soldier_id', 'card_id'),)


class SquadObjective(db.Model):
    """Objectives selected for a squad — many-to-many via junction table."""
    __tablename__ = 'squad_objectives'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squads.id', ondelete='CASCADE'), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    card = db.relationship('Card')

    __table_args__ = (db.UniqueConstraint('squad_id', 'card_id'),)


class SquadLike(db.Model):
    __tablename__ = 'squad_likes'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squads.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.Text, nullable=False, default=now_utc)

    __table_args__ = (db.UniqueConstraint('squad_id', 'user_id'),)


class CardAssociation(db.Model):
    """Pre-printed gear/skills that a Soldier card includes by default.
    Populated by scripts/parse_associations.py; never written at runtime."""
    __tablename__ = 'card_associations'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    parent_card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False, index=True)
    child_card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    parent_card = db.relationship('Card', foreign_keys=[parent_card_id])
    child_card = db.relationship('Card', foreign_keys=[child_card_id])

    __table_args__ = (db.UniqueConstraint('parent_card_id', 'child_card_id'),)


class SquadComment(db.Model):
    __tablename__ = 'squad_comments'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squads.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.Text, nullable=False, default=now_utc)
    updated_at = db.Column(db.Text, nullable=False, default=now_utc)

    def to_dict(self):
        return {
            'id': self.id,
            'squad_id': self.squad_id,
            'body': self.body,
            'author': {'id': self.author.id, 'username': self.author.username},
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class CardTranslation(db.Model):
    """Translated card text (display only — English in `cards` stays canonical).
    Keyed by card number, which is stable across CSV re-imports. See spec/07_i18n.md."""
    __tablename__ = 'card_translations'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    card_number = db.Column(db.Text, nullable=False, index=True)
    lang = db.Column(db.Text, nullable=False)
    field = db.Column(db.Text, nullable=False)                     # 'name' | 'notes'
    value = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, default='draft')   # 'draft' | 'reviewed'
    stale = db.Column(db.Integer, nullable=False, default=0)       # English changed since translation
    source_hash = db.Column(db.Text, nullable=False, default='')   # sha1 of the English text translated
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    updated_at = db.Column(db.Text, nullable=False, default=i18n.now_precise)

    __table_args__ = (db.UniqueConstraint('card_number', 'lang', 'field'),)
