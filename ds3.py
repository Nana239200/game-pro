"""
GameEnginePro - Physics Module
نظام الفيزياء المتقدم
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Union
from enum import Enum, auto
from dataclasses import dataclass, field
import math
import itertools
from collections import defaultdict

# ============================================================================
# Physics Types
# ============================================================================

class ShapeType(Enum):
    """أنواع الأشكال الفيزيائية"""
    SPHERE = auto()
    BOX = auto()
    CAPSULE = auto()
    CYLINDER = auto()
    MESH = auto()
    PLANE = auto()

class BodyType(Enum):
    """أنواع الأجسام"""
    STATIC = auto()     # ثابت
    DYNAMIC = auto()    # ديناميكي
    KINEMATIC = auto()  # حركي

@dataclass
class PhysicsMaterial:
    """مادة فيزيائية"""
    name: str = "default"
    density: float = 1.0
    friction: float = 0.5
    restitution: float = 0.2
    bounciness: float = 0.0

@dataclass
class CollisionShape:
    """شكل التصادم"""
    shape_type: ShapeType
    size: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    material: PhysicsMaterial = field(default_factory=PhysicsMaterial)
    
    def get_bounding_sphere(self):
        """الحصول على كرة محيطة"""
        if self.shape_type == ShapeType.SPHERE:
            return self.size[0]
        elif self.shape_type == ShapeType.BOX:
            return math.sqrt(sum(s * s for s in self.size)) / 2
        elif self.shape_type == ShapeType.CAPSULE:
            return max(self.size[0], self.size[1]) + self.size[2]
        else:
            return max(self.size)

@dataclass
class RigidBody:
    """جسم صلب"""
    position: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype='f4'))
    rotation: np.ndarray = field(default_factory=lambda: np.identity(3, dtype='f4'))
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype='f4'))
    angular_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype='f4'))
    force: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype='f4'))
    torque: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype='f4'))
    
    mass: float = 1.0
    inverse_mass: float = 1.0
    inertia: np.ndarray = field(default_factory=lambda: np.identity(3, dtype='f4'))
    inverse_inertia: np.ndarray = field(default_factory=lambda: np.identity(3, dtype='f4'))
    
    body_type: BodyType = BodyType.DYNAMIC
    shapes: List[CollisionShape] = field(default_factory=list)
    material: PhysicsMaterial = field(default_factory=PhysicsMaterial)
    
    linear_damping: float = 0.01
    angular_damping: float = 0.01
    gravity_scale: float = 1.0
    
    sleeping: bool = False
    awake_timer: float = 0.0
    
    def __post_init__(self):
        self.update_inertia()
    
    def update_inertia(self):
        """تحديث العطالة"""
        if self.body_type == BodyType.STATIC:
            self.inverse_mass = 0.0
            self.inverse_inertia = np.zeros((3, 3), dtype='f4')
        else:
            self.inverse_mass = 1.0 / self.mass if self.mass > 0 else 0.0
            
            # حساب عطالة الصندوق (تقريبي)
            width, height, depth = 1.0, 1.0, 1.0
            if self.shapes and self.shapes[0].shape_type == ShapeType.BOX:
                width, height, depth = self.shapes[0].size
            
            ix = self.mass * (height * height + depth * depth) / 12
            iy = self.mass * (width * width + depth * depth) / 12
            iz = self.mass * (width * width + height * height) / 12
            
            self.inertia = np.diag([ix, iy, iz])
            self.inverse_inertia = np.linalg.inv(self.inertia)
    
    def apply_force(self, force: np.ndarray, point: np.ndarray = None):
        """تطبيق قوة"""
        self.force += force
        
        if point is not None:
            r = point - self.position
            self.torque += np.cross(r, force)
    
    def apply_impulse(self, impulse: np.ndarray, point: np.ndarray = None):
        """تطبيق دفعة"""
        self.velocity += impulse * self.inverse_mass
        
        if point is not None:
            r = point - self.position
            self.angular_velocity += self.inverse_inertia @ np.cross(r, impulse)
    
    def get_transform(self):
        """الحصول على مصفوفة التحويل"""
        transform = np.identity(4, dtype='f4')
        transform[:3, :3] = self.rotation
        transform[:3, 3] = self.position
        return transform

# ============================================================================
# Collision Detection
# ============================================================================

@dataclass
class ContactPoint:
    """نقطة اتصال"""
    position: np.ndarray
    normal: np.ndarray
    depth: float
    impulse_normal: float = 0.0
    impulse_friction: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype='f4'))

@dataclass
class CollisionManifold:
    """مجمع التصادم"""
    body_a: RigidBody
    body_b: RigidBody
    contacts: List[ContactPoint]
    normal: np.ndarray
    penetration: float
    restitution: float
    friction: float
    
    def solve(self, dt: float):
        """حل التصادم"""
        for contact in self.contacts:
            self._resolve_collision(contact, dt)
    
    def _resolve_collision(self, contact: ContactPoint, dt: float):
        """حل التصادم لنقطة اتصال"""
        # حساب السرعة النسبية
        ra = contact.position - self.body_a.position
        rb = contact.position - self.body_b.position
        
        va = self.body_a.velocity + np.cross(self.body_a.angular_velocity, ra)
        vb = self.body_b.velocity + np.cross(self.body_b.angular_velocity, rb)
        vrel = va - vb
        
        # السرعة على طول العمودي
        vn = np.dot(vrel, contact.normal)
        
        # حساب الدفع
        e = min(self.body_a.material.restitution, self.body_b.material.restitution)
        j = -(1 + e) * vn
        
        # الكتلة الفعالة
        inv_mass_a = self.body_a.inverse_mass
        inv_mass_b = self.body_b.inverse_mass
        
        ra_cross_n = np.cross(ra, contact.normal)
        rb_cross_n = np.cross(rb, contact.normal)
        
        inv_inertia_a = self.body_a.inverse_inertia
        inv_inertia_b = self.body_b.inverse_inertia
        
        angular_a = np.dot(ra_cross_n, inv_inertia_a @ ra_cross_n)
        angular_b = np.dot(rb_cross_n, inv_inertia_b @ rb_cross_n)
        
        denom = inv_mass_a + inv_mass_b + angular_a + angular_b
        if denom > 0:
            j /= denom
        
        # تطبيق الدفع
        impulse = j * contact.normal
        self.body_a.apply_impulse(-impulse, contact.position)
        self.body_b.apply_impulse(impulse, contact.position)
        
        # تصحيح الموقع
        correction = max(contact.depth - 0.01, 0.0) * contact.normal / (inv_mass_a + inv_mass_b) * 0.2
        
        if self.body_a.body_type != BodyType.STATIC:
            self.body_a.position -= correction * inv_mass_a
        
        if self.body_b.body_type != BodyType.STATIC:
            self.body_b.position += correction * inv_mass_b

class CollisionDetector:
    """كاشف التصادمات"""
    
    @staticmethod
    def sphere_vs_sphere(sphere_a: CollisionShape, transform_a: np.ndarray,
                        sphere_b: CollisionShape, transform_b: np.ndarray) -> Optional[CollisionManifold]:
        """كشف تصادم كرة-كرة"""
        pos_a = transform_a[:3, 3]
        pos_b = transform_b[:3, 3]
        
        radius_a = sphere_a.size[0]
        radius_b = sphere_b.size[0]
        
        diff = pos_b - pos_a
        distance = np.linalg.norm(diff)
        
        if distance == 0:
            # نفس الموقع
            normal = np.array([1, 0, 0], dtype='f4')
            penetration = radius_a + radius_b
        else:
            normal = diff / distance
            penetration = radius_a + radius_b - distance
        
        if penetration > 0:
            contact_point = pos_a + normal * (radius_a - penetration / 2)
            
            return CollisionManifold(
                body_a=None,  # سيتم تعيينه لاحقاً
                body_b=None,
                contacts=[ContactPoint(
                    position=contact_point,
                    normal=normal,
                    depth=penetration
                )],
                normal=normal,
                penetration=penetration,
                restitution=min(sphere_a.material.restitution, sphere_b.material.restitution),
                friction=math.sqrt(sphere_a.material.friction * sphere_b.material.friction)
            )
        
        return None
    
    @staticmethod
    def box_vs_box(box_a: CollisionShape, transform_a: np.ndarray,
                  box_b: CollisionShape, transform_b: np.ndarray) -> Optional[CollisionManifold]:
        """كشف تصادم صندوق-صندوق"""
        # هذا تنفيذ مبسط لـ SAT (Separating Axis Theorem)
        size_a = np.array(box_a.size, dtype='f4')
        size_b = np.array(box_b.size, dtype='f4')
        
        # الحصول على المحاور
        axes_a = transform_a[:3, :3]
        axes_b = transform_b[:3, :3]
        
        # جمع جميع المحاور المحتملة
        axes = []
        for i in range(3):
            axes.append(axes_a[:, i])
            axes.append(axes_b[:, i])
        
        # محاور المنتج الاتجاهي
        for i in range(3):
            for j in range(3):
                cross = np.cross(axes_a[:, i], axes_b[:, j])
                if np.linalg.norm(cross) > 0.001:
                    axes.append(cross / np.linalg.norm(cross))
        
        # مركز الصندوقين
        center_a = transform_a[:3, 3]
        center_b = transform_b[:3, 3]
        
        min_overlap = float('inf')
        min_axis = None
        
        # اختبار كل محور
        for axis in axes:
            if np.linalg.norm(axis) < 0.001:
                continue
            
            axis = axis / np.linalg.norm(axis)
            
            # إسقاط الصندوق A
            proj_a = CollisionDetector._project_box(center_a, axes_a, size_a, axis)
            
            # إسقاط الصندوق B
            proj_b = CollisionDetector._project_box(center_b, axes_b, size_b, axis)
            
            # التحقق من التداخل
            overlap = min(proj_a[1], proj_b[1]) - max(proj_a[0], proj_b[0])
            
            if overlap <= 0:
                return None  # لا يوجد تصادم
            
            if overlap < min_overlap:
                min_overlap = overlap
                min_axis = axis
        
        if min_axis is not None:
            # اتجاه العمودي (من A إلى B)
            direction = center_b - center_a
            if np.dot(direction, min_axis) < 0:
                min_axis = -min_axis
            
            # نقطة الاتصال (تقريبية - المركز)
            contact_point = (center_a + center_b) / 2
            
            return CollisionManifold(
                body_a=None,
                body_b=None,
                contacts=[ContactPoint(
                    position=contact_point,
                    normal=min_axis,
                    depth=min_overlap
                )],
                normal=min_axis,
                penetration=min_overlap,
                restitution=min(box_a.material.restitution, box_b.material.restitution),
                friction=math.sqrt(box_a.material.friction * box_b.material.friction)
            )
        
        return None
    
    @staticmethod
    def _project_box(center: np.ndarray, axes: np.ndarray, size: np.ndarray, axis: np.ndarray) -> Tuple[float, float]:
        """إسقاط صندوق على محور"""
        projection = np.dot(center, axis)
        
        # حساب نصف القطر على هذا المحور
        radius = (abs(np.dot(axes[:, 0], axis)) * size[0] / 2 +
                  abs(np.dot(axes[:, 1], axis)) * size[1] / 2 +
                  abs(np.dot(axes[:, 2], axis)) * size[2] / 2)
        
        return projection - radius, projection + radius
    
    @staticmethod
    def sphere_vs_box(sphere: CollisionShape, sphere_transform: np.ndarray,
                     box: CollisionShape, box_transform: np.ndarray) -> Optional[CollisionManifold]:
        """كشف تصادم كرة-صندوق"""
        # تحويل موقع الكرة إلى مساحة الصندوق المحلية
        inv_box_transform = np.linalg.inv(box_transform)
        sphere_local_pos = inv_box_transform[:3, :3] @ sphere_transform[:3, 3] + inv_box_transform[:3, 3]
        
        # أقرب نقطة على الصندوق للكرة
        half_size = np.array(box.size, dtype='f4') / 2
        closest = np.clip(sphere_local_pos, -half_size, half_size)
        
        # حساب المسافة
        diff = sphere_local_pos - closest
        distance = np.linalg.norm(diff)
        radius = sphere.size[0]
        
        if distance < radius:
            # العمودي في المساحة المحلية
            if distance > 0.001:
                normal_local = diff / distance
            else:
                # إذا كانت الكرة داخل الصندوق
                normal_local = np.array([1, 0, 0], dtype='f4')
            
            # تحويل العمودي إلى المساحة العالمية
            normal = box_transform[:3, :3] @ normal_local
            normal = normal / np.linalg.norm(normal)
            
            penetration = radius - distance
            contact_point_world = sphere_transform[:3, 3] - normal * (radius - penetration / 2)
            
            return CollisionManifold(
                body_a=None,
                body_b=None,
                contacts=[ContactPoint(
                    position=contact_point_world,
                    normal=normal,
                    depth=penetration
                )],
                normal=normal,
                penetration=penetration,
                restitution=min(sphere.material.restitution, box.material.restitution),
                friction=math.sqrt(sphere.material.friction * box.material.friction)
            )
        
        return None

# ============================================================================
# Physics World
# ============================================================================

class PhysicsWorld:
    """عالم الفيزياء"""
    
    def __init__(self, gravity: Tuple[float, float, float] = (0, -9.81, 0)):
        self.gravity = np.array(gravity, dtype='f4')
        self.bodies: List[RigidBody] = []
        self.manifolds: List[CollisionManifold] = []
        
        self.broadphase_grid = defaultdict(list)
        self.cell_size = 2.0
        
        self.stats = {
            'collisions_detected': 0,
            'collisions_resolved': 0,
            'broadphase_checks': 0,
            'narrowphase_checks': 0
        }
    
    def add_body(self, body: RigidBody):
        """إضافة جسم"""
        self.bodies.append(body)
    
    def remove_body(self, body: RigidBody):
        """إزالة جسم"""
        if body in self.bodies:
            self.bodies.remove(body)
    
    def update(self, dt: float):
        """تحديث العالم الفيزيائي"""
        # تطبيق الجاذبية
        self._apply_gravity(dt)
        
        # كشف التصادمات
        self._detect_collisions()
        
        # حل التصادمات
        self._resolve_collisions(dt)
        
        # تكامل السرعة
        self._integrate_velocities(dt)
        
        # تكامل المواقع
        self._integrate_positions(dt)
        
        # مسح القوى
        self._clear_forces()
        
        # تحديث النوم
        self._update_sleeping(dt)
    
    def _apply_gravity(self, dt: float):
        """تطبيق الجاذبية"""
        for body in self.bodies:
            if body.body_type == BodyType.DYNAMIC and not body.sleeping:
                body.force += self.gravity * body.mass * body.gravity_scale
    
    def _detect_collisions(self):
        """كشف التصادمات"""
        self.manifolds.clear()
        self.stats['collisions_detected'] = 0
        
        # المرحلة العريضة (Broadphase)
        self._broadphase()
        
        # المرحلة الضيقة (Narrowphase)
        self._narrowphase()
    
    def _broadphase(self):
        """المرحلة العريضة لكشف التصادمات"""
        self.broadphase_grid.clear()
        
        # وضع الأجسام في الخلايا
        for i, body in enumerate(self.bodies):
            if body.body_type == BodyType.STATIC and body.sleeping:
                continue
            
            # الحصول على الكرة المحيطة
            radius = 0
            for shape in body.shapes:
                radius = max(radius, shape.get_bounding_sphere())
            
            pos = body.position
            cell_x = int(pos[0] / self.cell_size)
            cell_y = int(pos[1] / self.cell_size)
            cell_z = int(pos[2] / self.cell_size)
            
            cell_key = (cell_x, cell_y, cell_z)
            self.broadphase_grid[cell_key].append((i, body, radius))
        
        # التحقق من التصادمات بين الخلايا المجاورة
        for cell_key, bodies_in_cell in self.broadphase_grid.items():
            cell_x, cell_y, cell_z = cell_key
            
            # التحقق داخل الخلية
            self._check_cell_collisions(bodies_in_cell)
            
            # التحقق مع الخلايا المجاورة
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        if dx == 0 and dy == 0 and dz == 0:
                            continue
                        
                        neighbor_key = (cell_x + dx, cell_y + dy, cell_z + dz)
                        if neighbor_key in self.broadphase_grid:
                            self._check_cross_cell_collisions(
                                bodies_in_cell,
                                self.broadphase_grid[neighbor_key]
                            )
    
    def _check_cell_collisions(self, bodies):
        """التحقق من التصادمات داخل خلية"""
        n = len(bodies)
        for i in range(n):
            idx_i, body_i, radius_i = bodies[i]
            for j in range(i + 1, n):
                idx_j, body_j, radius_j = bodies[j]
                
                # اختبار الكرات المحيطة أولاً
                diff = body_j.position - body_i.position
                distance_sq = np.dot(diff, diff)
                radius_sum = radius_i + radius_j
                
                if distance_sq <= radius_sum * radius_sum:
                    self.stats['broadphase_checks'] += 1
                    self._check_body_collision(idx_i, body_i, idx_j, body_j)
    
    def _check_cross_cell_collisions(self, bodies_a, bodies_b):
        """التحقق من التصادمات بين خليتين"""
        for idx_i, body_i, radius_i in bodies_a:
            for idx_j, body_j, radius_j in bodies_b:
                # اختبار الكرات المحيطة أولاً
                diff = body_j.position - body_i.position
                distance_sq = np.dot(diff, diff)
                radius_sum = radius_i + radius_j
                
                if distance_sq <= radius_sum * radius_sum:
                    self.stats['broadphase_checks'] += 1
                    self._check_body_collision(idx_i, body_i, idx_j, body_j)
    
    def _check_body_collision(self, idx_i: int, body_i: RigidBody, 
                             idx_j: int, body_j: RigidBody):
        """التحقق من تصادم بين جسمين"""
        # تخطي الأجسام الثابتة النائمة
        if (body_i.body_type == BodyType.STATIC and body_i.sleeping and
            body_j.body_type == BodyType.STATIC and body_j.sleeping):
            return
        
        self.stats['narrowphase_checks'] += 1
        
        # التحقق من تصادم كل شكل مع كل شكل
        for shape_i in body_i.shapes:
            transform_i = body_i.get_transform()
            
            for shape_j in body_j.shapes:
                transform_j = body_j.get_transform()
                
                manifold = None
                
                # كشف التصادم حسب نوع الشكل
                if shape_i.shape_type == ShapeType.SPHERE and shape_j.shape_type == ShapeType.SPHERE:
                    manifold = CollisionDetector.sphere_vs_sphere(
                        shape_i, transform_i, shape_j, transform_j
                    )
                elif shape_i.shape_type == ShapeType.BOX and shape_j.shape_type == ShapeType.BOX:
                    manifold = CollisionDetector.box_vs_box(
                        shape_i, transform_i, shape_j, transform_j
                    )
                elif shape_i.shape_type == ShapeType.SPHERE and shape_j.shape_type == ShapeType.BOX:
                    manifold = CollisionDetector.sphere_vs_box(
                        shape_i, transform_i, shape_j, transform_j
                    )
                elif shape_i.shape_type == ShapeType.BOX and shape_j.shape_type == ShapeType.SPHERE:
                    manifold = CollisionDetector.sphere_vs_box(
                        shape_j, transform_j, shape_i, transform_i
                    )
                    if manifold:
                        # عكس العمودي للجسم الأول
                        manifold.normal = -manifold.normal
                
                if manifold:
                    manifold.body_a = body_i
                    manifold.body_b = body_j
                    self.manifolds.append(manifold)
                    self.stats['collisions_detected'] += 1
    
    def _narrowphase(self):
        """المرحلة الضيقة لكشف التصادمات"""
        # تم التنفيذ في _check_body_collision
        pass
    
    def _resolve_collisions(self, dt: float):
        """حل التصادمات"""
        self.stats['collisions_resolved'] = len(self.manifolds)
        
        # حل كل تصادم عدة مرات للاستقرار
        iterations = 4
        for _ in range(iterations):
            for manifold in self.manifolds:
                manifold.solve(dt)
    
    def _integrate_velocities(self, dt: float):
        """تكامل السرعات"""
        for body in self.bodies:
            if body.body_type == BodyType.DYNAMIC and not body.sleeping:
                # السرعة الخطية
                acceleration = body.force * body.inverse_mass
                body.velocity += acceleration * dt
                body.velocity *= (1 - body.linear_damping)
                
                # السرعة الزاوية
                angular_acceleration = body.inverse_inertia @ body.torque
                body.angular_velocity += angular_acceleration * dt
                body.angular_velocity *= (1 - body.angular_damping)
    
    def _integrate_positions(self, dt: float):
        """تكامل المواقع"""
        for body in self.bodies:
            if body.body_type != BodyType.STATIC and not body.sleeping:
                # الموقع
                body.position += body.velocity * dt
                
                # الدوران (تقريبي)
                angle = np.linalg.norm(body.angular_velocity) * dt
                if angle > 0.001:
                    axis = body.angular_velocity / angle
                    rotation = self._axis_angle_to_matrix(axis, angle)
                    body.rotation = rotation @ body.rotation
    
    def _axis_angle_to_matrix(self, axis: np.ndarray, angle: float) -> np.ndarray:
        """تحويل محور وزاوية إلى مصفوفة دوران"""
        axis = axis / np.linalg.norm(axis)
        x, y, z = axis
        c = math.cos(angle)
        s = math.sin(angle)
        t = 1 - c
        
        return np.array([
            [t*x*x + c,    t*x*y - s*z,  t*x*z + s*y],
            [t*x*y + s*z,  t*y*y + c,    t*y*z - s*x],
            [t*x*z - s*y,  t*y*z + s*x,  t*z*z + c]
        ], dtype='f4')
    
    def _clear_forces(self):
        """مسح القوى"""
        for body in self.bodies:
            body.force.fill(0)
            body.torque.fill(0)
    
    def _update_sleeping(self, dt: float):
        """تحديث حالة النوم"""
        sleep_threshold = 0.1  # سرعة عتبة النوم
        
        for body in self.bodies:
            if body.body_type == BodyType.DYNAMIC:
                speed_sq = np.dot(body.velocity, body.velocity)
                ang_speed_sq = np.dot(body.angular_velocity, body.angular_velocity)
                
                if speed_sq < sleep_threshold and ang_speed_sq < sleep_threshold:
                    body.awake_timer += dt
                    if body.awake_timer > 2.0:  # ثانيتين من السكون
                        body.sleeping = True
                else:
                    body.awake_timer = 0
                    body.sleeping = False
    
    def raycast(self, origin: np.ndarray, direction: np.ndarray, 
                max_distance: float = 1000.0) -> Optional[Tuple[RigidBody, float, np.ndarray]]:
        """إطلاق شعاع"""
        direction = direction / np.linalg.norm(direction)
        closest_hit = None
        closest_distance = max_distance
        
        for body in self.bodies:
            if body.body_type == BodyType.STATIC and body.sleeping:
                continue
            
            for shape in body.shapes:
                hit, distance, normal = self._raycast_shape(
                    origin, direction, shape, body.get_transform()
                )
                
                if hit and distance < closest_distance:
                    closest_hit = (body, distance, normal)
                    closest_distance = distance
        
        return closest_hit
    
    def _raycast_shape(self, origin: np.ndarray, direction: np.ndarray,
                      shape: CollisionShape, transform: np.ndarray) -> Tuple[bool, float, np.ndarray]:
        """إطلاق شعاع على شكل"""
        # تحويل الشعاع إلى المساحة المحلية
        inv_transform = np.linalg.inv(transform)
        local_origin = inv_transform[:3, :3] @ origin + inv_transform[:3, 3]
        local_dir = inv_transform[:3, :3] @ direction
        
        hit = False
        distance = 0
        normal = np.array([0, 0, 0], dtype='f4')
        
        if shape.shape_type == ShapeType.SPHERE:
            hit, distance, normal = self._raycast_sphere(
                local_origin, local_dir, shape.size[0]
            )
        elif shape.shape_type == ShapeType.BOX:
            hit, distance, normal = self._raycast_box(
                local_origin, local_dir, shape.size
            )
        
        if hit:
            # تحويل العمودي إلى المساحة العالمية
            normal = transform[:3, :3] @ normal
            normal = normal / np.linalg.norm(normal)
        
        return hit, distance, normal
    
    def _raycast_sphere(self, origin: np.ndarray, direction: np.ndarray, 
                       radius: float) -> Tuple[bool, float, np.ndarray]:
        """إطلاق شعاع على كرة"""
        # معادلة الشعاع والكرة
        oc = -origin  # المركز عند (0,0,0)
        
        a = np.dot(direction, direction)
        b = 2.0 * np.dot(oc, direction)
        c = np.dot(oc, oc) - radius * radius
        
        discriminant = b * b - 4 * a * c
        
        if discriminant < 0:
            return False, 0, np.zeros(3, dtype='f4')
        
        sqrt_disc = math.sqrt(discriminant)
        t1 = (-b - sqrt_disc) / (2 * a)
        t2 = (-b + sqrt_disc) / (2 * a)
        
        if t1 < 0 and t2 < 0:
            return False, 0, np.zeros(3, dtype='f4')
        
        t = t1 if t1 >= 0 else t2
        hit_point = origin + direction * t
        normal = hit_point / radius
        
        return True, t, normal
    
    def _raycast_box(self, origin: np.ndarray, direction: np.ndarray,
                    size: Tuple[float, float, float]) -> Tuple[bool, float, np.ndarray]:
        """إطلاق شعاع على صندوق"""
        half_size = np.array(size, dtype='f4') / 2
        
        # خوارزمية slab
        tmin = -float('inf')
        tmax = float('inf')
        normal = np.zeros(3, dtype='f4')
        
        for i in range(3):
            if abs(direction[i]) < 1e-6:
                # موازٍ للمحور
                if origin[i] < -half_size[i] or origin[i] > half_size[i]:
                    return False, 0, np.zeros(3, dtype='f4')
            else:
                inv_dir = 1.0 / direction[i]
                t1 = (-half_size[i] - origin[i]) * inv_dir
                t2 = (half_size[i] - origin[i]) * inv_dir
                
                if t1 > t2:
                    t1, t2 = t2, t1
                    normal_sign = -1
                else:
                    normal_sign = 1
                
                if t1 > tmin:
                    tmin = t1
                    if i == 0:
                        normal = np.array([normal_sign, 0, 0], dtype='f4')
                    elif i == 1:
                        normal = np.array([0, normal_sign, 0], dtype='f4')
                    else:
                        normal = np.array([0, 0, normal_sign], dtype='f4')
                
                if t2 < tmax:
                    tmax = t2
                
                if tmin > tmax:
                    return False, 0, np.zeros(3, dtype='f4')
        
        if tmin < 0:
            return False, 0, np.zeros(3, dtype='f4')
        
        return True, tmin, normal
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات العالم الفيزيائي"""
        return {
            'total_bodies': len(self.bodies),
            'dynamic_bodies': sum(1 for b in self.bodies if b.body_type == BodyType.DYNAMIC),
            'static_bodies': sum(1 for b in self.bodies if b.body_type == BodyType.STATIC),
            'sleeping_bodies': sum(1 for b in self.bodies if b.sleeping),
            'active_collisions': len(self.manifolds),
            'broadphase_checks': self.stats['broadphase_checks'],
            'narrowphase_checks': self.stats['narrowphase_checks'],
            'collisions_detected': self.stats['collisions_detected'],
            'collisions_resolved': self.stats['collisions_resolved']
        }

