"""
GameEnginePro - AI Module
نظام الذكاء الاصطناعي المتقدم
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Union, Callable
from enum import Enum, auto
from dataclasses import dataclass, field
import math
import random
import heapq
from collections import defaultdict, deque

# ============================================================================
# AI Types
# ============================================================================

class AIState(Enum):
    """حالات الذكاء الاصطناعي"""
    IDLE = auto()
    PATROLLING = auto()
    CHASING = auto()
    ATTACKING = auto()
    FLEEING = auto()
    SEARCHING = auto()
    DEAD = auto()

class AISensorType(Enum):
    """أنواع أجهزة الاستشعار"""
    VISION = auto()
    HEARING = auto()
    TOUCH = auto()
    SMELL = auto()

class AIBehavior(Enum):
    """أنواع السلوك"""
    PASSIVE = auto()
    AGGRESSIVE = auto()
    DEFENSIVE = auto()
    NEUTRAL = auto()
    BOSS = auto()

# ============================================================================
# Pathfinding
# ============================================================================

class Node:
    """عقدة في الرسم البياني"""
    
    __slots__ = ('position', 'g', 'h', 'f', 'parent', 'walkable')
    
    def __init__(self, position: Tuple[int, int, int]):
        self.position = position
        self.g = 0  # تكلفة من البداية
        self.h = 0  # تكلفة تقديرية للهدف
        self.f = 0  # التكلفة الكلية
        self.parent = None
        self.walkable = True
    
    def __lt__(self, other):
        return self.f < other.f
    
    def __eq__(self, other):
        return self.position == other.position

class Grid:
    """شبكة للبحث عن المسار"""
    
    def __init__(self, width: int, height: int, depth: int = 1):
        self.width = width
        self.height = height
        self.depth = depth
        self.nodes = {}
        self._initialize_grid()
    
    def _initialize_grid(self):
        """تهيئة الشبكة"""
        for z in range(self.depth):
            for y in range(self.height):
                for x in range(self.width):
                    self.nodes[(x, y, z)] = Node((x, y, z))
    
    def get_node(self, position: Tuple[int, int, int]) -> Optional[Node]:
        """الحصول على عقدة"""
        return self.nodes.get(position)
    
    def get_neighbors(self, node: Node, allow_diagonal: bool = True) -> List[Node]:
        """الحصول على الجيران"""
        neighbors = []
        x, y, z = node.position
        
        # الاتجاهات الأساسية
        directions = [
            (1, 0, 0), (-1, 0, 0),  # يمين، يسار
            (0, 1, 0), (0, -1, 0),  # أمام، خلف
            (0, 0, 1), (0, 0, -1)   # أعلى، أسفل
        ]
        
        # الاتجاهات القطرية
        if allow_diagonal:
            diagonal_directions = [
                (1, 1, 0), (-1, 1, 0), (1, -1, 0), (-1, -1, 0),
                (1, 0, 1), (-1, 0, 1), (1, 0, -1), (-1, 0, -1),
                (0, 1, 1), (0, -1, 1), (0, 1, -1), (0, -1, -1)
            ]
            directions.extend(diagonal_directions)
        
        for dx, dy, dz in directions:
            neighbor_pos = (x + dx, y + dy, z + dz)
            neighbor = self.get_node(neighbor_pos)
            if neighbor and neighbor.walkable:
                neighbors.append(neighbor)
        
        return neighbors
    
    def set_walkable(self, position: Tuple[int, int, int], walkable: bool):
        """تعيين إمكانية المشي"""
        node = self.get_node(position)
        if node:
            node.walkable = walkable
    
    def clear(self):
        """مسح الشبكة"""
        for node in self.nodes.values():
            node.g = 0
            node.h = 0
            node.f = 0
            node.parent = None

class AStar:
    """خوارزمية A* للبحث عن المسار"""
    
    @staticmethod
    def find_path(grid: Grid, start: Tuple[int, int, int], 
                  end: Tuple[int, int, int]) -> List[Tuple[int, int, int]]:
        """البحث عن مسار"""
        start_node = grid.get_node(start)
        end_node = grid.get_node(end)
        
        if not start_node or not end_node or not end_node.walkable:
            return []
        
        open_list = []
        closed_set = set()
        
        heapq.heappush(open_list, start_node)
        
        while open_list:
            current_node = heapq.heappop(open_list)
            closed_set.add(current_node.position)
            
            if current_node == end_node:
                path = []
                while current_node:
                    path.append(current_node.position)
                    current_node = current_node.parent
                return path[::-1]
            
            neighbors = grid.get_neighbors(current_node)
            for neighbor in neighbors:
                if neighbor.position in closed_set:
                    continue
                
                # تكلفة الحركة
                move_cost = AStar._get_move_cost(current_node.position, neighbor.position)
                tentative_g = current_node.g + move_cost
                
                if neighbor not in open_list or tentative_g < neighbor.g:
                    neighbor.g = tentative_g
                    neighbor.h = AStar._heuristic(neighbor.position, end_node.position)
                    neighbor.f = neighbor.g + neighbor.h
                    neighbor.parent = current_node
                    
                    if neighbor not in open_list:
                        heapq.heappush(open_list, neighbor)
        
        return []
    
    @staticmethod
    def _get_move_cost(pos_a: Tuple[int, int, int], 
                      pos_b: Tuple[int, int, int]) -> float:
        """الحصول على تكلفة الحركة"""
        dx = abs(pos_a[0] - pos_b[0])
        dy = abs(pos_a[1] - pos_b[1])
        dz = abs(pos_a[2] - pos_b[2])
        
        # إذا كانت الحركة قطرية، التكلفة √2 أو √3
        if dx + dy + dz == 1:
            return 1.0  # حركة مستقيمة
        elif dx + dy + dz == 2 and dx != 2 and dy != 2 and dz != 2:
            return 1.414  # √2 للقطر في مستوى
        else:
            return 1.732  # √3 للقطر في الفضاء
    
    @staticmethod
    def _heuristic(pos_a: Tuple[int, int, int], 
                  pos_b: Tuple[int, int, int]) -> float:
        """دالة الاستدلال (مسافة مانهاتن)"""
        dx = abs(pos_a[0] - pos_b[0])
        dy = abs(pos_a[1] - pos_b[1])
        dz = abs(pos_a[2] - pos_b[2])
        return dx + dy + dz

class NavigationMesh:
    """شبكة الملاحة"""
    
    def __init__(self):
        self.vertices = []
        self.polygons = []
        self.connections = defaultdict(list)
    
    def build_from_mesh(self, mesh_vertices, mesh_indices):
        """بناء شبكة ملاحة من شبكة رسومية"""
        # هذا تنفيذ مبسط
        # في التنفيذ الحقيقي، سيتم استخدام خوارزميات مثل Recast
        pass
    
    def find_path(self, start: np.ndarray, end: np.ndarray) -> List[np.ndarray]:
        """البحث عن مسار في شبكة الملاحة"""
        # هذا تنفيذ مبسط
        return [start, end]

# ============================================================================
# Finite State Machine
# ============================================================================

class State:
    """حالة في آلة الحالة المحدودة"""
    
    def __init__(self, name: str):
        self.name = name
        self.enter_callbacks = []
        self.update_callbacks = []
        self.exit_callbacks = []
    
    def enter(self, entity, ai_system):
        """الدخول إلى الحالة"""
        for callback in self.enter_callbacks:
            callback(entity, ai_system)
    
    def update(self, entity, ai_system, delta_time: float):
        """تحديث الحالة"""
        for callback in self.update_callbacks:
            callback(entity, ai_system, delta_time)
    
    def exit(self, entity, ai_system):
        """الخروج من الحالة"""
        for callback in self.exit_callbacks:
            callback(entity, ai_system)

class Transition:
    """انتقال بين حالات"""
    
    def __init__(self, from_state: str, to_state: str, condition: Callable):
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition

class FiniteStateMachine:
    """آلة الحالة المحدودة"""
    
    def __init__(self):
        self.states: Dict[str, State] = {}
        self.transitions: Dict[str, List[Transition]] = defaultdict(list)
        self.current_state: Optional[State] = None
        self.previous_state: Optional[State] = None
    
    def add_state(self, state: State):
        """إضافة حالة"""
        self.states[state.name] = state
    
    def add_transition(self, transition: Transition):
        """إضافة انتقال"""
        self.transitions[transition.from_state].append(transition)
    
    def set_initial_state(self, state_name: str):
        """تعيين الحالة الأولية"""
        if state_name in self.states:
            self.current_state = self.states[state_name]
    
    def update(self, entity, ai_system, delta_time: float):
        """تحديث آلة الحالة"""
        if not self.current_state:
            return
        
        # التحقق من الانتقالات
        current_state_name = self.current_state.name
        for transition in self.transitions.get(current_state_name, []):
            if transition.condition(entity, ai_system):
                self.change_state(transition.to_state, entity, ai_system)
                break
        
        # تحديث الحالة الحالية
        if self.current_state:
            self.current_state.update(entity, ai_system, delta_time)
    
    def change_state(self, new_state_name: str, entity, ai_system):
        """تغيير الحالة"""
        if new_state_name not in self.states:
            return
        
        if self.current_state:
            self.current_state.exit(entity, ai_system)
            self.previous_state = self.current_state
        
        self.current_state = self.states[new_state_name]
        self.current_state.enter(entity, ai_system)

# ============================================================================
# Behavior Tree
# ============================================================================

class NodeStatus(Enum):
    """حالة عقدة شجرة السلوك"""
    SUCCESS = auto()
    FAILURE = auto()
    RUNNING = auto()

class BehaviorNode:
    """عقدة شجرة السلوك"""
    
    def __init__(self, name: str = ""):
        self.name = name
        self.children = []
        self.status = NodeStatus.FAILURE
    
    def add_child(self, child: 'BehaviorNode'):
        """إضافة طفل"""
        self.children.append(child)
    
    def execute(self, entity, ai_system, delta_time: float) -> NodeStatus:
        """تنفيذ العقدة"""
        return NodeStatus.SUCCESS

class SequenceNode(BehaviorNode):
    """عقدة تسلسل (تنفيذ جميع الأطفال بالتسلسل)"""
    
    def execute(self, entity, ai_system, delta_time: float) -> NodeStatus:
        for child in self.children:
            status = child.execute(entity, ai_system, delta_time)
            if status != NodeStatus.SUCCESS:
                return status
        return NodeStatus.SUCCESS

class SelectorNode(BehaviorNode):
    """عقدة محدد (تنفيذ حتى نجاح طفل)"""
    
    def execute(self, entity, ai_system, delta_time: float) -> NodeStatus:
        for child in self.children:
            status = child.execute(entity, ai_system, delta_time)
            if status != NodeStatus.FAILURE:
                return status
        return NodeStatus.FAILURE

class ParallelNode(BehaviorNode):
    """عقدة متوازية (تنفيذ جميع الأطفال بالتوازي)"""
    
    def execute(self, entity, ai_system, delta_time: float) -> NodeStatus:
        success_count = 0
        failure_count = 0
        
        for child in self.children:
            status = child.execute(entity, ai_system, delta_time)
            if status == NodeStatus.SUCCESS:
                success_count += 1
            elif status == NodeStatus.FAILURE:
                failure_count += 1
        
        if success_count == len(self.children):
            return NodeStatus.SUCCESS
        elif failure_count > 0:
            return NodeStatus.FAILURE
        else:
            return NodeStatus.RUNNING

class ConditionNode(BehaviorNode):
    """عقدة شرط"""
    
    def __init__(self, name: str, condition: Callable):
        super().__init__(name)
        self.condition = condition
    
    def execute(self, entity, ai_system, delta_time: float) -> NodeStatus:
        if self.condition(entity, ai_system):
            return NodeStatus.SUCCESS
        return NodeStatus.FAILURE

class ActionNode(BehaviorNode):
    """عقدة إجراء"""
    
    def __init__(self, name: str, action: Callable):
        super().__init__(name)
        self.action = action
    
    def execute(self, entity, ai_system, delta_time: float) -> NodeStatus:
        return self.action(entity, ai_system, delta_time)

class BehaviorTree:
    """شجرة السلوك"""
    
    def __init__(self, root: BehaviorNode = None):
        self.root = root
    
    def update(self, entity, ai_system, delta_time: float) -> NodeStatus:
        """تحديث شجرة السلوك"""
        if self.root:
            return self.root.execute(entity, ai_system, delta_time)
        return NodeStatus.FAILURE

# ============================================================================
# Sensors
# ============================================================================

@dataclass
class SensorData:
    """بيانات المستشعر"""
    type: AISensorType
    position: np.ndarray
    strength: float
    source_entity_id: int
    timestamp: float

class VisionSensor:
    """مستشعر الرؤية"""
    
    def __init__(self, range: float = 10.0, fov: float = 90.0):
        self.range = range
        self.fov = fov
        self.detected_entities = []
    
    def update(self, entity, ai_system, delta_time: float):
        """تحديث المستشعر"""
        self.detected_entities.clear()
        
        entity_pos = entity.get_component(ComponentType.TRANSFORM).position
        entity_pos_np = np.array([entity_pos.x, entity_pos.y, entity_pos.z])
        entity_forward = ai_system.get_entity_forward(entity.id)
        
        # التحقق من جميع الكيانات
        for other_entity in ai_system.get_all_entities():
            if other_entity.id == entity.id:
                continue
            
            other_pos = other_entity.get_component(ComponentType.TRANSFORM).position
            other_pos_np = np.array([other_pos.x, other_pos.y, other_pos.z])
            
            # حساب المسافة
            direction = other_pos_np - entity_pos_np
            distance = np.linalg.norm(direction)
            
            if distance > self.range:
                continue
            
            # حساب الزاوية
            if np.linalg.norm(direction) > 0:
                direction = direction / distance
                dot_product = np.dot(entity_forward, direction)
                angle = math.degrees(math.acos(max(-1, min(1, dot_product))))
                
                if angle <= self.fov / 2:
                    # التحقق من العوائق
                    if not ai_system.has_line_of_sight(entity.id, other_entity.id):
                        continue
                    
                    self.detected_entities.append({
                        'entity': other_entity,
                        'distance': distance,
                        'angle': angle
                    })
    
    def can_see_entity(self, target_entity_id: int) -> bool:
        """التحقق من رؤية كيان"""
        for detection in self.detected_entities:
            if detection['entity'].id == target_entity_id:
                return True
        return False

class HearingSensor:
    """مستشعر السمع"""
    
    def __init__(self, range: float = 20.0):
        self.range = range
        self.sounds = []
    
    def add_sound(self, position: np.ndarray, loudness: float, source_entity_id: int):
        """إضافة صوت"""
        self.sounds.append({
            'position': position,
            'loudness': loudness,
            'source_entity_id': source_entity_id,
            'timestamp': time.time()
        })
    
    def update(self, entity, ai_system, delta_time: float):
        """تحديث المستشعر"""
        entity_pos = entity.get_component(ComponentType.TRANSFORM).position
        entity_pos_np = np.array([entity_pos.x, entity_pos.y, entity_pos.z])
        
        # إزالة الأصوات القديمة
        current_time = time.time()
        self.sounds = [s for s in self.sounds 
                      if current_time - s['timestamp'] < 5.0]  # 5 ثواني
        
        # التحقق من الأصوات القريبة
        for sound in self.sounds:
            direction = sound['position'] - entity_pos_np
            distance = np.linalg.norm(direction)
            
            # حساب شدة الصوت بعد التوهين
            effective_loudness = sound['loudness'] / max(1, distance)
            
            if effective_loudness > 0.1:  # عتبة السمع
                # يمكن للكيان سماع الصوت
                ai_system.process_sound(entity, sound)

# ============================================================================
# AI Agent
# ============================================================================

@dataclass
class AIAgent:
    """وكيل الذكاء الاصطناعي"""
    entity_id: int
    behavior: AIBehavior = AIBehavior.NEUTRAL
    fsm: FiniteStateMachine = field(default_factory=FiniteStateMachine)
    behavior_tree: BehaviorTree = field(default_factory=BehaviorTree)
    vision_sensor: VisionSensor = field(default_factory=lambda: VisionSensor())
    hearing_sensor: HearingSensor = field(default_factory=lambda: HearingSensor())
    
    # الذاكرة
    memory: Dict[str, Any] = field(default_factory=dict)
    known_entities: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    
    # الإحصائيات
    stats: Dict[str, Any] = field(default_factory=lambda: {
        'time_in_state': defaultdict(float),
        'transitions': 0,
        'targets_detected': 0,
        'attacks_made': 0
    })
    
    def update(self, ai_system, delta_time: float):
        """تحديث الوكيل"""
        # تحديث المستشعرات
        entity = ai_system.get_entity(self.entity_id)
        if not entity:
            return
        
        self.vision_sensor.update(entity, ai_system, delta_time)
        self.hearing_sensor.update(entity, ai_system, delta_time)
        
        # تحديث آلة الحالة
        self.fsm.update(entity, ai_system, delta_time)
        
        # تحديث شجرة السلوك (إذا لم تستخدم FSM)
        if not self.fsm.current_state:
            self.behavior_tree.update(entity, ai_system, delta_time)
        
        # تحديث الإحصائيات
        if self.fsm.current_state:
            state_name = self.fsm.current_state.name
            self.stats['time_in_state'][state_name] += delta_time
    
    def remember_entity(self, entity_id: int, info: Dict[str, Any]):
        """تذكر كيان"""
        self.known_entities[entity_id] = {
            **info,
            'last_seen': time.time()
        }
    
    def forget_entity(self, entity_id: int):
        """نسيان كيان"""
        if entity_id in self.known_entities:
            del self.known_entities[entity_id]
    
    def get_known_entity_info(self, entity_id: int) -> Optional[Dict[str, Any]]:
        """الحصول على معلومات عن كيان معروف"""
        return self.known_entities.get(entity_id)
    
    def get_nearest_known_enemy(self) -> Optional[int]:
        """الحصول على أقرب عدو معروف"""
        entity = self.get_entity()
        if not entity:
            return None
        
        entity_pos = entity.get_component(ComponentType.TRANSFORM).position
        entity_pos_np = np.array([entity_pos.x, entity_pos.y, entity_pos.z])
        
        nearest_id = None
        nearest_distance = float('inf')
        
        for known_id, info in self.known_entities.items():
            if info.get('is_enemy', False):
                known_pos = info.get('last_position')
                if known_pos is not None:
                    distance = np.linalg.norm(entity_pos_np - known_pos)
                    if distance < nearest_distance:
                        nearest_distance = distance
                        nearest_id = known_id
        
        return nearest_id
    
    def get_entity(self):
        """الحصول على الكيان"""
        return ai_system.get_entity(self.entity_id)  # يجب تمرير ai_system

# ============================================================================
# AI System
# ============================================================================

class AISystem:
    """نظام الذكاء الاصطناعي"""
    
    def __init__(self, engine):
        self.engine = engine
        self.agents: Dict[int, AIAgent] = {}
        self.nav_mesh = NavigationMesh()
        self.pathfinding_grid = None
        
        # التسجيلات
        self.sound_events = []
        self.vision_events = []
        
        # الإحصائيات
        self.stats = {
            'total_agents': 0,
            'active_agents': 0,
            'pathfinding_requests': 0,
            'sensor_updates': 0
        }
    
    def initialize(self, grid_width: int = 100, grid_height: int = 100):
        """تهيئة النظام"""
        self.pathfinding_grid = Grid(grid_width, grid_height)
        
        # تسجيل سلوكيات افتراضية
        self._register_default_behaviors()
        
        print("AI system initialized")
        return True
    
    def _register_default_behaviors(self):
        """تسجيل السلوكيات الافتراضية"""
        # سلوك الحراسة
        guard_behavior = self._create_guard_behavior()
        
        # سلوك المهاجم
        attacker_behavior = self._create_attacker_behavior()
        
        # سلوك الرئيس
        boss_behavior = self._create_boss_behavior()
    
    def _create_guard_behavior(self) -> BehaviorTree:
        """إنشاء سلوك حارس"""
        root = SequenceNode("Guard Behavior")
        
        # التحقق من وجود أعداء
        check_enemies = ConditionNode("Check Enemies", 
                                     lambda e, s: s.has_detected_enemies(e.id))
        
        # مهاجمة العدو
        attack_enemy = ActionNode("Attack Enemy", 
                                 lambda e, s: s.attack_nearest_enemy(e.id))
        
        # الدوريات
        patrol = SequenceNode("Patrol")
        choose_patrol_point = ActionNode("Choose Patrol Point",
                                        lambda e, s: s.choose_patrol_point(e.id))
        move_to_point = ActionNode("Move To Point",
                                  lambda e, s: s.move_to_patrol_point(e.id))
        
        patrol.add_child(choose_patrol_point)
        patrol.add_child(move_to_point)
        
        # اختيار السلوك
        selector = SelectorNode("Behavior Selector")
        selector.add_child(check_enemies)
        selector.add_child(attack_enemy)
        selector.add_child(patrol)
        
        root.add_child(selector)
        return BehaviorTree(root)
    
    def _create_attacker_behavior(self) -> FiniteStateMachine:
        """إنشاء سلوك مهاجم"""
        fsm = FiniteStateMachine()
        
        # الحالات
        idle = State("Idle")
        patrol = State("Patrol")
        chase = State("Chase")
        attack = State("Attack")
        flee = State("Flee")
        
        # إضافة الحالات
        fsm.add_state(idle)
        fsm.add_state(patrol)
        fsm.add_state(chase)
        fsm.add_state(attack)
        fsm.add_state(flee)
        
        # الانتقالات
        fsm.add_transition(Transition("Idle", "Patrol",
                                     lambda e, s: s.should_start_patrol(e.id)))
        fsm.add_transition(Transition("Patrol", "Chase",
                                     lambda e, s: s.has_detected_enemies(e.id)))
        fsm.add_transition(Transition("Chase", "Attack",
                                     lambda e, s: s.is_in_attack_range(e.id)))
        fsm.add_transition(Transition("Attack", "Chase",
                                     lambda e, s: not s.is_in_attack_range(e.id)))
        fsm.add_transition(Transition("Attack", "Flee",
                                     lambda e, s: s.is_low_health(e.id)))
        fsm.add_transition(Transition("Chase", "Flee",
                                     lambda e, s: s.is_low_health(e.id)))
        fsm.add_transition(Transition("Flee", "Patrol",
                                     lambda e, s: not s.has_detected_enemies(e.id)))
        
        fsm.set_initial_state("Idle")
        return fsm
    
    def _create_boss_behavior(self):
        """إنشاء سلوك رئيس"""
        # سلوك أكثر تعقيداً للمراحل النهائية
        pass
    
    def add_agent(self, entity_id: int, behavior: AIBehavior = AIBehavior.NEUTRAL):
        """إضافة وكيل"""
        if entity_id in self.agents:
            return
        
        agent = AIAgent(entity_id=entity_id, behavior=behavior)
        
        # تعيين السلوك المناسب
        if behavior == AIBehavior.AGGRESSIVE:
            agent.fsm = self._create_attacker_behavior()
        elif behavior == AIBehavior.DEFENSIVE:
            agent.behavior_tree = self._create_guard_behavior()
        
        self.agents[entity_id] = agent
        self.stats['total_agents'] += 1
    
    def remove_agent(self, entity_id: int):
        """إزالة وكيل"""
        if entity_id in self.agents:
            del self.agents[entity_id]
            self.stats['total_agents'] -= 1
    
    def update(self, delta_time: float):
        """تحديث النظام"""
        self.stats['active_agents'] = 0
        
        for agent in list(self.agents.values()):
            entity = self.get_entity(agent.entity_id)
            if entity and entity.active:
                agent.update(self, delta_time)
                self.stats['active_agents'] += 1
        
        # تحديث الإحصائيات
        self.stats['sensor_updates'] = sum(
            1 for a in self.agents.values() 
            if self.get_entity(a.entity_id) and self.get_entity(a.entity_id).active
        )
    
    def get_entity(self, entity_id: int):
        """الحصول على كيان"""
        return self.engine.entity_manager.get_entity(entity_id)
    
    def get_entity_forward(self, entity_id: int) -> np.ndarray:
        """الحصول على متجه الأمام للكيان"""
        entity = self.get_entity(entity_id)
        if not entity:
            return np.array([0, 0, 1], dtype='f4')
        
        # هذا تنفيذ مبسط
        # في التنفيذ الحقيقي، سيتم حسابها من التحويل
        return np.array([0, 0, 1], dtype='f4')
    
    def has_line_of_sight(self, entity_id: int, target_id: int) -> bool:
        """التحقق من وجود خط رؤية"""
        entity = self.get_entity(entity_id)
        target = self.get_entity(target_id)
        
        if not entity or not target:
            return False
        
        entity_pos = entity.get_component(ComponentType.TRANSFORM).position
        target_pos = target.get_component(ComponentType.TRANSFORM).position
        
        # استخدام نظام الفيزياء للتحقق من العوائق
        physics_system = self.engine.systems.get('physics')
        if physics_system:
            hit = physics_system.raycast_from_entity(
                entity_id,
                Vector3(target_pos.x - entity_pos.x,
                       target_pos.y - entity_pos.y,
                       target_pos.z - entity_pos.z).normalized(),
                100.0
            )
            
            if hit and hit['entity_id'] == target_id:
                return True
        
        return False
    
    def has_detected_enemies(self, entity_id: int) -> bool:
        """التحقق من اكتشاف أعداء"""
        if entity_id not in self.agents:
            return False
        
        agent = self.agents[entity_id]
        return len(agent.vision_sensor.detected_entities) > 0
    
    def is_in_attack_range(self, entity_id: int) -> bool:
        """التحقق من كون الكيان في مدى الهجوم"""
        if entity_id not in self.agents:
            return False
        
        agent = self.agents[entity_id]
        if not agent.vision_sensor.detected_entities:
            return False
        
        # التحقق من أقرب كيان
        nearest = min(agent.vision_sensor.detected_entities,
                     key=lambda x: x['distance'])
        
        # مدى الهجوم الافتراضي: 2 وحدة
        return nearest['distance'] <= 2.0
    
    def is_low_health(self, entity_id: int) -> bool:
        """التحقق من كون صحة الكيان منخفضة"""
        entity = self.get_entity(entity_id)
        if not entity:
            return False
        
        # هذا يتطلب نظام صحة للكيانات
        return False
    
    def should_start_patrol(self, entity_id: int) -> bool:
        """التحقق من وجوب بدء الدوريات"""
        # بدء الدوريات بعد 5 ثواني من الخمول
        if entity_id not in self.agents:
            return False
        
        agent = self.agents[entity_id]
        idle_time = agent.stats['time_in_state'].get('Idle', 0)
        return idle_time > 5.0
    
    def attack_nearest_enemy(self, entity_id: int) -> NodeStatus:
        """مهاجمة أقرب عدو"""
        if entity_id not in self.agents:
            return NodeStatus.FAILURE
        
        agent = self.agents[entity_id]
        if not agent.vision_sensor.detected_entities:
            return NodeStatus.FAILURE
        
        # العثور على أقرب كيان
        nearest = min(agent.vision_sensor.detected_entities,
                     key=lambda x: x['distance'])
        
        # تنفيذ الهجوم
        target_entity = nearest['entity']
        
        # إرسال حدث الهجوم
        self.engine.event_bus.dispatch(Event(
            EventType.ENTITY_ATTACK,  # يحتاج إلى تعريف
            {
                'attacker_id': entity_id,
                'target_id': target_entity.id,
                'damage': 10.0  # قيمة افتراضية
            }
        ))
        
        agent.stats['attacks_made'] += 1
        return NodeStatus.SUCCESS
    
    def choose_patrol_point(self, entity_id: int) -> NodeStatus:
        """اختيار نقطة دورية"""
        if entity_id not in self.agents:
            return NodeStatus.FAILURE
        
        agent = self.agents[entity_id]
        
        # اختيار نقطة عشوائية ضمن نطاق
        entity = self.get_entity(entity_id)
        if not entity:
            return NodeStatus.FAILURE
        
        entity_pos = entity.get_component(ComponentType.TRANSFORM).position
        
        # نقطة عشوائية في دائرة نصف قطرها 10 وحدة
        angle = random.uniform(0, 2 * math.pi)
        distance = random.uniform(5, 10)
        
        patrol_point = (
            entity_pos.x + math.cos(angle) * distance,
            entity_pos.y,
            entity_pos.z + math.sin(angle) * distance
        )
        
        agent.memory['patrol_point'] = patrol_point
        return NodeStatus.SUCCESS
    
    def move_to_patrol_point(self, entity_id: int) -> NodeStatus:
        """التحرك إلى نقطة دورية"""
        if entity_id not in self.agents:
            return NodeStatus.FAILURE
        
        agent = self.agents[entity_id]
        if 'patrol_point' not in agent.memory:
            return NodeStatus.FAILURE
        
        entity = self.get_entity(entity_id)
        if not entity:
            return NodeStatus.FAILURE
        
        patrol_point = agent.memory['patrol_point']
        entity_pos = entity.get_component(ComponentType.TRANSFORM).position
        
        # حساب الاتجاه
        dx = patrol_point[0] - entity_pos.x
        dz = patrol_point[2] - entity_pos.z
        distance = math.sqrt(dx * dx + dz * dz)
        
        if distance < 1.0:  # وصل إلى النقطة
            return NodeStatus.SUCCESS
        
        # التحرك نحو النقطة
        # هذا يتطلب نظام حركة للكيانات
        return NodeStatus.RUNNING
    
    def find_path(self, start: np.ndarray, end: np.ndarray) -> List[np.ndarray]:
        """البحث عن مسار"""
        self.stats['pathfinding_requests'] += 1
        
        if self.pathfinding_grid:
            # تحويل الإحداثيات إلى خلايا الشبكة
            start_cell = (int(start[0]), int(start[1]), 0)
            end_cell = (int(end[0]), int(end[1]), 0)
            
            path_cells = AStar.find_path(self.pathfinding_grid, start_cell, end_cell)
            
            # تحويل الخلايا إلى إحداثيات عالمية
            path = [np.array([cell[0] + 0.5, start[1], cell[1] + 0.5], dtype='f4')
                   for cell in path_cells]
            return path
        
        # استخدام شبكة الملاحة إذا كانت متوفرة
        return self.nav_mesh.find_path(start, end)
    
    def process_sound(self, entity, sound_data):
        """معالجة صوت"""
        self.sound_events.append({
            'entity_id': entity.id,
            'sound_data': sound_data,
            'timestamp': time.time()
        })
    
    def shutdown(self):
        """إيقاف النظام"""
        self.agents.clear()
        print("AI system shutdown")
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات النظام"""
        # إحصائيات الوكيل
        agent_stats = []
        for agent in self.agents.values():
            entity = self.get_entity(agent.entity_id)
            if entity:
                agent_stats.append({
                    'entity_id': agent.entity_id,
                    'behavior': agent.behavior.name,
                    'current_state': agent.fsm.current_state.name if agent.fsm.current_state else 'None',
                    'known_entities': len(agent.known_entities),
                    'detected_entities': len(agent.vision_sensor.detected_entities)
                })
        
        return {
            **self.stats,
            'agent_details': agent_stats,
            'sound_events': len(self.sound_events),
            'vision_events': len(self.vision_events)
        }