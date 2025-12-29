"""
GameEnginePro - Core Module
نواة محرك الألعاب الأساسية
الإصدار: 1.0.0
المطور: GameEnginePro Team
"""

import pygame
import numpy as np
import json
import pickle
import threading
import queue
import time
import math
import random
import sys
import os
import gc
import weakref
import hashlib
import zlib
import base64
from enum import Enum, IntEnum, auto
from typing import Dict, List, Tuple, Optional, Any, Union, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from collections import defaultdict, deque, OrderedDict
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import logging
import inspect
import cProfile
import pstats
import tracemalloc

# ============================================================================
# Configuration & Constants
# ============================================================================

class EngineConfig:
    """إعدادات محرك الألعاب"""
    
    # إصدار المحرك
    ENGINE_VERSION = "1.0.0"
    ENGINE_NAME = "GameEnginePro"
    
    # إعدادات الأداء
    TARGET_FPS = 60
    MAX_FRAME_TIME = 0.1  # 100ms
    FIXED_TIMESTEP = 1.0 / 60.0
    MAX_PHYSICS_STEPS = 5
    
    # إعدادات الذاكرة
    MAX_ENTITIES = 10000
    MAX_COMPONENTS = 100000
    POOL_SIZES = {
        'transform': 10000,
        'render': 5000,
        'physics': 5000,
        'ai': 2000
    }
    
    # إعدادات التصيير
    DEFAULT_SCREEN_WIDTH = 1920
    DEFAULT_SCREEN_HEIGHT = 1080
    FULLSCREEN_MODES = ['windowed', 'borderless', 'fullscreen']
    VSYNC_ENABLED = True
    MSAA_SAMPLES = 4
    
    # إعدادات الصوت
    AUDIO_CHANNELS = 32
    AUDIO_FREQUENCY = 44100
    AUDIO_BUFFER_SIZE = 2048
    
    # إعدادات الشبكة
    NETWORK_PORT = 7777
    MAX_PLAYERS = 16
    NETWORK_TICKRATE = 30
    
    # إعدادات المسارات
    @staticmethod
    def get_paths():
        base_dir = Path.home() / "GameEnginePro"
        return {
            'base': base_dir,
            'logs': base_dir / "logs",
            'saves': base_dir / "saves",
            'cache': base_dir / "cache",
            'assets': base_dir / "assets",
            'config': base_dir / "config",
            'temp': base_dir / "temp"
        }
    
    @classmethod
    def initialize_paths(cls):
        """إنشاء المسارات المطلوبة"""
        paths = cls.get_paths()
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

# ============================================================================
# Logging System
# ============================================================================

class LogLevel(IntEnum):
    """مستويات السجلات"""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

class Logger:
    """نظام تسجيل متقدم"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.loggers = {}
        self.handlers = {}
        self.log_queue = queue.Queue()
        self.worker_thread = None
        self.running = False
        
        # إعداد التسجيل
        self.setup_logging()
        self._initialized = True
    
    def setup_logging(self):
        """إعداد نظام التسجيل"""
        paths = EngineConfig.get_paths()
        
        # تنسيق السجلات
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # سجل الملفات
        file_handler = logging.FileHandler(
            paths['logs'] / f"engine_{datetime.now().strftime('%Y%m%d')}.log",
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        
        # سجل وحدة التحكم
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        
        # السجل الرئيسي
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        self.start_log_worker()
    
    def start_log_worker(self):
        """بدء عامل معالجة السجلات"""
        self.running = True
        self.worker_thread = threading.Thread(
            target=self._log_worker,
            daemon=True,
            name="LogWorker"
        )
        self.worker_thread.start()
    
    def _log_worker(self):
        """معالجة السجلات في الخلفية"""
        while self.running:
            try:
                record = self.log_queue.get(timeout=1)
                if record is None:
                    break
                
                logger = logging.getLogger(record.name)
                logger.handle(record)
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Log worker error: {e}")
    
    def log(self, level: LogLevel, message: str, name: str = "Engine"):
        """تسجيل رسالة"""
        logger = logging.getLogger(name)
        logger.log(level.value, message)
    
    def debug(self, message: str, name: str = "Engine"):
        """تسجيل رسالة تصحيح"""
        self.log(LogLevel.DEBUG, message, name)
    
    def info(self, message: str, name: str = "Engine"):
        """تسجيل رسالة معلومات"""
        self.log(LogLevel.INFO, message, name)
    
    def warning(self, message: str, name: str = "Engine"):
        """تسجيل رسالة تحذير"""
        self.log(LogLevel.WARNING, message, name)
    
    def error(self, message: str, name: str = "Engine"):
        """تسجيل رسالة خطأ"""
        self.log(LogLevel.ERROR, message, name)
    
    def critical(self, message: str, name: str = "Engine"):
        """تسجيل رسالة حرجة"""
        self.log(LogLevel.CRITICAL, message, name)
    
    def shutdown(self):
        """إيقاف نظام التسجيل"""
        self.running = False
        if self.worker_thread:
            self.log_queue.put(None)
            self.worker_thread.join(timeout=5)

# ============================================================================
# Event System
# ============================================================================

class EventType(Enum):
    """أنواع الأحداث"""
    # أحداث النظام
    ENGINE_INIT = auto()
    ENGINE_SHUTDOWN = auto()
    FRAME_START = auto()
    FRAME_END = auto()
    
    # أحداث الإدخال
    KEY_DOWN = auto()
    KEY_UP = auto()
    MOUSE_DOWN = auto()
    MOUSE_UP = auto()
    MOUSE_MOVE = auto()
    MOUSE_WHEEL = auto()
    JOYSTICK_AXIS = auto()
    JOYSTICK_BUTTON = auto()
    
    # أحداث الكيانات
    ENTITY_CREATED = auto()
    ENTITY_DESTROYED = auto()
    COMPONENT_ADDED = auto()
    COMPONENT_REMOVED = auto()
    
    # أحداث اللعبة
    GAME_START = auto()
    GAME_PAUSE = auto()
    GAME_RESUME = auto()
    GAME_OVER = auto()
    
    # أحداث المستوى
    LEVEL_LOADED = auto()
    LEVEL_UNLOADED = auto()
    LEVEL_COMPLETED = auto()
    
    # أحداث الفيزياء
    COLLISION_START = auto()
    COLLISION_END = auto()
    TRIGGER_ENTER = auto()
    TRIGGER_EXIT = auto()
    
    # أحداث الصوت
    SOUND_PLAYED = auto()
    MUSIC_STARTED = auto()
    MUSIC_STOPPED = auto()

@dataclass
class Event:
    """فئة الحدث"""
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: Any = None
    
    def __post_init__(self):
        self.handled = False
    
    def is_handled(self) -> bool:
        return self.handled
    
    def mark_handled(self):
        self.handled = True

class EventBus:
    """نظام تمرير الأحداث"""
    
    def __init__(self):
        self.handlers = defaultdict(list)
        self.event_queue = deque()
        self.priority_handlers = defaultdict(list)
        self.event_history = deque(maxlen=1000)
        self.lock = threading.RLock()
        self.enabled = True
    
    def subscribe(self, event_type: EventType, handler: Callable, priority: int = 0):
        """الاشتراك في حدث"""
        with self.lock:
            if priority > 0:
                self.priority_handlers[event_type].append((priority, handler))
                self.priority_handlers[event_type].sort(key=lambda x: x[0], reverse=True)
            else:
                self.handlers[event_type].append(handler)
    
    def unsubscribe(self, event_type: EventType, handler: Callable):
        """إلغاء الاشتراك من حدث"""
        with self.lock:
            if handler in self.handlers[event_type]:
                self.handlers[event_type].remove(handler)
            
            # إزالة من المعالجات ذات الأولوية
            self.priority_handlers[event_type] = [
                (p, h) for p, h in self.priority_handlers[event_type]
                if h != handler
            ]
    
    def dispatch(self, event: Event):
        """إرسال حدث"""
        if not self.enabled:
            return
        
        with self.lock:
            self.event_history.append(event)
            
            # معالجة المعالجات ذات الأولوية أولاً
            for priority, handler in self.priority_handlers[event.type]:
                try:
                    handler(event)
                    if event.is_handled():
                        return
                except Exception as e:
                    Logger().error(f"Priority handler error: {e}")
            
            # معالجة المعالجات العادية
            for handler in self.handlers[event.type]:
                try:
                    handler(event)
                    if event.is_handled():
                        return
                except Exception as e:
                    Logger().error(f"Handler error: {e}")
    
    def queue_event(self, event: Event):
        """إضافة حدث إلى قائمة الانتظار"""
        with self.lock:
            self.event_queue.append(event)
    
    def process_events(self):
        """معالجة الأحداث في قائمة الانتظار"""
        with self.lock:
            while self.event_queue:
                event = self.event_queue.popleft()
                self.dispatch(event)
    
    def clear(self):
        """مسح جميع الأحداث"""
        with self.lock:
            self.event_queue.clear()
            self.event_history.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات النظام"""
        with self.lock:
            return {
                'queued_events': len(self.event_queue),
                'total_handlers': sum(len(h) for h in self.handlers.values()) + 
                                 sum(len(h) for h in self.priority_handlers.values()),
                'history_size': len(self.event_history),
                'event_types': len(self.handlers)
            }

