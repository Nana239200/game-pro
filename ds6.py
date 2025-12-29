"""
GameEnginePro - RPG Demo Game
لعبة RPG تجريبية كاملة
"""

import pygame
import sys
import math
import random
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum, auto
from dataclasses import dataclass, field
import json
from pathlib import Path

# استيراد محرك الألعاب
from engine.core import GameEngine, Event, EventType, EventBus, Logger
from engine.core import Entity, EntityManager, ComponentType
from engine.math import Vector2, Vector3, Matrix4, Transform
from engine.renderer import RenderSystem, Camera, Material, Mesh
from engine.physics import PhysicsSystem, RigidBody, CollisionShape, ShapeType
from engine.ai import AISystem, AIAgent, AIBehavior
from engine.audio import AudioSystem, AudioType
from engine.network import NetworkSystem, NetworkRole

# ============================================================================
# Game Enums
# ============================================================================

class GameState(Enum):
    """حالات اللعبة"""
    MAIN_MENU = auto()
    CHARACTER_SELECTION = auto()
    PLAYING = auto()
    PAUSED = auto()
    INVENTORY = auto()
    DIALOGUE = auto()
    COMBAT = auto()
    GAME_OVER = auto()

class CharacterClass(Enum):
    """فئات الشخصيات"""
    WARRIOR = "محارب"
    MAGE = "ساحر"
    ARCHER = "رامي"
    ROGUE = "لص"

class ItemType(Enum):
    """أنواع العناصر"""
    WEAPON = "سلاح"
    ARMOR = "درع"
    POTION = "جرعة"
    SCROLL = "درج"
    KEY = "مفتاح"
    TREASURE = "كنز"
    MATERIAL = "مادة"

class QuestState(Enum):
    """حالات المهام"""
    AVAILABLE = auto()
    ACTIVE = auto()
    COMPLETED = auto()
    FAILED = auto()

# ============================================================================
# Game Data Classes
# ============================================================================