# ============================================================================
# Physics System
# ============================================================================

class PhysicsSystem:
    """نظام الفيزياء"""
    
    def __init__(self, engine):
        self.engine = engine
        self.world = PhysicsWorld()
        self.debug_draw = False
        self.paused = False
        
        self.entity_to_body = {}
        self.body_to_entity = {}
    
    def initialize(self):
        """تهيئة نظام الفيزياء"""
        print("Physics system initialized")
        return True
    
    def update(self, delta_time: float):
        """تحديث نظام الفيزياء"""
        if self.paused:
            return
        
        # تحديث العالم الفيزيائي
        self.world.update(delta_time)
        
        # مزامنة الكيانات مع الأجسام الفيزيائية
        self._sync_entities()
    
    def _sync_entities(self):
        """مزامنة الكيانات مع الأجسام الفيزيائية"""
        for entity_id, body in self.entity_to_body.items():
            entity = self.engine.entity_manager.get_entity(entity_id)
            if entity and entity.active:
                # تحديث تحويل الكيان من الجسم الفيزيائي
                transform_component = entity.get_component(ComponentType.TRANSFORM)
                if transform_component:
                    transform_component.position = Vector3(*body.position)
                    
                    # تحويل مصفوفة الدوران إلى أويلر (مبسط)
                    # في التنفيذ الحقيقي، سيتم استخدام الكواتيرنيونات
                    pass
    
    def add_entity_body(self, entity_id: int, body: RigidBody):
        """إضافة جسم فيزيائي لكيان"""
        self.entity_to_body[entity_id] = body
        self.body_to_entity[id(body)] = entity_id
        self.world.add_body(body)
    
    def remove_entity_body(self, entity_id: int):
        """إزالة جسم فيزيائي من كيان"""
        if entity_id in self.entity_to_body:
            body = self.entity_to_body[entity_id]
            self.world.remove_body(body)
            del self.body_to_entity[id(body)]
            del self.entity_to_body[entity_id]
    
    def raycast_from_entity(self, entity_id: int, direction: Vector3, 
                           max_distance: float = 100.0) -> Optional[Dict]:
        """إطلاق شعاع من كيان"""
        entity = self.engine.entity_manager.get_entity(entity_id)
        if not entity:
            return None
        
        transform = entity.get_component(ComponentType.TRANSFORM)
        if not transform:
            return None
        
        origin = np.array(transform.position, dtype='f4')
        direction_np = np.array(direction, dtype='f4')
        
        hit = self.world.raycast(origin, direction_np, max_distance)
        
        if hit:
            body, distance, normal = hit
            hit_entity_id = self.body_to_entity.get(id(body))
            
            return {
                'entity_id': hit_entity_id,
                'distance': distance,
                'point': origin + direction_np * distance,
                'normal': normal,
                'body': body
            }
        
        return None
    
    def apply_force_to_entity(self, entity_id: int, force: Vector3, point: Vector3 = None):
        """تطبيق قوة على كيان"""
        if entity_id in self.entity_to_body:
            body = self.entity_to_body[entity_id]
            force_np = np.array(force, dtype='f4')
            point_np = np.array(point, dtype='f4') if point else None
            body.apply_force(force_np, point_np)
    
    def apply_impulse_to_entity(self, entity_id: int, impulse: Vector3, point: Vector3 = None):
        """تطبيق دفعة على كيان"""
        if entity_id in self.entity_to_body:
            body = self.entity_to_body[entity_id]
            impulse_np = np.array(impulse, dtype='f4')
            point_np = np.array(point, dtype='f4') if point else None
            body.apply_impulse(impulse_np, point_np)
    
    def set_entity_velocity(self, entity_id: int, velocity: Vector3):
        """تعيين سرعة كيان"""
        if entity_id in self.entity_to_body:
            body = self.entity_to_body[entity_id]
            body.velocity = np.array(velocity, dtype='f4')
    
    def get_entity_velocity(self, entity_id: int) -> Optional[Vector3]:
        """الحصول على سرعة كيان"""
        if entity_id in self.entity_to_body:
            body = self.entity_to_body[entity_id]
            return Vector3(*body.velocity)
        return None
    
    def toggle_debug_draw(self):
        """تبديل وضع الرسم التصحيحي"""
        self.debug_draw = not self.debug_draw
    
    def pause(self):
        """إيقاف الفيزياء"""
        self.paused = True
    
    def resume(self):
        """استئناف الفيزياء"""
        self.paused = False
    
    def shutdown(self):
        """إيقاف نظام الفيزياء"""
        self.world.bodies.clear()
        self.entity_to_body.clear()
        self.body_to_entity.clear()
        print("Physics system shutdown")
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات النظام"""
        return self.world.get_statistics()