# ============================================================================
# Resource Management System
# ============================================================================

class ResourceType(Enum):
    """أنواع الموارد"""
    TEXTURE = "texture"
    MODEL = "model"
    SHADER = "shader"
    SOUND = "sound"
    MUSIC = "music"
    FONT = "font"
    SCRIPT = "script"
    CONFIG = "config"
    DATA = "data"

@dataclass
class Resource:
    """فئة المورد"""
    id: str
    type: ResourceType
    path: Path
    data: Any = None
    size: int = 0
    loaded: bool = False
    references: int = 0
    last_access: float = field(default_factory=time.time)
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        return isinstance(other, Resource) and self.id == other.id

class ResourceManager:
    """مدير الموارد المتقدم"""
    
    def __init__(self):
        self.resources: Dict[str, Resource] = {}
        self.resource_pools = defaultdict(dict)
        self.loaders = {}
        self.cache_size = 1024 * 1024 * 512  # 512MB
        self.current_cache = 0
        self.lock = threading.RLock()
        self.lru_queue = deque()
        
        # سجل التحميل
        self.load_log = deque(maxlen=100)
        
        # تسجيل المعالجات
        self.register_default_loaders()
    
    def register_loader(self, resource_type: ResourceType, loader: Callable):
        """تسجيل محمل للمورد"""
        self.loaders[resource_type] = loader
    
    def register_default_loaders(self):
        """تسجيل المعالجات الافتراضية"""
        self.register_loader(ResourceType.TEXTURE, self._load_texture)
        self.register_loader(ResourceType.SOUND, self._load_sound)
        self.register_loader(ResourceType.FONT, self._load_font)
        self.register_loader(ResourceType.CONFIG, self._load_config)
    
    def _load_texture(self, path: Path) -> Any:
        """تحميل نسيج"""
        import pygame
        try:
            texture = pygame.image.load(str(path)).convert_alpha()
            return texture
        except Exception as e:
            Logger().error(f"Failed to load texture {path}: {e}")
            return None
    
    def _load_sound(self, path: Path) -> Any:
        """تحميل صوت"""
        import pygame
        try:
            sound = pygame.mixer.Sound(str(path))
            return sound
        except Exception as e:
            Logger().error(f"Failed to load sound {path}: {e}")
            return None
    
    def _load_font(self, path: Path) -> Any:
        """تحميل خط"""
        import pygame
        try:
            font = pygame.font.Font(str(path), 24)
            return font
        except Exception as e:
            Logger().error(f"Failed to load font {path}: {e}")
            return None
    
    def _load_config(self, path: Path) -> Any:
        """تحميل إعدادات"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                if path.suffix == '.json':
                    return json.load(f)
                elif path.suffix == '.yaml':
                    import yaml
                    return yaml.safe_load(f)
                else:
                    return f.read()
        except Exception as e:
            Logger().error(f"Failed to load config {path}: {e}")
            return None
    
    def load(self, resource_id: str, resource_type: ResourceType, 
             path: Union[str, Path], force_reload: bool = False) -> Optional[Resource]:
        """تحميل مورد"""
        with self.lock:
            path = Path(path)
            
            # التحقق من التخزين المؤقت
            if not force_reload and resource_id in self.resources:
                resource = self.resources[resource_id]
                resource.last_access = time.time()
                resource.references += 1
                
                # تحديث LRU
                if resource_id in self.lru_queue:
                    self.lru_queue.remove(resource_id)
                self.lru_queue.append(resource_id)
                
                self.log_load(resource_id, "cache_hit")
                return resource
            
            # التحقق من وجود الملف
            if not path.exists():
                Logger().error(f"Resource file not found: {path}")
                return None
            
            # إنشاء المورد
            resource = Resource(
                id=resource_id,
                type=resource_type,
                path=path,
                size=path.stat().st_size
            )
            
            # التحقق من سعة التخزين المؤقت
            if self.current_cache + resource.size > self.cache_size:
                self._clean_cache(resource.size)
            
            # تحميل البيانات
            loader = self.loaders.get(resource_type)
            if loader:
                resource.data = loader(path)
                if resource.data is not None:
                    resource.loaded = True
                    resource.references = 1
                    
                    # تخزين المورد
                    self.resources[resource_id] = resource
                    self.resource_pools[resource_type][resource_id] = resource
                    self.current_cache += resource.size
                    
                    # إضافة إلى LRU
                    self.lru_queue.append(resource_id)
                    
                    self.log_load(resource_id, "loaded")
                    return resource
            
            return None
    
    def _clean_cache(self, required_size: int):
        """تنظيف التخزين المؤقت"""
        while self.lru_queue and self.current_cache + required_size > self.cache_size:
            resource_id = self.lru_queue.popleft()
            if resource_id in self.resources:
                resource = self.resources[resource_id]
                if resource.references == 0:
                    self._unload_resource(resource_id)
    
    def _unload_resource(self, resource_id: str):
        """إلغاء تحميل مورد"""
        if resource_id in self.resources:
            resource = self.resources[resource_id]
            
            # تحرير الذاكرة
            if hasattr(resource.data, '__del__'):
                del resource.data
            
            self.current_cache -= resource.size
            del self.resources[resource_id]
            del self.resource_pools[resource.type][resource_id]
            
            self.log_load(resource_id, "unloaded")
    
    def release(self, resource_id: str):
        """تحرير مورد"""
        with self.lock:
            if resource_id in self.resources:
                resource = self.resources[resource_id]
                resource.references = max(0, resource.references - 1)
                
                if resource.references == 0:
                    resource.last_access = time.time()
    
    def preload(self, manifest_path: Path):
        """تحميل مسبق للموارد"""
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            for item in manifest.get('resources', []):
                self.load(
                    item['id'],
                    ResourceType(item['type']),
                    manifest_path.parent / item['path']
                )
            
            Logger().info(f"Preloaded {len(manifest.get('resources', []))} resources")
            
        except Exception as e:
            Logger().error(f"Failed to preload resources: {e}")
    
    def log_load(self, resource_id: str, action: str):
        """تسجيل عملية تحميل"""
        self.load_log.append({
            'timestamp': time.time(),
            'resource_id': resource_id,
            'action': action
        })
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات الموارد"""
        with self.lock:
            stats = {
                'total_resources': len(self.resources),
                'cache_size_mb': self.current_cache / (1024 * 1024),
                'max_cache_mb': self.cache_size / (1024 * 1024),
                'cache_usage_percent': (self.current_cache / self.cache_size) * 100,
                'loaded_resources': sum(1 for r in self.resources.values() if r.loaded),
                'total_references': sum(r.references for r in self.resources.values())
            }
            
            # إحصائيات حسب النوع
            for resource_type in ResourceType:
                type_resources = self.resource_pools.get(resource_type, {})
                stats[f'{resource_type.value}_count'] = len(type_resources)
                stats[f'{resource_type.value}_size_mb'] = sum(
                    r.size for r in type_resources.values()
                ) / (1024 * 1024)
            
            return stats