@dataclass
class CharacterStats:
    """إحصائيات الشخصية"""
    strength: int = 10
    dexterity: int = 10
    intelligence: int = 10
    constitution: int = 10
    wisdom: int = 10
    charisma: int = 10
    
    # المشتقات
    @property
    def max_health(self):
        return 50 + (self.constitution * 5) + (self.strength * 2)
    
    @property
    def max_mana(self):
        return 30 + (self.intelligence * 4) + (self.wisdom * 3)
    
    @property
    def physical_attack(self):
        return self.strength + (self.dexterity // 2)
    
    @property
    def magical_attack(self):
        return self.intelligence + (self.wisdom // 2)
    
    @property
    def defense(self):
        return (self.constitution // 2) + (self.dexterity // 4)

@dataclass
class Item:
    """عنصر في اللعبة"""
    id: str
    name: str
    item_type: ItemType
    description: str
    value: int
    weight: float
    stats: Dict[str, Any] = field(default_factory=dict)
    requirements: Dict[str, int] = field(default_factory=dict)
    effects: List[Dict[str, Any]] = field(default_factory=list)
    
    def can_use(self, character) -> bool:
        """التحقق من إمكانية استخدام العنصر"""
        for stat, value in self.requirements.items():
            if getattr(character.stats, stat, 0) < value:
                return False
        return True

@dataclass
class Inventory:
    """مخزن الشخصية"""
    items: List[Item] = field(default_factory=list)
    max_weight: float = 100.0
    gold: int = 0
    
    @property
    def current_weight(self) -> float:
        return sum(item.weight for item in self.items)
    
    @property
    def is_full(self) -> bool:
        return self.current_weight >= self.max_weight
    
    def add_item(self, item: Item) -> bool:
        """إضافة عنصر"""
        if self.current_weight + item.weight <= self.max_weight:
            self.items.append(item)
            return True
        return False
    
    def remove_item(self, item_id: str) -> Optional[Item]:
        """إزالة عنصر"""
        for i, item in enumerate(self.items):
            if item.id == item_id:
                return self.items.pop(i)
        return None
    
    def has_item(self, item_id: str) -> bool:
        """التحقق من وجود عنصر"""
        return any(item.id == item_id for item in self.items)

@dataclass
class Quest:
    """مهمة في اللعبة"""
    id: str
    title: str
    description: str
    giver: str  # اسم الشخص الذي أعطى المهمة
    objectives: List[Dict[str, Any]] = field(default_factory=list)
    rewards: Dict[str, Any] = field(default_factory=dict)
    state: QuestState = QuestState.AVAILABLE
    progress: Dict[str, int] = field(default_factory=dict)
    
    def update_progress(self, objective_type: str, amount: int = 1):
        """تحديث تقدم المهمة"""
        if objective_type in self.progress:
            self.progress[objective_type] += amount
        else:
            self.progress[objective_type] = amount
        
        self._check_completion()
    
    def _check_completion(self):
        """التحقق من اكتمال المهمة"""
        for objective in self.objectives:
            obj_type = objective['type']
            target = objective['target']
            
            if self.progress.get(obj_type, 0) < target:
                return
        
        self.state = QuestState.COMPLETED
    
    def get_rewards(self, character):
        """منح مكافآت المهمة"""
        if 'gold' in self.rewards:
            character.inventory.gold += self.rewards['gold']
        
        if 'items' in self.rewards:
            for item_id in self.rewards['items']:
                # البحث عن العنصر وإضافته
                pass
        
        if 'experience' in self.rewards:
            character.add_experience(self.rewards['experience'])

@dataclass
class DialogueNode:
    """عقدة حوار"""
    id: str
    text: str
    responses: List[Dict[str, Any]] = field(default_factory=list)
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    
    def is_available(self, character) -> bool:
        """التحقق من توفر خيار الحوار"""
        for condition in self.conditions:
            cond_type = condition['type']
            
            if cond_type == 'quest_state':
                # التحقق من حالة المهمة
                pass
            elif cond_type == 'has_item':
                # التحقق من وجود عنصر
                pass
            elif cond_type == 'stat_check':
                # التحقق من الإحصائيات
                pass
        
        return True

# ============================================================================
# Player Character
# ============================================================================

class PlayerCharacter:
    """شخصية اللاعب"""
    
    def __init__(self, name: str, character_class: CharacterClass):
        self.name = name
        self.character_class = character_class
        self.level = 1
        self.experience = 0
        self.experience_to_next = 100
        
        # الإحصائيات
        self.stats = CharacterStats()
        self._apply_class_bonuses()
        
        # الحالة
        self.health = self.stats.max_health
        self.mana = self.stats.max_mana
        self.stamina = 100
        
        # المعدات
        self.equipment = {
            'weapon': None,
            'shield': None,
            'helmet': None,
            'chest': None,
            'gloves': None,
            'boots': None,
            'accessory1': None,
            'accessory2': None
        }
        
        # المخزن
        self.inventory = Inventory()
        
        # المهارات
        self.skills = []
        self.abilities = []
        
        # المهام
        self.active_quests: List[Quest] = []
        self.completed_quests: List[Quest] = []
        
        # المكان
        self.location = "start_village"
        self.world_position = Vector3(0, 0, 0)
        
        # الكيان المرتبط
        self.entity_id = None
    
    def _apply_class_bonuses(self):
        """تطبيق مكافآت الفئة"""
        bonuses = {
            CharacterClass.WARRIOR: {'strength': 4, 'constitution': 3, 'dexterity': 1},
            CharacterClass.MAGE: {'intelligence': 4, 'wisdom': 3, 'constitution': 1},
            CharacterClass.ARCHER: {'dexterity': 4, 'strength': 2, 'wisdom': 2},
            CharacterClass.ROGUE: {'dexterity': 4, 'charisma': 3, 'intelligence': 1}
        }
        
        class_bonus = bonuses.get(self.character_class, {})
        for stat, bonus in class_bonus.items():
            setattr(self.stats, stat, getattr(self.stats, stat) + bonus)
    
    def add_experience(self, amount: int):
        """إضافة خبرة"""
        self.experience += amount
        
        while self.experience >= self.experience_to_next:
            self.level_up()
    
    def level_up(self):
        """ارتقاء مستوى"""
        self.level += 1
        self.experience -= self.experience_to_next
        self.experience_to_next = int(self.experience_to_next * 1.5)
        
        # زيادة الإحصائيات
        stat_increase = {
            'strength': 2 if self.character_class == CharacterClass.WARRIOR else 1,
            'dexterity': 2 if self.character_class in [CharacterClass.ARCHER, CharacterClass.ROGUE] else 1,
            'intelligence': 2 if self.character_class == CharacterClass.MAGE else 1,
            'constitution': 2,
            'wisdom': 1,
            'charisma': 1
        }
        
        for stat, increase in stat_increase.items():
            setattr(self.stats, stat, getattr(self.stats, stat) + increase)
        
        # استعادة الصحة والمانا
        self.health = self.stats.max_health
        self.mana = self.stats.max_mana
        
        # تعلم مهارة جديدة كل 5 مستويات
        if self.level % 5 == 0:
            self._learn_new_ability()
    
    def _learn_new_ability(self):
        """تعلم قدرة جديدة"""
        # سيتم تنفيذها بناءً على فئة الشخصية
        pass
    
    def equip_item(self, item: Item) -> bool:
        """تجهيز عنصر"""
        if item.item_type == ItemType.WEAPON:
            self.equipment['weapon'] = item
            return True
        elif item.item_type == ItemType.ARMOR:
            # تحديد نوع الدرع
            armor_type = item.stats.get('armor_type', 'chest')
            if armor_type in self.equipment:
                self.equipment[armor_type] = item
                return True
        return False
    
    def unequip_item(self, slot: str) -> Optional[Item]:
        """إزالة تجهيز عنصر"""
        item = self.equipment.get(slot)
        if item:
            self.equipment[slot] = None
            return item
        return None
    
    def calculate_damage(self) -> Tuple[int, str]:
        """حساب الضرر"""
        base_damage = self.stats.physical_attack
        damage_type = "physical"
        
        if self.equipment['weapon']:
            weapon = self.equipment['weapon']
            base_damage += weapon.stats.get('damage', 0)
            damage_type = weapon.stats.get('damage_type', 'physical')
        
        # حساب الضرر النهائي
        damage = base_damage
        
        # تطبيق المضاعفات من المهارات
        for skill in self.skills:
            if skill.get('type') == 'damage_boost':
                damage = int(damage * (1 + skill.get('value', 0) / 100))
        
        return damage, damage_type
    
    def calculate_defense(self) -> int:
        """حساب الدفاع"""
        base_defense = self.stats.defense
        
        # إضافة دفاع المعدات
        for slot, item in self.equipment.items():
            if item and hasattr(item, 'stats'):
                base_defense += item.stats.get('defense', 0)
        
        return base_defense
    
    def take_damage(self, damage: int, damage_type: str = "physical") -> int:
        """تلقّي ضرر"""
        defense = self.calculate_defense()
        
        # تقليل الضرر بالدفاع
        mitigated_damage = max(1, damage - defense // 2)
        
        self.health -= mitigated_damage
        
        if self.health <= 0:
            self.health = 0
            # حدث الموت
        
        return mitigated_damage
    
    def heal(self, amount: int):
        """علاج"""
        self.health = min(self.stats.max_health, self.health + amount)
    
    def restore_mana(self, amount: int):
        """استعادة مانا"""
        self.mana = min(self.stats.max_mana, self.mana + amount)
    
    def use_item(self, item: Item) -> bool:
        """استخدام عنصر"""
        if not item.can_use(self):
            return False
        
        if item.item_type == ItemType.POTION:
            # تطبيق تأثير الجرعة
            for effect in item.effects:
                effect_type = effect.get('type')
                value = effect.get('value')
                
                if effect_type == 'heal':
                    self.heal(value)
                elif effect_type == 'restore_mana':
                    self.restore_mana(value)
                elif effect_type == 'buff':
                    # تطبيق تأثير مؤقت
                    pass
            
            return True
        
        return False
    
    def get_status(self) -> Dict[str, Any]:
        """الحصول على حالة الشخصية"""
        return {
            'name': self.name,
            'class': self.character_class.value,
            'level': self.level,
            'experience': f"{self.experience}/{self.experience_to_next}",
            'health': f"{self.health}/{self.stats.max_health}",
            'mana': f"{self.mana}/{self.stats.max_mana}",
            'stats': {
                'strength': self.stats.strength,
                'dexterity': self.stats.dexterity,
                'intelligence': self.stats.intelligence,
                'constitution': self.stats.constitution,
                'wisdom': self.stats.wisdom,
                'charisma': self.stats.charisma
            },
            'damage': self.calculate_damage()[0],
            'defense': self.calculate_defense(),
            'gold': self.inventory.gold,
            'weight': f"{self.inventory.current_weight:.1f}/{self.inventory.max_weight:.1f}",
            'location': self.location
        }

# ============================================================================
# Game World
# ============================================================================

class GameWorld:
    """عالم اللعبة"""
    
    def __init__(self):
        self.regions = {}
        self.locations = {}
        self.npcs = {}
        self.enemies = {}
        self.quests = {}
        self.items = {}
        
        # التحميل
        self._load_game_data()
    
    def _load_game_data(self):
        """تحميل بيانات اللعبة"""
        # تحميل المناطق
        self.regions = {
            'greenwood': {
                'name': 'الغابة الخضراء',
                'description': 'غابة خصبة مليئة بالحياة والأسرار.',
                'level_range': (1, 10),
                'locations': ['start_village', 'elf_camp', 'ancient_ruins']
            },
            'mountains': {
                'name': 'جبال الظل',
                'description': 'سلسلة جبال وعرة يسكنها مخلوقات خطيرة.',
                'level_range': (10, 20),
                'locations': ['dwarf_fortress', 'dragon_lair', 'crystal_caves']
            },
            'desert': {
                'name': 'صحراء النار',
                'description': 'صحراء حارقة تخفي كنوزاً قديمة.',
                'level_range': (20, 30),
                'locations': ['oasis', 'pyramid', 'lost_city']
            }
        }
        
        # تحميل المواقع
        self.locations = {
            'start_village': {
                'name': 'قرية البداية',
                'description': 'قرية هادئة حيث تبدأ مغامرتك.',
                'region': 'greenwood',
                'type': 'village',
                'npcs': ['elder', 'blacksmith', 'merchant', 'quest_giver'],
                'shops': ['blacksmith', 'general_store', 'tavern'],
                'connections': ['elf_camp', 'ancient_ruins']
            },
            'elf_camp': {
                'name': 'معسكر الإلف',
                'description': 'معسكر مخفي لقبيلة الإلف في الغابة.',
                'region': 'greenwood',
                'type': 'camp',
                'npcs': ['elf_leader', 'elf_archer', 'elf_healer'],
                'shops': ['elf_merchant'],
                'connections': ['start_village', 'ancient_ruins']
            }
        }
        
        # تحميل NPCs
        self.npcs = {
            'elder': {
                'name': 'شيخ القرية',
                'description': 'شيخ حكيم يقود قرية البداية.',
                'location': 'start_village',
                'type': 'quest_giver',
                'dialogue': 'elder_dialogue',
                'quests': ['first_quest', 'goblin_problem']
            },
            'blacksmith': {
                'name': 'الحداد',
                'description': 'حداد ماهر يصنع أفضل الأسلحة والدروع.',
                'location': 'start_village',
                'type': 'shopkeeper',
                'shop': 'blacksmith',
                'dialogue': 'blacksmith_dialogue'
            }
        }
        
        # تحميل الأعداء
        self.enemies = {
            'goblin': {
                'name': 'قوبلين',
                'level': 2,
                'health': 30,
                'damage': (5, 8),
                'defense': 3,
                'experience': 25,
                'gold': (5, 15),
                'loot': ['goblin_ear', 'rusty_dagger', 'small_potion'],
                'spawn_locations': ['ancient_ruins', 'forest_path']
            },
            'wolf': {
                'name': 'ذئب',
                'level': 3,
                'health': 40,
                'damage': (6, 10),
                'defense': 2,
                'experience': 35,
                'gold': (2, 8),
                'loot': ['wolf_pelt', 'wolf_fang'],
                'spawn_locations': ['greenwood']
            }
        }
        
        # تحميل العناصر
        self.items = {
            'rusty_sword': Item(
                id='rusty_sword',
                name='سيف صدئ',
                item_type=ItemType.WEAPON,
                description='سيف قديم ومغطى بالصدأ، لكنه لا يزال حاداً.',
                value=15,
                weight=3.0,
                stats={'damage': 8, 'damage_type': 'physical'}
            ),
            'leather_armor': Item(
                id='leather_armor',
                name='درع جلدى',
                item_type=ItemType.ARMOR,
                description='درع مصنوع من الجلد المتين.',
                value=25,
                weight=5.0,
                stats={'defense': 6, 'armor_type': 'chest'}
            ),
            'health_potion': Item(
                id='health_potion',
                name='جرعة صحية',
                item_type=ItemType.POTION,
                description='جرعة حمراء تعيد بعض الصحة.',
                value=10,
                weight=0.5,
                effects=[{'type': 'heal', 'value': 30}]
            )
        }
        
        # تحميل المهام
        self.quests = {
            'first_quest': Quest(
                id='first_quest',
                title='المهمة الأولى',
                description='ساعد شيخ القرية في جمع 5 أعشاب طبية.',
                giver='elder',
                objectives=[
                    {'type': 'collect', 'target': 5, 'item': 'medicinal_herb'}
                ],
                rewards={
                    'gold': 100,
                    'experience': 150,
                    'items': ['rusty_sword']
                }
            ),
            'goblin_problem': Quest(
                id='goblin_problem',
                title='مشكلة القوبلين',
                description='اقتل 10 قوبلين في الأطلال القديمة.',
                giver='elder',
                objectives=[
                    {'type': 'kill', 'target': 10, 'enemy': 'goblin'}
                ],
                rewards={
                    'gold': 250,
                    'experience': 300,
                    'items': ['leather_armor']
                }
            )
        }
    
    def get_location(self, location_id: str) -> Optional[Dict[str, Any]]:
        """الحصول على موقع"""
        return self.locations.get(location_id)
    
    def get_npc(self, npc_id: str) -> Optional[Dict[str, Any]]:
        """الحصول على NPC"""
        return self.npcs.get(npc_id)
    
    def get_enemy(self, enemy_id: str) -> Optional[Dict[str, Any]]:
        """الحصول على عدو"""
        return self.enemies.get(enemy_id)
    
    def get_item(self, item_id: str) -> Optional[Item]:
        """الحصول على عنصر"""
        return self.items.get(item_id)
    
    def get_quest(self, quest_id: str) -> Optional[Quest]:
        """الحصول على مهمة"""
        return self.quests.get(quest_id)
    
    def get_random_enemy(self, location_id: str) -> Optional[Dict[str, Any]]:
        """الحصول على عدو عشوائي للموقع"""
        location = self.get_location(location_id)
        if not location:
            return None
        
        # البحث عن أعداء يمكنهم الظهور في هذا الموقع
        available_enemies = []
        for enemy_id, enemy_data in self.enemies.items():
            if location_id in enemy_data.get('spawn_locations', []):
                available_enemies.append(enemy_data)
        
        if available_enemies:
            return random.choice(available_enemies)
        
        return None

# ============================================================================
# RPG Game Class
# ============================================================================

class RPGGame:
    """فئة اللعبة RPG الرئيسية"""
    
    def __init__(self):
        # المحرك
        self.engine = GameEngine()
        self.world = GameWorld()
        
        # حالة اللعبة
        self.state = GameState.MAIN_MENU
        self.player = None
        self.party: List[PlayerCharacter] = []
        
        # الأنظمة
        self.render_system = None
        self.physics_system = None
        self.ai_system = None
        self.audio_system = None
        self.network_system = None
        
        # واجهة المستخدم
        self.ui_manager = None
        self.current_menu = None
        
        # اللعبة
        self.current_location = None
        self.current_npc = None
        self.current_dialogue = None
        self.combat_encounter = None
        
        # الوقت
        self.game_time = 0
        self.game_days = 1
        
        # الإحصائيات
        self.stats = {
            'play_time': 0,
            'enemies_killed': 0,
            'quests_completed': 0,
            'gold_earned': 0,
            'deaths': 0
        }
        
        # التهيئة
        self._initialize()
    
    def _initialize(self):
        """تهيئة اللعبة"""
        # تهيئة المحرك
        self.engine.initialize(
            title="مغامرات المملكة المفقودة",
            width=1280,
            height=720,
            fullscreen=False
        )
        
        # تسجيل الأنظمة
        self.render_system = RenderSystem(self.engine)
        self.physics_system = PhysicsSystem(self.engine)
        self.ai_system = AISystem(self.engine)
        self.audio_system = AudioSystem(self.engine)
        
        # تهيئة الأنظمة
        self.render_system.initialize(1280, 720)
        self.physics_system.initialize()
        self.ai_system.initialize()
        self.audio_system.initialize()
        
        # تسجيل الأنظمة في المحرك
        self.engine.register_system(self.render_system, "render", priority=100)
        self.engine.register_system(self.physics_system, "physics", priority=90)
        self.engine.register_system(self.ai_system, "ai", priority=80)
        self.engine.register_system(self.audio_system, "audio", priority=70)
        
        # تحميل الموارد
        self._load_resources()
        
        # تسجيل معالجات الأحداث
        self._register_event_handlers()
        
        print("RPG Game initialized")
    
    def _load_resources(self):
        """تحميل الموارد"""
        # تحميل النماذج
        self._load_models()
        
        # تحميل النسيج
        self._load_textures()
        
        # تحميل الأصوات
        self._load_sounds()
        
        # تحميل الواجهات
        self._load_ui()
    
    def _load_models(self):
        """تحميل النماذج"""
        models = {
            'player': 'models/player.obj',
            'npc_elder': 'models/npc_elder.obj',
            'goblin': 'models/goblin.obj',
            'wolf': 'models/wolf.obj',
            'tree': 'models/tree.obj',
            'rock': 'models/rock.obj',
            'house': 'models/house.obj'
        }
        
        for name, path in models.items():
            self.render_system.mesh_manager.load_mesh_from_file(name, Path(path))
    
    def _load_textures(self):
        """تحميل النسيج"""
        textures = {
            'player_tex': 'textures/player.png',
            'npc_tex': 'textures/npc.png',
            'goblin_tex': 'textures/goblin.png',
            'terrain_grass': 'textures/grass.png',
            'terrain_rock': 'textures/rock.png',
            'ui_background': 'textures/ui_bg.png'
        }
        
        for name, path in textures.items():
            self.render_system.texture_manager.load_texture(name, Path(path))
    
    def _load_sounds(self):
        """تحميل الأصوات"""
        sounds = {
            'music_main': ('audio/music/main.ogg', AudioType.MUSIC),
            'music_combat': ('audio/music/combat.ogg', AudioType.MUSIC),
            'sword_swing': ('audio/effects/sword_swing.wav', AudioType.EFFECT),
            'bow_shoot': ('audio/effects/bow_shoot.wav', AudioType.EFFECT),
            'spell_cast': ('audio/effects/spell_cast.wav', AudioType.EFFECT),
            'potion_drink': ('audio/effects/potion_drink.wav', AudioType.EFFECT)
        }
        
        for name, (path, audio_type) in sounds.items():
            self.audio_system.audio_manager.load_source(name, Path(path), audio_type)
    
    def _load_ui(self):
        """تحميل واجهة المستخدم"""
        # سيتم تنفيذها
        pass
    
    def _register_event_handlers(self):
        """تسجيل معالجات الأحداث"""
        event_bus = self.engine.event_bus
        
        # أحداث النظام
        event_bus.subscribe(EventType.KEY_DOWN, self._on_key_down)
        event_bus.subscribe(EventType.KEY_UP, self._on_key_up)
        event_bus.subscribe(EventType.MOUSE_DOWN, self._on_mouse_down)
        event_bus.subscribe(EventType.MOUSE_UP, self._on_mouse_up)
        
        # أحداث اللعبة
        event_bus.subscribe(EventType.ENTITY_CREATED, self._on_entity_created)
        event_bus.subscribe(EventType.ENTITY_DESTROYED, self._on_entity_destroyed)
        event_bus.subscribe(EventType.COLLISION_START, self._on_collision_start)
    
    def _on_key_down(self, event: Event):
        """معالجة ضغط مفتاح"""
        key = event.data['key']
        
        if self.state == GameState.PLAYING:
            self._handle_gameplay_input(key, True)
        elif self.state == GameState.MAIN_MENU:
            self._handle_menu_input(key, True)
        elif self.state == GameState.PAUSED:
            self._handle_pause_input(key, True)
        elif self.state == GameState.COMBAT:
            self._handle_combat_input(key, True)
    
    def _on_key_up(self, event: Event):
        """معالجة رفع مفتاح"""
        key = event.data['key']
        
        if self.state == GameState.PLAYING:
            self._handle_gameplay_input(key, False)
    
    def _on_mouse_down(self, event: Event):
        """معالجة ضغط زر الفأرة"""
        button = event.data['button']
        pos = event.data['pos']
        
        if self.state == GameState.PLAYING:
            self._handle_mouse_click(button, pos, True)
        elif self.state == GameState.MAIN_MENU:
            self._handle_menu_click(button, pos)
    
    def _on_mouse_up(self, event: Event):
        """معالجة رفع زر الفأرة"""
        button = event.data['button']
        pos = event.data['pos']
        
        if self.state == GameState.PLAYING:
            self._handle_mouse_click(button, pos, False)
    
    def _on_entity_created(self, event: Event):
        """معالجة إنشاء كيان"""
        entity_id = event.data['entity_id']
        # يمكن إضافة منطق إضافي هنا
    
    def _on_entity_destroyed(self, event: Event):
        """معالجة تدمير كيان"""
        entity_id = event.data['entity_id']
        # يمكن إضافة منطق إضافي هنا
    
    def _on_collision_start(self, event: Event):
        """معالجة بدء تصادم"""
        entity_a = event.data.get('entity_a')
        entity_b = event.data.get('entity_b')
        
        # التحقق من تصادم اللاعب مع عدو
        if self.player and self.player.entity_id:
            if (entity_a == self.player.entity_id or entity_b == self.player.entity_id):
                # تحديد الكيان الآخر
                other_entity = entity_b if entity_a == self.player.entity_id else entity_a
                
                # التحقق إذا كان عدو
                # (سيتم تنفيذ هذا بناءً على نظام الكيانات)
                pass
    
    def _handle_gameplay_input(self, key: int, pressed: bool):
        """معالجة إدخال اللعب"""
        # الحركة
        if key == pygame.K_w or key == pygame.K_UP:
            self._move_player('forward', pressed)
        elif key == pygame.K_s or key == pygame.K_DOWN:
            self._move_player('backward', pressed)
        elif key == pygame.K_a or key == pygame.K_LEFT:
            self._move_player('left', pressed)
        elif key == pygame.K_d or key == pygame.K_RIGHT:
            self._move_player('right', pressed)
        
        # الإجراءات
        elif key == pygame.K_SPACE and pressed:
            self._player_interact()
        elif key == pygame.K_e and pressed:
            self._open_inventory()
        elif key == pygame.K_q and pressed:
            self._use_ability(0)
        elif key == pygame.K_TAB and pressed:
            self._switch_target()
        
        # النظام
        elif key == pygame.K_ESCAPE and pressed:
            self._toggle_pause()
    
    def _handle_menu_input(self, key: int, pressed: bool):
        """معالجة إدخال القائمة"""
        if key == pygame.K_UP and pressed:
            self._navigate_menu(-1)
        elif key == pygame.K_DOWN and pressed:
            self._navigate_menu(1)
        elif key == pygame.K_RETURN and pressed:
            self._select_menu_option()
        elif key == pygame.K_ESCAPE and pressed:
            self._go_back_menu()
    
    def _handle_pause_input(self, key: int, pressed: bool):
        """معالجة إدخال الإيقاف المؤقت"""
        if key == pygame.K_ESCAPE and pressed:
            self._toggle_pause()
        elif key == pygame.K_m and pressed:
            self._return_to_main_menu()
    
    def _handle_combat_input(self, key: int, pressed: bool):
        """معالجة إدخال القتال"""
        if key == pygame.K_1 and pressed:
            self._combat_action('attack')
        elif key == pygame.K_2 and pressed:
            self._combat_action('skill')
        elif key == pygame.K_3 and pressed:
            self._combat_action('item')
        elif key == pygame.K_4 and pressed:
            self._combat_action('defend')
        elif key == pygame.K_ESCAPE and pressed:
            self._flee_combat()
    
    def _handle_mouse_click(self, button: int, pos: Tuple[int, int], pressed: bool):
        """معالجة نقر الفأرة"""
        if button == 1 and pressed:  # زر الأيسر
            self._player_attack()
        elif button == 3 and pressed:  # زر الأيمن
            self._player_block()
    
    def _handle_menu_click(self, button: int, pos: Tuple[int, int]):
        """معالجة نقر القائمة"""
        if button == 1:  # زر الأيسر
            # التحقق من النقر على خيارات القائمة
            pass
    
    def _move_player(self, direction: str, active: bool):
        """تحريك اللاعب"""
        if not self.player or not self.player.entity_id:
            return
        
        # الحصول على كيان اللاعب
        entity = self.engine.entity_manager.get_entity(self.player.entity_id)
        if not entity:
            return
        
        # الحصول على مكون الفيزياء
        body = self.physics_system.entity_to_body.get(self.player.entity_id)
        if not body:
            return
        
        # تطبيق القوة بناءً على الاتجاه
        force = np.zeros(3, dtype='f4')
        speed = 10.0
        
        if direction == 'forward':
            force[2] = -speed  # أمام
        elif direction == 'backward':
            force[2] = speed   # خلف
        elif direction == 'left':
            force[0] = -speed  # يسار
        elif direction == 'right':
            force[0] = speed   # يمين
        
        if active:
            body.apply_force(force)
        else:
            # إيقاف الحركة
            body.velocity[0] *= 0.9
            body.velocity[2] *= 0.9
    
    def _player_interact(self):
        """تفاعل اللاعب"""
        if not self.player:
            return
        
        # إطلاق شعاع للكشف عن الكيانات القريبة
        player_pos = self.player.world_position
        
        # التحقق من NPCs القريبة
        for npc_id, npc_data in self.world.npcs.items():
            npc_location = npc_data.get('location')
            if npc_location == self.player.location:
                # تفاعل مع NPC
                self._start_dialogue(npc_id)
                return
        
        # التحقق من العناصر القريبة
        # التحقق من الأبواب
        # التحقق من الأعداء
    
    def _start_dialogue(self, npc_id: str):
        """بدء حوار مع NPC"""
        npc_data = self.world.get_npc(npc_id)
        if not npc_data:
            return
        
        self.current_npc = npc_id
        self.state = GameState.DIALOGUE
        
        # تحميل الحوار
        dialogue_id = npc_data.get('dialogue')
        if dialogue_id:
            self._load_dialogue(dialogue_id)
        
        print(f"Starting dialogue with {npc_data['name']}")
    
    def _load_dialogue(self, dialogue_id: str):
        """تحميل الحوار"""
        # سيتم تحميل الحوار من ملف
        self.current_dialogue = {
            'current_node': 'start',
            'nodes': {
                'start': DialogueNode(
                    id='start',
                    text='مرحباً يا بطل! كيف يمكنني مساعدتك؟',
                    responses=[
                        {'text': 'من أنت؟', 'next': 'who_are_you'},
                        {'text': 'هل لديك مهام لي؟', 'next': 'quests'},
                        {'text': 'وداعاً', 'next': 'end'}
                    ]
                ),
                'who_are_you': DialogueNode(
                    id='who_are_you',
                    text='أنا شيخ هذه القرية. أحرسها منذ أكثر من 50 سنة.',
                    responses=[
                        {'text': 'أعود', 'next': 'start'}
                    ]
                ),
                'quests': DialogueNode(
                    id='quests',
                    text='نعم، لدينا مشكلة مع القوبلين في الأطلال.',
                    responses=[
                        {'text': 'سأساعد', 'next': 'accept_quest'},
                        {'text': 'ليس الآن', 'next': 'start'}
                    ]
                ),
                'accept_quest': DialogueNode(
                    id='accept_quest',
                    text='شكراً لك! اذهب للأطلال القديمة واقتل 10 قوبلين.',
                    actions=[
                        {'type': 'give_quest', 'quest_id': 'goblin_problem'}
                    ],
                    responses=[
                        {'text': 'سأفعل', 'next': 'end'}
                    ]
                ),
                'end': DialogueNode(
                    id='end',
                    text='حظاً سعيداً في مغامراتك!',
                    actions=[
                        {'type': 'end_dialogue'}
                    ],
                    responses=[]
                )
            }
        }
    
    def _open_inventory(self):
        """فتح المخزن"""
        if self.state == GameState.PLAYING:
            self.state = GameState.INVENTORY
            print("Inventory opened")
    
    def _use_ability(self, ability_slot: int):
        """استخدام قدرة"""
        if not self.player or ability_slot >= len(self.player.abilities):
            return
        
        # التحقق من المانا
        ability = self.player.abilities[ability_slot]
        mana_cost = ability.get('mana_cost', 0)
        
        if self.player.mana < mana_cost:
            print("Not enough mana!")
            return
        
        # استخدام القدرة
        self.player.mana -= mana_cost
        print(f"Used ability: {ability['name']}")
    
    def _switch_target(self):
        """تبديل الهدف"""
        # سيتم تنفيذها في نظام القتال
        pass
    
    def _toggle_pause(self):
        """تبديل الإيقاف المؤقت"""
        if self.state == GameState.PLAYING:
            self.state = GameState.PAUSED
            self.audio_system.audio_manager.pause_music()
        elif self.state == GameState.PAUSED:
            self.state = GameState.PLAYING
            self.audio_system.audio_manager.resume_music()
    
    def _return_to_main_menu(self):
        """العودة للقائمة الرئيسية"""
        self.state = GameState.MAIN_MENU
        self._cleanup_game()
    
    def _combat_action(self, action: str):
        """إجراء قتالي"""
        if not self.combat_encounter:
            return
        
        if action == 'attack':
            self._player_attack()
        elif action == 'skill':
            self._use_ability(0)  # أول مهارة
        elif action == 'item':
            self._use_combat_item()
        elif action == 'defend':
            self._player_defend()
    
    def _player_attack(self):
        """هجوم اللاعب"""
        if not self.player:
            return
        
        # حساب الضرر
        damage, damage_type = self.player.calculate_damage()
        
        # البحث عن هدف
        target = self._get_combat_target()
        if target:
            # تطبيق الضرر على الهدف
            # (سيتم تنفيذها في نظام القتال)
            print(f"Player attacks for {damage} {damage_type} damage!")
    
    def _player_defend(self):
        """دفاع اللاعب"""
        if not self.player:
            return
        
        # زيادة الدفاع للجولة
        print("Player defends!")
    
    def _use_combat_item(self):
        """استخدام عنصر في القتال"""
        # سيتم تنفيذها
        pass
    
    def _flee_combat(self):
        """الهروب من القتال"""
        if self.combat_encounter:
            # فرصة الهروب
            if random.random() < 0.7:  # 70% فرصة
                print("Successfully fled from combat!")
                self.state = GameState.PLAYING
                self.combat_encounter = None
            else:
                print("Failed to flee!")
    
    def _get_combat_target(self):
        """الحصول على هدف القتال"""
        if self.combat_encounter:
            # العودة على الهدف الحالي
            return self.combat_encounter.get('current_target')
        return None
    
    def _navigate_menu(self, direction: int):
        """التنقل في القائمة"""
        # سيتم تنفيذها في واجهة المستخدم
        pass
    
    def _select_menu_option(self):
        """اختيار خيار القائمة"""
        # سيتم تنفيذها في واجهة المستخدم
        pass
    
    def _go_back_menu(self):
        """العودة للقائمة السابقة"""
        # سيتم تنفيذها في واجهة المستخدم
        pass
    
    def create_character(self, name: str, character_class: CharacterClass):
        """إنشاء شخصية"""
        self.player = PlayerCharacter(name, character_class)
        
        # إنشاء كيان للاعب
        entity = self.engine.entity_manager.create_entity(['player'])
        
        # إضافة مكونات
        transform = Transform()
        transform.position = Vector3(0, 0, 0)
        
        entity.add_component(ComponentType.TRANSFORM, transform)
        
        # إضافة جسم فيزيائي
        body = RigidBody(
            position=np.array([0, 0, 0], dtype='f4'),
            body_type=BodyType.DYNAMIC,
            mass=70.0
        )
        
        # إضافة شكل تصادم
        shape = CollisionShape(
            shape_type=ShapeType.CAPSULE,
            size=(0.5, 0.5, 1.8)  # كبسولة بطول الإنسان
        )
        body.shapes.append(shape)
        
        self.physics_system.add_entity_body(entity.id, body)
        
        # إضافة وكيل ذكاء اصطناعي (للمراقبة فقط)
        self.ai_system.add_agent(entity.id, AIBehavior.NEUTRAL)
        
        # ربط باللاعب
        self.player.entity_id = entity.id
        self.player.world_position = Vector3(0, 0, 0)
        
        print(f"Character created: {name} the {character_class.value}")
    
    def start_game(self):
        """بدء اللعبة"""
        if not self.player:
            return
        
        # تحميل الموقع الأول
        self._load_location('start_village')
        
        # بدء الموسيقى
        self.audio_system.audio_manager.play_music('music_main', loops=-1)
        
        # تغيير الحالة
        self.state = GameState.PLAYING
        
        print("Game started!")
    
    def _load_location(self, location_id: str):
        """تحميل موقع"""
        location_data = self.world.get_location(location_id)
        if not location_data:
            return
        
        self.current_location = location_id
        self.player.location = location_id
        
        # إنشاء الكيانات للموقع
        self._create_location_entities(location_data)
        
        # تحديث موضع اللاعب
        spawn_point = location_data.get('spawn_point', (0, 0, 0))
        if self.player.entity_id:
            body = self.physics_system.entity_to_body.get(self.player.entity_id)
            if body:
                body.position = np.array(spawn_point, dtype='f4')
                self.player.world_position = Vector3(*spawn_point)
        
        print(f"Entered location: {location_data['name']}")
    
    def _create_location_entities(self, location_data: Dict[str, Any]):
        """إنشاء كيانات الموقع"""
        location_type = location_data.get('type', 'village')
        
        if location_type == 'village':
            self._create_village_entities(location_data)
        elif location_type == 'forest':
            self._create_forest_entities(location_data)
        elif location_type == 'dungeon':
            self._create_dungeon_entities(location_data)
    
    def _create_village_entities(self, location_data: Dict[str, Any]):
        """إنشاء كيانات القرية"""
        # إنشاء منازل
        for i in range(5):
            entity = self.engine.entity_manager.create_entity(['house'])
            
            # وضع عشوائي
            x = random.uniform(-20, 20)
            z = random.uniform(-20, 20)
            
            transform = Transform()
            transform.position = Vector3(x, 0, z)
            transform.scale = Vector3(3, 3, 3)
            
            entity.add_component(ComponentType.TRANSFORM, transform)
            
            # إضافة إلى نظام التصيير
            self.render_system.queue_render(
                'house',
                transform.matrix(),
                texture='house_tex'
            )
        
        # إنشاء NPCs
        npc_ids = location_data.get('npcs', [])
        for npc_id in npc_ids:
            npc_data = self.world.get_npc(npc_id)
            if npc_data:
                self._create_npc_entity(npc_data)
    
    def _create_npc_entity(self, npc_data: Dict[str, Any]):
        """إنشاء كيان NPC"""
        entity = self.engine.entity_manager.create_entity(['npc'])
        
        # وضع عشوائي
        x = random.uniform(-15, 15)
        z = random.uniform(-15, 15)
        
        transform = Transform()
        transform.position = Vector3(x, 0, z)
        
        entity.add_component(ComponentType.TRANSFORM, transform)
        
        # إضافة جسم فيزيائي
        body = RigidBody(
            position=np.array([x, 0, z], dtype='f4'),
            body_type=BodyType.KINEMATIC
        )
        
        shape = CollisionShape(
            shape_type=ShapeType.CAPSULE,
            size=(0.4, 0.4, 1.6)
        )
        body.shapes.append(shape)
        
        self.physics_system.add_entity_body(entity.id, body)
        
        # إضافة ذكاء اصطناعي
        self.ai_system.add_agent(entity.id, AIBehavior.PASSIVE)
        
        # إضافة إلى نظام التصيير
        self.render_system.queue_render(
            'npc_elder',
            transform.matrix(),
            texture='npc_tex'
        )
    
    def _create_forest_entities(self, location_data: Dict[str, Any]):
        """إنشاء كيانات الغابة"""
        # إنشاء أشجار
        for i in range(20):
            entity = self.engine.entity_manager.create_entity(['tree'])
            
            x = random.uniform(-30, 30)
            z = random.uniform(-30, 30)
            
            transform = Transform()
            transform.position = Vector3(x, 0, z)
            transform.scale = Vector3(random.uniform(1, 2), random.uniform(1, 2), random.uniform(1, 2))
            
            entity.add_component(ComponentType.TRANSFORM, transform)
            
            self.render_system.queue_render(
                'tree',
                transform.matrix(),
                texture='tree_tex'
            )
    
    def _create_dungeon_entities(self, location_data: Dict[str, Any]):
        """إنشاء كيانات الزنزانة"""
        # إنشاء جدران وأرضيات
        pass
    
    def start_combat(self, enemy_type: str):
        """بدء قتال"""
        enemy_data = self.world.get_enemy(enemy_type)
        if not enemy_data:
            return
        
        self.state = GameState.COMBAT
        self.combat_encounter = {
            'enemies': [enemy_data.copy()],
            'current_target': 0,
            'turn': 'player'
        }
        
        # تغيير الموسيقى
        self.audio_system.audio_manager.play_music('music_combat', loops=-1)
        
        print(f"Combat started with {enemy_data['name']}!")
    
    def update(self, delta_time: float):
        """تحديث اللعبة"""
        if self.state == GameState.PLAYING:
            self._update_gameplay(delta_time)
        elif self.state == GameState.COMBAT:
            self._update_combat(delta_time)
        
        # تحديث الوقت
        self.game_time += delta_time
        if self.game_time >= 86400:  # 24 ساعة في الثانية
            self.game_time = 0
            self.game_days += 1
    
    def _update_gameplay(self, delta_time: float):
        """تحديث اللعب"""
        # تحديث موضع اللاعب
        if self.player and self.player.entity_id:
            body = self.physics_system.entity_to_body.get(self.player.entity_id)
            if body:
                self.player.world_position = Vector3(*body.position)
        
        # التحقق من الأعداء القريبين
        self._check_for_enemies()
        
        # تحديث الاستعادة
        if self.player:
            # استعادة المانا
            mana_regen = self.player.stats.wisdom * 0.1 * delta_time
            self.player.mana = min(self.player.stats.max_mana, self.player.mana + mana_regen)
            
            # استعادة الطاقة
            stamina_regen = 5.0 * delta_time
            self.player.stamina = min(100, self.player.stamina + stamina_regen)
    
    def _update_combat(self, delta_time: float):
        """تحديث القتال"""
        if not self.combat_encounter:
            return
        
        turn = self.combat_encounter.get('turn')
        
        if turn == 'player':
            # انتظار إدخال اللاعب
            pass
        elif turn == 'enemy':
            # هجوم الأعداء
            self._enemy_turn()
    
    def _enemy_turn(self):
        """دور العدو"""
        enemies = self.combat_encounter.get('enemies', [])
        
        for enemy in enemies:
            if enemy.get('health', 0) <= 0:
                continue
            
            # هجوم العدو
            damage_min, damage_max = enemy.get('damage', (5, 10))
            damage = random.randint(damage_min, damage_max)
            
            player_defense = self.player.calculate_defense()
            mitigated_damage = max(1, damage - player_defense // 2)
            
            self.player.take_damage(mitigated_damage)
            
            print(f"{enemy['name']} attacks for {mitigated_damage} damage!")
            
            # التحقق من موت اللاعب
            if self.player.health <= 0:
                self._player_died()
                return
        
        # العودة لدور اللاعب
        self.combat_encounter['turn'] = 'player'
    
    def _check_for_enemies(self):
        """التحقق من وجود أعداء"""
        if not self.current_location:
            return
        
        # فرصة عشوائية للمواجهة
        if random.random() < 0.01:  # 1% فرصة كل تحديث
            enemy_data = self.world.get_random_enemy(self.current_location)
            if enemy_data:
                self.start_combat(enemy_data['name'])
    
    def _player_died(self):
        """موت اللاعب"""
        print("Player has died!")
        
        self.stats['deaths'] += 1
        
        # استعادة الصحة
        self.player.health = self.player.stats.max_health // 2
        self.player.mana = self.player.stats.max_mana // 2
        
        # العودة للقرية
        self._load_location('start_village')
        
        # الخروج من القتال
        self.state = GameState.PLAYING
        self.combat_encounter = None
        
        # استعادة الموسيقى
        self.audio_system.audio_manager.play_music('music_main', loops=-1)
    
    def _cleanup_game(self):
        """تنظيف اللعبة"""
        # إزالة الكيانات
        self.engine.entity_manager.clear()
        
        # إزالة الأجسام الفيزيائية
        self.physics_system.world.bodies.clear()
        
        # إزالة وكلاء الذكاء الاصطناعي
        self.ai_system.agents.clear()
        
        # إيقاف الموسيقى
        self.audio_system.audio_manager.stop_music()
        
        # إعادة تعيين المتغيرات
        self.player = None
        self.party.clear()
        self.current_location = None
        self.current_npc = None
        self.current_dialogue = None
        self.combat_encounter = None
        
        print("Game cleaned up")
    
    def render(self):
        """تصيير اللعبة"""
        # سيتم تنفيذها بواسطة نظام التصيير
        pass
    
    def run(self):
        """تشغيل اللعبة"""
        print("Starting RPG Game...")
        
        # عرض القائمة الرئيسية
        self._show_main_menu()
        
        # تشغيل المحرك
        self.engine.run()
    
    def _show_main_menu(self):
        """عرض القائمة الرئيسية"""
        self.state = GameState.MAIN_MENU
        
        # تشغيل الموسيقى
        self.audio_system.audio_manager.play_music('music_main', loops=-1)
        
        print("\n" + "="*50)
        print("مغامرات المملكة المفقودة")
        print("="*50)
        print("1. بدء لعبة جديدة")
        print("2. تحميل لعبة")
        print("3. الإعدادات")
        print("4. الخروج")
        print("="*50)
        
        # في الواجهة الرسومية، سيتم عرض القائمة بشكل مرئي
    
    def shutdown(self):
        """إيقاف اللعبة"""
        self._cleanup_game()
        
        # إيقاف الأنظمة
        self.audio_system.shutdown()
        self.ai_system.shutdown()
        self.physics_system.shutdown()
        self.render_system.shutdown()
        
        # إيقاف المحرك
        self.engine.shutdown()
        
        print("RPG Game shutdown")

# ============================================================================
# Main Function
# ============================================================================

def main():
    """الدالة الرئيسية"""
    try:
        # إنشاء اللعبة
        game = RPGGame()
        
        # تشغيل اللعبة
        game.run()
        
    except KeyboardInterrupt:
        print("\nGame interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()