# ============================================================================
# Entity Component System (ECS)
# ============================================================================

class ComponentType(Enum):
    """أنواع المكونات"""
    TRANSFORM = auto()
    RENDER = auto()
    PHYSICS = auto()
    ANIMATION = auto()
    AI = auto()
    SCRIPT = auto()
    AUDIO = auto()
    PARTICLE = auto()
    LIGHT = auto()
    CAMERA = auto()

class Entity:
    """فئة الكيان"""
    
    __slots__ = ('id', 'components', 'tags', 'active', 'parent', 'children')
    
    def __init__(self, entity_id: int):
        self.id = entity_id
        self.components: Dict[ComponentType, Any] = {}
        self.tags: List[str] = []
        self.active = True
        self.parent: Optional['Entity'] = None
        self.children: List['Entity'] = []
    
    def add_component(self, component_type: ComponentType, component: Any):
        """إضافة مكون"""
        self.components[component_type] = component
    
    def get_component(self, component_type: ComponentType) -> Optional[Any]:
        """الحصول على مكون"""
        return self.components.get(component_type)
    
    def has_component(self, component_type: ComponentType) -> bool:
        """التحقق من وجود مكون"""
        return component_type in self.components
    
    def remove_component(self, component_type: ComponentType):
        """إزالة مكون"""
        if component_type in self.components:
            del self.components[component_type]
    
    def add_tag(self, tag: str):
        """إضافة وسم"""
        if tag not in self.tags:
            self.tags.append(tag)
    
    def has_tag(self, tag: str) -> bool:
        """التحقق من وجود وسم"""
        return tag in self.tags
    
    def remove_tag(self, tag: str):
        """إزالة وسم"""
        if tag in self.tags:
            self.tags.remove(tag)
    
    def add_child(self, child: 'Entity'):
        """إضافة ابن"""
        if child not in self.children:
            self.children.append(child)
            child.parent = self
    
    def remove_child(self, child: 'Entity'):
        """إزالة ابن"""
        if child in self.children:
            self.children.remove(child)
            child.parent = None
    
    def get_world_transform(self):
        """الحصول على تحويل عالمي"""
        from .math import Transform  # سيكون في وحدة الرياضيات
        transform = self.get_component(ComponentType.TRANSFORM)
        if not transform:
            return Transform()
        
        world_transform = transform.copy()
        parent = self.parent
        while parent:
            parent_transform = parent.get_component(ComponentType.TRANSFORM)
            if parent_transform:
                world_transform = parent_transform.combine(world_transform)
            parent = parent.parent
        
        return world_transform

class ComponentPool:
    """تجمع المكونات"""
    
    def __init__(self, component_type: ComponentType, initial_size: int = 100):
        self.component_type = component_type
        self.components = []
        self.free_indices = []
        self.grow_size = initial_size // 2
        
        # تنمية التجمع الأولي
        self._grow(initial_size)
    
    def _grow(self, size: int):
        """تنمية التجمع"""
        for i in range(size):
            self.components.append(None)
            self.free_indices.append(len(self.components) - 1)
    
    def allocate(self) -> int:
        """تخصيص مؤشر مكون"""
        if not self.free_indices:
            self._grow(self.grow_size)
        
        return self.free_indices.pop()
    
    def deallocate(self, index: int):
        """تحرير مؤشر مكون"""
        self.components[index] = None
        self.free_indices.append(index)
    
    def get(self, index: int) -> Optional[Any]:
        """الحصول على مكون"""
        if 0 <= index < len(self.components):
            return self.components[index]
        return None
    
    def set(self, index: int, component: Any):
        """تعيين مكون"""
        if 0 <= index < len(self.components):
            self.components[index] = component
    
    def clear(self):
        """مسح التجمع"""
        self.components.clear()
        self.free_indices.clear()

class EntityManager:
    """مدير الكيانات المتقدم"""
    
    def __init__(self):
        self.entities: Dict[int, Entity] = {}
        self.component_pools: Dict[ComponentType, ComponentPool] = {}
        self.entity_component_map: Dict[int, Dict[ComponentType, int]] = defaultdict(dict)
        self.next_entity_id = 1
        self.lock = threading.RLock()
        
        # السجلات
        self.creation_log = deque(maxlen=1000)
        self.performance_stats = {
            'create_time': [],
            'destroy_time': [],
            'query_time': []
        }
        
        # إعداد تجمعات المكونات
        self._setup_component_pools()
    
    def _setup_component_pools(self):
        """إعداد تجمعات المكونات"""
        for component_type in ComponentType:
            initial_size = EngineConfig.POOL_SIZES.get(
                component_type.name.lower(), 100
            )
            self.component_pools[component_type] = ComponentPool(
                component_type, initial_size
            )
    
    def create_entity(self, tags: List[str] = None) -> Entity:
        """إنشاء كيان جديد"""
        start_time = time.perf_counter()
        
        with self.lock:
            entity_id = self.next_entity_id
            self.next_entity_id += 1
            
            entity = Entity(entity_id)
            if tags:
                for tag in tags:
                    entity.add_tag(tag)
            
            self.entities[entity_id] = entity
            
            # تسجيل الإنشاء
            self.creation_log.append({
                'timestamp': time.time(),
                'entity_id': entity_id,
                'tags': tags or []
            })
        
        # إرسال حدث
        event_bus = EventBus()
        event_bus.dispatch(Event(
            EventType.ENTITY_CREATED,
            {'entity_id': entity_id}
        ))
        
        # تسجيل الأداء
        elapsed = time.perf_counter() - start_time
        self.performance_stats['create_time'].append(elapsed)
        
        return entity
    
    def destroy_entity(self, entity_id: int):
        """تدمير كيان"""
        start_time = time.perf_counter()
        
        with self.lock:
            if entity_id not in self.entities:
                return
            
            entity = self.entities[entity_id]
            
            # تحرير المكونات
            for component_type, pool_index in self.entity_component_map[entity_id].items():
                pool = self.component_pools.get(component_type)
                if pool:
                    pool.deallocate(pool_index)
            
            # إزالة من الخريطة
            if entity_id in self.entity_component_map:
                del self.entity_component_map[entity_id]
            
            # إزالة الكيان
            del self.entities[entity_id]
            
            # إرسال حدث
            event_bus = EventBus()
            event_bus.dispatch(Event(
                EventType.ENTITY_DESTROYED,
                {'entity_id': entity_id}
            ))
        
        # تسجيل الأداء
        elapsed = time.perf_counter() - start_time
        self.performance_stats['destroy_time'].append(elapsed)
    
    def add_component(self, entity_id: int, component_type: ComponentType, 
                      component_data: Any) -> bool:
        """إضافة مكون لكيان"""
        with self.lock:
            if entity_id not in self.entities:
                return False
            
            # الحصول على التجمع
            pool = self.component_pools.get(component_type)
            if not pool:
                return False
            
            # تخصيص مؤشر
            pool_index = pool.allocate()
            pool.set(pool_index, component_data)
            
            # تحديث الخريطة
            self.entity_component_map[entity_id][component_type] = pool_index
            
            # تحديث الكيان
            entity = self.entities[entity_id]
            entity.add_component(component_type, component_data)
            
            # إرسال حدث
            event_bus = EventBus()
            event_bus.dispatch(Event(
                EventType.COMPONENT_ADDED,
                {
                    'entity_id': entity_id,
                    'component_type': component_type
                }
            ))
            
            return True
    
    def remove_component(self, entity_id: int, component_type: ComponentType) -> bool:
        """إزالة مكون من كيان"""
        with self.lock:
            if (entity_id not in self.entities or 
                entity_id not in self.entity_component_map or
                component_type not in self.entity_component_map[entity_id]):
                return False
            
            # الحصول على التجمع والمؤشر
            pool = self.component_pools.get(component_type)
            pool_index = self.entity_component_map[entity_id][component_type]
            
            if pool:
                pool.deallocate(pool_index)
            
            # تحديث الخريطة
            del self.entity_component_map[entity_id][component_type]
            
            # تحديث الكيان
            entity = self.entities[entity_id]
            entity.remove_component(component_type)
            
            # إرسال حدث
            event_bus = EventBus()
            event_bus.dispatch(Event(
                EventType.COMPONENT_REMOVED,
                {
                    'entity_id': entity_id,
                    'component_type': component_type
                }
            ))
            
            return True
    
    def query_entities(self, **criteria) -> List[Entity]:
        """استعلام الكيانات"""
        start_time = time.perf_counter()
        
        with self.lock:
            result = []
            
            for entity in self.entities.values():
                if not entity.active:
                    continue
                
                match = True
                
                # مطابقة المكونات
                if 'has_components' in criteria:
                    for component_type in criteria['has_components']:
                        if not entity.has_component(component_type):
                            match = False
                            break
                
                # مطابقة الوسوم
                if match and 'has_tags' in criteria:
                    for tag in criteria['has_tags']:
                        if not entity.has_tag(tag):
                            match = False
                            break
                
                # مطابقة الاستبعاد
                if match and 'exclude_tags' in criteria:
                    for tag in criteria['exclude_tags']:
                        if entity.has_tag(tag):
                            match = False
                            break
                
                if match:
                    result.append(entity)
            
            # تسجيل الأداء
            elapsed = time.perf_counter() - start_time
            self.performance_stats['query_time'].append(elapsed)
            
            return result
    
    def get_entity(self, entity_id: int) -> Optional[Entity]:
        """الحصول على كيان"""
        with self.lock:
            return self.entities.get(entity_id)
    
    def get_component(self, entity_id: int, component_type: ComponentType) -> Optional[Any]:
        """الحصول على مكون"""
        with self.lock:
            if (entity_id in self.entity_component_map and 
                component_type in self.entity_component_map[entity_id]):
                pool_index = self.entity_component_map[entity_id][component_type]
                pool = self.component_pools.get(component_type)
                if pool:
                    return pool.get(pool_index)
            return None
    
    def clear(self):
        """مسح جميع الكيانات"""
        with self.lock:
            entity_ids = list(self.entities.keys())
            for entity_id in entity_ids:
                self.destroy_entity(entity_id)
            
            self.entities.clear()
            self.entity_component_map.clear()
            
            for pool in self.component_pools.values():
                pool.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات الكيانات"""
        with self.lock:
            # حساب متوسطات الأداء
            def avg_time(times):
                return sum(times) / len(times) if times else 0
            
            stats = {
                'total_entities': len(self.entities),
                'active_entities': sum(1 for e in self.entities.values() if e.active),
                'component_count': sum(len(c) for c in self.entity_component_map.values()),
                'avg_create_time': avg_time(self.performance_stats['create_time']),
                'avg_destroy_time': avg_time(self.performance_stats['destroy_time']),
                'avg_query_time': avg_time(self.performance_stats['query_time']),
                'creation_log_size': len(self.creation_log)
            }
            
            # إحصائيات المكونات
            component_stats = {}
            for component_type in ComponentType:
                pool = self.component_pools.get(component_type)
                if pool:
                    component_stats[component_type.name] = {
                        'allocated': len(pool.components) - len(pool.free_indices),
                        'total': len(pool.components),
                        'free': len(pool.free_indices)
                    }
            
            stats['component_stats'] = component_stats
            
            return stats

# ============================================================================
# Math Library
# ============================================================================

class Vector2:
    """متجه ثنائي الأبعاد"""
    
    __slots__ = ('x', 'y')
    
    def __init__(self, x: float = 0.0, y: float = 0.0):
        self.x = float(x)
        self.y = float(y)
    
    def __add__(self, other: 'Vector2') -> 'Vector2':
        return Vector2(self.x + other.x, self.y + other.y)
    
    def __sub__(self, other: 'Vector2') -> 'Vector2':
        return Vector2(self.x - other.x, self.y - other.y)
    
    def __mul__(self, scalar: float) -> 'Vector2':
        return Vector2(self.x * scalar, self.y * scalar)
    
    def __truediv__(self, scalar: float) -> 'Vector2':
        return Vector2(self.x / scalar, self.y / scalar)
    
    def __neg__(self) -> 'Vector2':
        return Vector2(-self.x, -self.y)
    
    def __eq__(self, other: 'Vector2') -> bool:
        return math.isclose(self.x, other.x) and math.isclose(self.y, other.y)
    
    def __repr__(self) -> str:
        return f"Vector2({self.x:.2f}, {self.y:.2f})"
    
    def magnitude(self) -> float:
        """طول المتجه"""
        return math.sqrt(self.x * self.x + self.y * self.y)
    
    def normalized(self) -> 'Vector2':
        """متجه وحدة"""
        mag = self.magnitude()
        if mag > 0:
            return Vector2(self.x / mag, self.y / mag)
        return Vector2()
    
    def dot(self, other: 'Vector2') -> float:
        """حاصل الضرب النقطي"""
        return self.x * other.x + self.y * other.y
    
    def distance(self, other: 'Vector2') -> float:
        """المسافة بين متجهين"""
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)
    
    def rotate(self, angle: float) -> 'Vector2':
        """تدوير المتجه"""
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        return Vector2(
            self.x * cos_a - self.y * sin_a,
            self.x * sin_a + self.y * cos_a
        )
    
    def lerp(self, other: 'Vector2', t: float) -> 'Vector2':
        """الاستيفاء الخطي"""
        return Vector2(
            self.x + (other.x - self.x) * t,
            self.y + (other.y - self.y) * t
        )
    
    @classmethod
    def zero(cls) -> 'Vector2':
        """المتجه الصفري"""
        return cls(0, 0)
    
    @classmethod
    def one(cls) -> 'Vector2':
        """المتجه الواحد"""
        return cls(1, 1)
    
    @classmethod
    def up(cls) -> 'Vector2':
        """المتجه للأعلى"""
        return cls(0, -1)
    
    @classmethod
    def down(cls) -> 'Vector2':
        """المتجه للأسفل"""
        return cls(0, 1)
    
    @classmethod
    def left(cls) -> 'Vector2':
        """المتجه لليسار"""
        return cls(-1, 0)
    
    @classmethod
    def right(cls) -> 'Vector2':
        """المتجه لليمين"""
        return cls(1, 0)

class Vector3:
    """متجه ثلاثي الأبعاد"""
    
    __slots__ = ('x', 'y', 'z')
    
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
    
    def __add__(self, other: 'Vector3') -> 'Vector3':
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)
    
    def __sub__(self, other: 'Vector3') -> 'Vector3':
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)
    
    def __mul__(self, scalar: float) -> 'Vector3':
        return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)
    
    def __truediv__(self, scalar: float) -> 'Vector3':
        return Vector3(self.x / scalar, self.y / scalar, self.z / scalar)
    
    def __neg__(self) -> 'Vector3':
        return Vector3(-self.x, -self.y, -self.z)
    
    def __eq__(self, other: 'Vector3') -> bool:
        return (math.isclose(self.x, other.x) and 
                math.isclose(self.y, other.y) and 
                math.isclose(self.z, other.z))
    
    def __repr__(self) -> str:
        return f"Vector3({self.x:.2f}, {self.y:.2f}, {self.z:.2f})"
    
    def magnitude(self) -> float:
        """طول المتجه"""
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)
    
    def normalized(self) -> 'Vector3':
        """متجه وحدة"""
        mag = self.magnitude()
        if mag > 0:
            return Vector3(self.x / mag, self.y / mag, self.z / mag)
        return Vector3()
    
    def dot(self, other: 'Vector3') -> float:
        """حاصل الضرب النقطي"""
        return self.x * other.x + self.y * other.y + self.z * other.z
    
    def cross(self, other: 'Vector3') -> 'Vector3':
        """حاصل الضرب الاتجاهي"""
        return Vector3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x
        )
    
    def distance(self, other: 'Vector3') -> float:
        """المسافة بين متجهين"""
        return math.sqrt(
            (self.x - other.x) ** 2 +
            (self.y - other.y) ** 2 +
            (self.z - other.z) ** 2
        )
    
    def lerp(self, other: 'Vector3', t: float) -> 'Vector3':
        """الاستيفاء الخطي"""
        return Vector3(
            self.x + (other.x - self.x) * t,
            self.y + (other.y - self.y) * t,
            self.z + (other.z - self.z) * t
        )
    
    @classmethod
    def zero(cls) -> 'Vector3':
        """المتجه الصفري"""
        return cls(0, 0, 0)
    
    @classmethod
    def one(cls) -> 'Vector3':
        """المتجه الواحد"""
        return cls(1, 1, 1)
    
    @classmethod
    def up(cls) -> 'Vector3':
        """المتجه للأعلى"""
        return cls(0, 1, 0)
    
    @classmethod
    def down(cls) -> 'Vector3':
        """المتجه للأسفل"""
        return cls(0, -1, 0)
    
    @classmethod
    def left(cls) -> 'Vector3':
        """المتجه لليسار"""
        return cls(-1, 0, 0)
    
    @classmethod
    def right(cls) -> 'Vector3':
        """المتجه لليمين"""
        return cls(1, 0, 0)
    
    @classmethod
    def forward(cls) -> 'Vector3':
        """المتجه للأمام"""
        return cls(0, 0, 1)
    
    @classmethod
    def back(cls) -> 'Vector3':
        """المتجه للخلف"""
        return cls(0, 0, -1)

class Matrix4:
    """مصفوفة 4x4"""
    
    def __init__(self, data: List[List[float]] = None):
        if data is None:
            self.data = [[0.0] * 4 for _ in range(4)]
            self.identity()
        else:
            self.data = data
    
    def identity(self):
        """تحويل إلى مصفوفة وحدة"""
        for i in range(4):
            for j in range(4):
                self.data[i][j] = 1.0 if i == j else 0.0
        return self
    
    def __mul__(self, other: 'Matrix4') -> 'Matrix4':
        """ضرب المصفوفات"""
        result = Matrix4()
        for i in range(4):
            for j in range(4):
                result.data[i][j] = (
                    self.data[i][0] * other.data[0][j] +
                    self.data[i][1] * other.data[1][j] +
                    self.data[i][2] * other.data[2][j] +
                    self.data[i][3] * other.data[3][j]
                )
        return result
    
    def transform_vector(self, vector: Vector3) -> Vector3:
        """تحويل متجه"""
        x = (self.data[0][0] * vector.x + self.data[0][1] * vector.y + 
             self.data[0][2] * vector.z + self.data[0][3])
        y = (self.data[1][0] * vector.x + self.data[1][1] * vector.y + 
             self.data[1][2] * vector.z + self.data[1][3])
        z = (self.data[2][0] * vector.x + self.data[2][1] * vector.y + 
             self.data[2][2] * vector.z + self.data[2][3])
        w = (self.data[3][0] * vector.x + self.data[3][1] * vector.y + 
             self.data[3][2] * vector.z + self.data[3][3])
        
        if w != 0:
            return Vector3(x / w, y / w, z / w)
        return Vector3(x, y, z)
    
    @classmethod
    def translation(cls, x: float, y: float, z: float) -> 'Matrix4':
        """مصفوفة إزاحة"""
        m = cls()
        m.identity()
        m.data[0][3] = x
        m.data[1][3] = y
        m.data[2][3] = z
        return m
    
    @classmethod
    def scaling(cls, x: float, y: float, z: float) -> 'Matrix4':
        """مصفوفة قياس"""
        m = cls()
        m.identity()
        m.data[0][0] = x
        m.data[1][1] = y
        m.data[2][2] = z
        return m
    
    @classmethod
    def rotation_x(cls, angle: float) -> 'Matrix4':
        """مصفوفة دوران حول المحور X"""
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        m = cls()
        m.identity()
        m.data[1][1] = cos_a
        m.data[1][2] = -sin_a
        m.data[2][1] = sin_a
        m.data[2][2] = cos_a
        return m
    
    @classmethod
    def rotation_y(cls, angle: float) -> 'Matrix4':
        """مصفوفة دوران حول المحور Y"""
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        m = cls()
        m.identity()
        m.data[0][0] = cos_a
        m.data[0][2] = sin_a
        m.data[2][0] = -sin_a
        m.data[2][2] = cos_a
        return m
    
    @classmethod
    def rotation_z(cls, angle: float) -> 'Matrix4':
        """مصفوفة دوران حول المحور Z"""
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        m = cls()
        m.identity()
        m.data[0][0] = cos_a
        m.data[0][1] = -sin_a
        m.data[1][0] = sin_a
        m.data[1][1] = cos_a
        return m
    
    @classmethod
    def perspective(cls, fov: float, aspect: float, 
                   near: float, far: float) -> 'Matrix4':
        """مصفوفة منظور"""
        f = 1.0 / math.tan(math.radians(fov) / 2.0)
        
        m = cls()
        m.data[0][0] = f / aspect
        m.data[1][1] = f
        m.data[2][2] = (far + near) / (near - far)
        m.data[2][3] = (2 * far * near) / (near - far)
        m.data[3][2] = -1.0
        m.data[3][3] = 0.0
        return m
    
    @classmethod
    def orthographic(cls, left: float, right: float,
                    bottom: float, top: float,
                    near: float, far: float) -> 'Matrix4':
        """مصفوفة متعامدة"""
        m = cls()
        m.data[0][0] = 2.0 / (right - left)
        m.data[1][1] = 2.0 / (top - bottom)
        m.data[2][2] = -2.0 / (far - near)
        m.data[0][3] = -(right + left) / (right - left)
        m.data[1][3] = -(top + bottom) / (top - bottom)
        m.data[2][3] = -(far + near) / (far - near)
        m.data[3][3] = 1.0
        return m

class Transform:
    """التحويل"""
    
    __slots__ = ('position', 'rotation', 'scale')
    
    def __init__(self, position: Vector3 = None, 
                 rotation: Vector3 = None, 
                 scale: Vector3 = None):
        self.position = position or Vector3()
        self.rotation = rotation or Vector3()
        self.scale = scale or Vector3(1, 1, 1)
    
    def matrix(self) -> Matrix4:
        """الحصول على مصفوفة التحويل"""
        # تطبيق القياس
        scale_mat = Matrix4.scaling(self.scale.x, self.scale.y, self.scale.z)
        
        # تطبيق الدوران
        rot_x = Matrix4.rotation_x(self.rotation.x)
        rot_y = Matrix4.rotation_y(self.rotation.y)
        rot_z = Matrix4.rotation_z(self.rotation.z)
        rot_mat = rot_z * rot_y * rot_x
        
        # تطبيق الإزاحة
        trans_mat = Matrix4.translation(self.position.x, self.position.y, self.position.z)
        
        return trans_mat * rot_mat * scale_mat
    
    def combine(self, other: 'Transform') -> 'Transform':
        """دمج تحويلين"""
        result = Transform()
        
        # دمج الإزاحة
        result.position = self.position + other.position
        
        # دمج الدوران
        result.rotation = Vector3(
            self.rotation.x + other.rotation.x,
            self.rotation.y + other.rotation.y,
            self.rotation.z + other.rotation.z
        )
        
        # دمج القياس
        result.scale = Vector3(
            self.scale.x * other.scale.x,
            self.scale.y * other.scale.y,
            self.scale.z * other.scale.z
        )
        
        return result
    
    def copy(self) -> 'Transform':
        """نسخ التحويل"""
        return Transform(
            Vector3(self.position.x, self.position.y, self.position.z),
            Vector3(self.rotation.x, self.rotation.y, self.rotation.z),
            Vector3(self.scale.x, self.scale.y, self.scale.z)
        )
    
    def __repr__(self) -> str:
        return (f"Transform(pos={self.position}, "
                f"rot={self.rotation}, scale={self.scale})")

# ============================================================================
# Time Management System
# ============================================================================

class Time:
    """نظام إدارة الوقت"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self.start_time = time.perf_counter()
        self.last_time = self.start_time
        self.current_time = self.start_time
        self.delta_time = 0.0
        self.fixed_delta_time = EngineConfig.FIXED_TIMESTEP
        self.time_scale = 1.0
        self.frame_count = 0
        self.fps = 0
        self.fps_buffer = deque(maxlen=60)
        self.paused = False
        self.game_time = 0.0
        self.real_time = 0.0
        
        self._initialized = True
    
    def update(self):
        """تحديث الوقت"""
        self.current_time = time.perf_counter()
        self.real_time = self.current_time - self.start_time
        
        if not self.paused:
            raw_delta = self.current_time - self.last_time
            self.delta_time = raw_delta * self.time_scale
            self.game_time += self.delta_time
            
            # حساب FPS
            self.fps_buffer.append(raw_delta)
            if raw_delta > 0:
                self.fps = 1.0 / raw_delta
            else:
                self.fps = 0
        
        self.last_time = self.current_time
        self.frame_count += 1
    
    def pause(self):
        """إيقاف الوقت"""
        self.paused = True
    
    def resume(self):
        """استئناف الوقت"""
        self.paused = False
    
    def set_time_scale(self, scale: float):
        """تعيين مقياس الوقت"""
        self.time_scale = max(0.0, scale)
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات الوقت"""
        avg_delta = sum(self.fps_buffer) / len(self.fps_buffer) if self.fps_buffer else 0
        avg_fps = 1.0 / avg_delta if avg_delta > 0 else 0
        
        return {
            'fps': self.fps,
            'avg_fps': avg_fps,
            'delta_time': self.delta_time,
            'fixed_delta_time': self.fixed_delta_time,
            'time_scale': self.time_scale,
            'game_time': self.game_time,
            'real_time': self.real_time,
            'frame_count': self.frame_count,
            'paused': self.paused
        }

# ============================================================================
# Main Engine Class
# ============================================================================

class GameEngine:
    """المحرك الرئيسي للألعاب"""
    
    def __init__(self):
        # إعداد المسارات
        self.paths = EngineConfig.initialize_paths()
        
        # إعداد التسجيل
        self.logger = Logger()
        self.logger.info(f"{EngineConfig.ENGINE_NAME} v{EngineConfig.ENGINE_VERSION}")
        self.logger.info("Initializing engine...")
        
        # الأنظمة الأساسية
        self.event_bus = EventBus()
        self.resource_manager = ResourceManager()
        self.entity_manager = EntityManager()
        self.time = Time()
        
        # حالة المحرك
        self.initialized = False
        self.running = False
        self.window = None
        self.screen = None
        self.clock = None
        
        # الأنظمة المسجلة
        self.systems = {}
        self.update_order = []
        
        # الإحصائيات
        self.statistics = {
            'frame_times': deque(maxlen=300),
            'memory_usage': deque(maxlen=300),
            'entity_counts': deque(maxlen=300)
        }
        
        # تتبع الذاكرة
        tracemalloc.start()
        
        # تسجيل معالجات النظام
        self._register_system_handlers()
    
    def _register_system_handlers(self):
        """تسجيل معالجات نظام المحرك"""
        # معالجات الأحداث الحرجة
        self.event_bus.subscribe(EventType.ENGINE_SHUTDOWN, self._on_shutdown, priority=100)
        self.event_bus.subscribe(EventType.ENGINE_INIT, self._on_init, priority=100)
    
    def _on_init(self, event: Event):
        """معالجة تهيئة المحرك"""
        self.logger.info("Engine initialization complete")
    
    def _on_shutdown(self, event: Event):
        """معالجة إيقاف المحرك"""
        self.logger.info("Engine shutdown requested")
        self.running = False
    
    def initialize(self, title: str = None, width: int = None, 
                  height: int = None, fullscreen: bool = False):
        """تهيئة المحرك"""
        if self.initialized:
            self.logger.warning("Engine already initialized")
            return
        
        try:
            # إعداد PyGame
            pygame.init()
            pygame.display.init()
            pygame.font.init()
            pygame.mixer.init(
                frequency=EngineConfig.AUDIO_FREQUENCY,
                size=-16,
                channels=EngineConfig.AUDIO_CHANNELS,
                buffer=EngineConfig.AUDIO_BUFFER_SIZE
            )
            
            # إعداد النافذة
            screen_width = width or EngineConfig.DEFAULT_SCREEN_WIDTH
            screen_height = height or EngineConfig.DEFAULT_SCREEN_HEIGHT
            
            flags = 0
            if fullscreen:
                flags |= pygame.FULLSCREEN
            if EngineConfig.MSAA_SAMPLES > 1:
                flags |= pygame.HWSURFACE | pygame.DOUBLEBUF
            
            self.window = pygame.display.set_mode(
                (screen_width, screen_height),
                flags
            )
            
            title = title or f"{EngineConfig.ENGINE_NAME} v{EngineConfig.ENGINE_VERSION}"
            pygame.display.set_caption(title)
            
            self.screen = self.window
            self.clock = pygame.time.Clock()
            
            # إرسال حدث التهيئة
            self.event_bus.dispatch(Event(
                EventType.ENGINE_INIT,
                {
                    'screen_width': screen_width,
                    'screen_height': screen_height,
                    'fullscreen': fullscreen
                }
            ))
            
            self.initialized = True
            self.logger.info(f"Window initialized: {screen_width}x{screen_height}")
            
        except Exception as e:
            self.logger.critical(f"Failed to initialize engine: {e}")
            raise
    
    def register_system(self, system, name: str, priority: int = 0):
        """تسجيل نظام"""
        if name in self.systems:
            self.logger.warning(f"System '{name}' already registered")
            return
        
        self.systems[name] = {
            'instance': system,
            'priority': priority,
            'enabled': True
        }
        
        # تحديث ترتيب التحديث
        self.update_order = sorted(
            self.systems.keys(),
            key=lambda x: self.systems[x]['priority'],
            reverse=True
        )
        
        self.logger.info(f"System '{name}' registered with priority {priority}")
    
    def unregister_system(self, name: str):
        """إلغاء تسجيل نظام"""
        if name in self.systems:
            del self.systems[name]
            self.update_order.remove(name)
            self.logger.info(f"System '{name}' unregistered")
    
    def enable_system(self, name: str):
        """تفعيل نظام"""
        if name in self.systems:
            self.systems[name]['enabled'] = True
    
    def disable_system(self, name: str):
        """تعطيل نظام"""
        if name in self.systems:
            self.systems[name]['enabled'] = False
    
    def run(self):
        """تشغيل الحلقة الرئيسية"""
        if not self.initialized:
            self.logger.error("Engine not initialized")
            return
        
        self.running = True
        self.logger.info("Starting main game loop")
        
        frame_start = time.perf_counter()
        
        while self.running:
            try:
                # معالجة الأحداث
                self._process_events()
                
                # تحديث الوقت
                self.time.update()
                
                # تحديث الأنظمة
                self._update_systems()
                
                # التصيير
                self._render()
                
                # تحديث الإحصائيات
                self._update_statistics(frame_start)
                
                # التحكم في معدل الإطارات
                self.clock.tick(EngineConfig.TARGET_FPS)
                
                # تحديث وقت بداية الإطار
                frame_start = time.perf_counter()
                
            except KeyboardInterrupt:
                self.logger.info("Interrupted by user")
                self.running = False
            except Exception as e:
                self.logger.error(f"Error in game loop: {e}")
                if self.logger:
                    self.logger.exception("Game loop exception")
        
        self.shutdown()
    
    def _process_events(self):
        """معالجة أحداث النظام"""
        # معالجة أحداث PyGame
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.event_bus.dispatch(Event(EventType.ENGINE_SHUTDOWN))
            elif event.type == pygame.KEYDOWN:
                self.event_bus.dispatch(Event(
                    EventType.KEY_DOWN,
                    {
                        'key': event.key,
                        'unicode': event.unicode,
                        'mod': event.mod
                    }
                ))
            elif event.type == pygame.KEYUP:
                self.event_bus.dispatch(Event(
                    EventType.KEY_UP,
                    {
                        'key': event.key,
                        'unicode': event.unicode,
                        'mod': event.mod
                    }
                ))
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.event_bus.dispatch(Event(
                    EventType.MOUSE_DOWN,
                    {
                        'button': event.button,
                        'pos': event.pos
                    }
                ))
            elif event.type == pygame.MOUSEBUTTONUP:
                self.event_bus.dispatch(Event(
                    EventType.MOUSE_UP,
                    {
                        'button': event.button,
                        'pos': event.pos
                    }
                ))
            elif event.type == pygame.MOUSEMOTION:
                self.event_bus.dispatch(Event(
                    EventType.MOUSE_MOVE,
                    {
                        'pos': event.pos,
                        'rel': event.rel,
                        'buttons': event.buttons
                    }
                ))
            elif event.type == pygame.MOUSEWHEEL:
                self.event_bus.dispatch(Event(
                    EventType.MOUSE_WHEEL,
                    {
                        'x': event.x,
                        'y': event.y
                    }
                ))
        
        # معالجة الأحداث المخصصة
        self.event_bus.process_events()
    
    def _update_systems(self):
        """تحديث الأنظمة المسجلة"""
        # إرسال حدث بداية الإطار
        self.event_bus.dispatch(Event(EventType.FRAME_START))
        
        # تحديث الأنظمة حسب الأولوية
        for system_name in self.update_order:
            system_info = self.systems[system_name]
            if system_info['enabled']:
                try:
                    system_info['instance'].update(self.time.delta_time)
                except Exception as e:
                    self.logger.error(f"Error updating system '{system_name}': {e}")
        
        # إرسال حدث نهاية الإطار
        self.event_bus.dispatch(Event(EventType.FRAME_END))
    
    def _render(self):
        """التصيير"""
        # مسح الشاشة
        self.screen.fill((0, 0, 0))
        
        # التصيير من الأنظمة
        for system_name in self.update_order:
            system_info = self.systems[system_name]
            if system_info['enabled'] and hasattr(system_info['instance'], 'render'):
                try:
                    system_info['instance'].render(self.screen)
                except Exception as e:
                    self.logger.error(f"Error rendering system '{system_name}': {e}")
        
        # تحديث العرض
        pygame.display.flip()
    
    def _update_statistics(self, frame_start: float):
        """تحديث الإحصائيات"""
        frame_time = time.perf_counter() - frame_start
        
        # وقت الإطار
        self.statistics['frame_times'].append(frame_time)
        
        # استخدام الذاكرة
        current, peak = tracemalloc.get_traced_memory()
        self.statistics['memory_usage'].append({
            'current_mb': current / 1024 / 1024,
            'peak_mb': peak / 1024 / 1024,
            'timestamp': time.time()
        })
        
        # عدد الكيانات
        entity_stats = self.entity_manager.get_statistics()
        self.statistics['entity_counts'].append({
            'total': entity_stats['total_entities'],
            'active': entity_stats['active_entities'],
            'timestamp': time.time()
        })
        
        # تسجيل الإحصائيات كل 60 إطار
        if self.time.frame_count % 60 == 0:
            self._log_statistics()
    
    def _log_statistics(self):
        """تسجيل الإحصائيات"""
        if not self.statistics['frame_times']:
            return
        
        # حساب متوسط وقت الإطار
        avg_frame_time = sum(self.statistics['frame_times']) / len(self.statistics['frame_times'])
        avg_fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
        
        # استخدام الذاكرة الحالي
        mem_usage = self.statistics['memory_usage'][-1] if self.statistics['memory_usage'] else {}
        
        # إحصائيات الكيانات
        entity_counts = self.statistics['entity_counts'][-1] if self.statistics['entity_counts'] else {}
        
        # تسجيل الإحصائيات
        self.logger.debug(
            f"Stats - FPS: {avg_fps:.1f}, "
            f"Frame: {avg_frame_time*1000:.2f}ms, "
            f"Memory: {mem_usage.get('current_mb', 0):.1f}MB, "
            f"Entities: {entity_counts.get('total', 0)}"
        )
    
    def shutdown(self):
        """إيقاف المحرك"""
        self.logger.info("Shutting down engine...")
        
        # إرسال حدث الإيقاف
        self.event_bus.dispatch(Event(EventType.ENGINE_SHUTDOWN))
        
        # إيقاف الأنظمة
        for system_name, system_info in self.systems.items():
            if hasattr(system_info['instance'], 'shutdown'):
                try:
                    system_info['instance'].shutdown()
                except Exception as e:
                    self.logger.error(f"Error shutting down system '{system_name}': {e}")
        
        # تنظيف المديرين
        self.resource_manager = None
        self.entity_manager.clear()
        
        # إيقاف PyGame
        pygame.mixer.quit()
        pygame.font.quit()
        pygame.display.quit()
        pygame.quit()
        
        # إيقاف التسجيل
        self.logger.shutdown()
        
        # إيقاف تتبع الذاكرة
        tracemalloc.stop()
        
        self.logger.info("Engine shutdown complete")
        print(f"\n{EngineConfig.ENGINE_NAME} shutdown successfully.")
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """الحصول على تشخيصات النظام"""
        # إحصائيات المحرك
        engine_stats = {
            'engine_version': EngineConfig.ENGINE_VERSION,
            'running': self.running,
            'initialized': self.initialized,
            'system_count': len(self.systems),
            'registered_systems': list(self.systems.keys())
        }
        
        # إحصائيات الوقت
        time_stats = self.time.get_statistics()
        
        # إحصائيات الكيانات
        entity_stats = self.entity_manager.get_statistics()
        
        # إحصائيات الموارد
        resource_stats = self.resource_manager.get_statistics()
        
        # إحصائيات الأحداث
        event_stats = self.event_bus.get_statistics()
        
        # جمع كل الإحصائيات
        return {
            'engine': engine_stats,
            'time': time_stats,
            'entities': entity_stats,
            'resources': resource_stats,
            'events': event_stats,
            'statistics': {
                'avg_frame_time': sum(self.statistics['frame_times']) / len(self.statistics['frame_times']) 
                    if self.statistics['frame_times'] else 0,
                'frame_time_samples': len(self.statistics['frame_times'])
            }
        }