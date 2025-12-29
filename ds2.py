"""
GameEnginePro - Renderer Module
نظام التصيير المتقدم 2D/3D
"""

import pygame
import numpy as np
import moderngl
from typing import Dict, List, Tuple, Optional, Any, Union
from enum import Enum, auto
from dataclasses import dataclass, field
import math
import json
from pathlib import Path
import time

# ============================================================================
# Graphics Enums and Types
# ============================================================================

class BlendMode(Enum):
    """أنواع مزج الألوان"""
    NONE = auto()
    ALPHA = auto()
    ADDITIVE = auto()
    MULTIPLY = auto()
    SCREEN = auto()

class FilterMode(Enum):
    """أنواع التصفية"""
    NEAREST = auto()
    LINEAR = auto()
    TRILINEAR = auto()

class WrapMode(Enum):
    """أنواع التكرار"""
    REPEAT = auto()
    CLAMP = auto()
    MIRROR = auto()

class PrimitiveType(Enum):
    """أنواع الأشكال الهندسية"""
    POINTS = auto()
    LINES = auto()
    LINE_STRIP = auto()
    TRIANGLES = auto()
    TRIANGLE_STRIP = auto()
    TRIANGLE_FAN = auto()

@dataclass
class Vertex:
    """فئة الرأس"""
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    texcoord: Tuple[float, float] = (0.0, 0.0)
    color: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)

@dataclass
class Material:
    """فئة المادة"""
    name: str = "default"
    diffuse_color: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    specular_color: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    shininess: float = 32.0
    diffuse_texture: Optional[str] = None
    normal_texture: Optional[str] = None
    specular_texture: Optional[str] = None
    emissive_texture: Optional[str] = None
    transparent: bool = False
    blend_mode: BlendMode = BlendMode.ALPHA

@dataclass
class Mesh:
    """فئة الشبكة"""
    vertices: List[Vertex] = field(default_factory=list)
    indices: List[int] = field(default_factory=list)
    material: Material = field(default_factory=Material)
    primitive_type: PrimitiveType = PrimitiveType.TRIANGLES
    bounding_box: Tuple[Tuple[float, float, float], Tuple[float, float, float]] = None

# ============================================================================
# Shader System
# ============================================================================

class Shader:
    """فائلة الشادر"""
    
    def __init__(self, ctx: moderngl.Context, vertex_shader: str, fragment_shader: str):
        self.ctx = ctx
        self.program = None
        self.uniforms = {}
        self.attributes = {}
        self.compile_shaders(vertex_shader, fragment_shader)
    
    def compile_shaders(self, vertex_shader: str, fragment_shader: str):
        """تجميع الشادرات"""
        try:
            self.program = self.ctx.program(
                vertex_shader=vertex_shader,
                fragment_shader=fragment_shader
            )
            
            # جمع المعلومات عن المتغيرات المنتظمة
            for uniform in self.program:
                self.uniforms[uniform.name] = uniform
            
            # جمع المعلومات عن السمات
            for attribute in self.program.attributes:
                self.attributes[attribute.name] = attribute
            
        except Exception as e:
            print(f"Failed to compile shader: {e}")
            raise
    
    def set_uniform(self, name: str, value):
        """تعيين متغير منتظم"""
        if name in self.uniforms:
            try:
                self.uniforms[name].value = value
            except Exception as e:
                print(f"Failed to set uniform {name}: {e}")
    
    def bind(self):
        """ربط الشادر"""
        if self.program:
            self.program.use()
    
    def release(self):
        """تحرير الشادر"""
        pass

class ShaderManager:
    """مدير الشادرات"""
    
    def __init__(self, ctx: moderngl.Context):
        self.ctx = ctx
        self.shaders: Dict[str, Shader] = {}
        self.shader_cache = {}
        self.load_builtin_shaders()
    
    def load_builtin_shaders(self):
        """تحميل الشادرات المضمنة"""
        # شادر النصي البسيط
        basic_vs = """
            #version 330
            in vec3 in_position;
            in vec2 in_texcoord;
            in vec4 in_color;
            
            out vec2 v_texcoord;
            out vec4 v_color;
            
            uniform mat4 u_projection;
            uniform mat4 u_view;
            uniform mat4 u_model;
            
            void main() {
                gl_Position = u_projection * u_view * u_model * vec4(in_position, 1.0);
                v_texcoord = in_texcoord;
                v_color = in_color;
            }
        """
        
        basic_fs = """
            #version 330
            in vec2 v_texcoord;
            in vec4 v_color;
            
            out vec4 f_color;
            
            uniform sampler2D u_texture;
            uniform bool u_use_texture;
            
            void main() {
                if (u_use_texture) {
                    f_color = texture(u_texture, v_texcoord) * v_color;
                } else {
                    f_color = v_color;
                }
            }
        """
        
        self.create_shader("basic", basic_vs, basic_fs)
        
        # شادر الإضاءة
        lit_vs = """
            #version 330
            in vec3 in_position;
            in vec3 in_normal;
            in vec2 in_texcoord;
            
            out vec3 v_position;
            out vec3 v_normal;
            out vec2 v_texcoord;
            
            uniform mat4 u_projection;
            uniform mat4 u_view;
            uniform mat4 u_model;
            uniform mat3 u_normal_matrix;
            
            void main() {
                vec4 world_pos = u_model * vec4(in_position, 1.0);
                v_position = world_pos.xyz;
                v_normal = u_normal_matrix * in_normal;
                v_texcoord = in_texcoord;
                gl_Position = u_projection * u_view * world_pos;
            }
        """
        
        lit_fs = """
            #version 330
            in vec3 v_position;
            in vec3 v_normal;
            in vec2 v_texcoord;
            
            out vec4 f_color;
            
            uniform sampler2D u_diffuse_texture;
            uniform vec4 u_diffuse_color;
            uniform vec3 u_light_pos;
            uniform vec3 u_light_color;
            uniform vec3 u_view_pos;
            
            void main() {
                vec3 norm = normalize(v_normal);
                vec3 light_dir = normalize(u_light_pos - v_position);
                vec3 view_dir = normalize(u_view_pos - v_position);
                vec3 reflect_dir = reflect(-light_dir, norm);
                
                // إضاءة محيطة
                float ambient_strength = 0.1;
                vec3 ambient = ambient_strength * u_light_color;
                
                // إضاءة منتشرة
                float diff = max(dot(norm, light_dir), 0.0);
                vec3 diffuse = diff * u_light_color;
                
                // إضاءة مرآة
                float spec_strength = 0.5;
                float spec = pow(max(dot(view_dir, reflect_dir), 0.0), 32);
                vec3 specular = spec_strength * spec * u_light_color;
                
                vec4 tex_color = texture(u_diffuse_texture, v_texcoord);
                vec3 result = (ambient + diffuse + specular) * tex_color.rgb * u_diffuse_color.rgb;
                f_color = vec4(result, tex_color.a * u_diffuse_color.a);
            }
        """
        
        self.create_shader("lit", lit_vs, lit_fs)
    
    def create_shader(self, name: str, vertex_shader: str, fragment_shader: str) -> Optional[Shader]:
        """إنشاء شادر جديد"""
        try:
            shader = Shader(self.ctx, vertex_shader, fragment_shader)
            self.shaders[name] = shader
            return shader
        except Exception as e:
            print(f"Failed to create shader '{name}': {e}")
            return None
    
    def get_shader(self, name: str) -> Optional[Shader]:
        """الحصول على شادر"""
        return self.shaders.get(name)
    
    def load_shader_from_file(self, name: str, vertex_path: Path, fragment_path: Path) -> bool:
        """تحميل شادر من ملف"""
        try:
            with open(vertex_path, 'r', encoding='utf-8') as f:
                vertex_shader = f.read()
            
            with open(fragment_path, 'r', encoding='utf-8') as f:
                fragment_shader = f.read()
            
            self.create_shader(name, vertex_shader, fragment_shader)
            return True
            
        except Exception as e:
            print(f"Failed to load shader from file: {e}")
            return False

# ============================================================================
# Texture System
# ============================================================================

class Texture:
    """فئة النسيج"""
    
    def __init__(self, ctx: moderngl.Context, path: Path = None, 
                 width: int = None, height: int = None, 
                 data: bytes = None, format: str = "RGBA"):
        self.ctx = ctx
        self.texture = None
        self.width = width or 0
        self.height = height or 0
        self.format = format
        self.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.wrap = (moderngl.REPEAT, moderngl.REPEAT)
        
        if path:
            self.load_from_file(path)
        elif width and height and data:
            self.create_from_data(width, height, data, format)
    
    def load_from_file(self, path: Path):
        """تحميل نسيج من ملف"""
        try:
            image = pygame.image.load(str(path))
            self.width = image.get_width()
            self.height = image.get_height()
            
            # تحويل الصورة إلى بيانات بايت
            image_data = pygame.image.tostring(image, "RGBA")
            
            # إنشاء نسيج OpenGL
            self.texture = self.ctx.texture(
                (self.width, self.height),
                4,  # مكونات RGBA
                image_data,
                dtype='f1'
            )
            
            self.texture.filter = self.filter
            self.texture.repeat_x = self.wrap[0] == moderngl.REPEAT
            self.texture.repeat_y = self.wrap[1] == moderngl.REPEAT
            
        except Exception as e:
            print(f"Failed to load texture from {path}: {e}")
    
    def create_from_data(self, width: int, height: int, data: bytes, format: str = "RGBA"):
        """إنشاء نسيج من بيانات"""
        try:
            self.width = width
            self.height = height
            self.format = format
            
            # تحديد عدد المكونات
            components = 4 if format == "RGBA" else 3
            
            self.texture = self.ctx.texture(
                (width, height),
                components,
                data,
                dtype='f1'
            )
            
            self.texture.filter = self.filter
            self.texture.repeat_x = self.wrap[0] == moderngl.REPEAT
            self.texture.repeat_y = self.wrap[1] == moderngl.REPEAT
            
        except Exception as e:
            print(f"Failed to create texture from data: {e}")
    
    def bind(self, unit: int = 0):
        """ربط النسيج"""
        if self.texture:
            self.texture.use(unit)
    
    def set_filter(self, min_filter: FilterMode, mag_filter: FilterMode):
        """تعيين عوامل التصفية"""
        filter_map = {
            FilterMode.NEAREST: moderngl.NEAREST,
            FilterMode.LINEAR: moderngl.LINEAR
        }
        
        self.filter = (filter_map.get(min_filter, moderngl.LINEAR),
                      filter_map.get(mag_filter, moderngl.LINEAR))
        
        if self.texture:
            self.texture.filter = self.filter
    
    def set_wrap(self, wrap_s: WrapMode, wrap_t: WrapMode):
        """تعيين أنماط التكرار"""
        wrap_map = {
            WrapMode.REPEAT: moderngl.REPEAT,
            WrapMode.CLAMP: moderngl.CLAMP_TO_EDGE,
            WrapMode.MIRROR: moderngl.MIRRORED_REPEAT
        }
        
        self.wrap = (wrap_map.get(wrap_s, moderngl.REPEAT),
                    wrap_map.get(wrap_t, moderngl.REPEAT))
        
        if self.texture:
            self.texture.repeat_x = self.wrap[0] == moderngl.REPEAT
            self.texture.repeat_y = self.wrap[1] == moderngl.REPEAT
    
    def release(self):
        """تحرير النسيج"""
        if self.texture:
            self.texture.release()

class TextureManager:
    """مدير النسيج"""
    
    def __init__(self, ctx: moderngl.Context):
        self.ctx = ctx
        self.textures: Dict[str, Texture] = {}
        self.default_texture = self.create_default_texture()
    
    def create_default_texture(self) -> Texture:
        """إنشاء نسيج افتراضي"""
        # نسيج 2x2 أبيض
        data = bytes([255, 255, 255, 255] * 4)
        texture = Texture(self.ctx, width=2, height=2, data=data, format="RGBA")
        return texture
    
    def load_texture(self, name: str, path: Path) -> Optional[Texture]:
        """تحميل نسيج"""
        try:
            if name in self.textures:
                return self.textures[name]
            
            texture = Texture(self.ctx, path=path)
            if texture.texture:
                self.textures[name] = texture
                return texture
            
        except Exception as e:
            print(f"Failed to load texture '{name}': {e}")
        
        return None
    
    def create_texture(self, name: str, width: int, height: int, 
                      data: bytes = None, format: str = "RGBA") -> Optional[Texture]:
        """إنشاء نسيج جديد"""
        try:
            if not data:
                # إنشاء بيانات فارغة
                components = 4 if format == "RGBA" else 3
                data = bytes([0] * width * height * components)
            
            texture = Texture(self.ctx, width=width, height=height, 
                             data=data, format=format)
            
            if texture.texture:
                self.textures[name] = texture
                return texture
            
        except Exception as e:
            print(f"Failed to create texture '{name}': {e}")
        
        return None
    
    def get_texture(self, name: str) -> Optional[Texture]:
        """الحصول على نسيج"""
        return self.textures.get(name, self.default_texture)
    
    def release_texture(self, name: str):
        """تحرير نسيج"""
        if name in self.textures:
            self.textures[name].release()
            del self.textures[name]

# ============================================================================
# Mesh System
# ============================================================================

class GPUMesh:
    """شبكة معالجة الرسوميات"""
    
    def __init__(self, ctx: moderngl.Context, mesh: Mesh):
        self.ctx = ctx
        self.vertex_buffer = None
        self.index_buffer = None
        self.vertex_array = None
        self.mesh = mesh
        self.upload_to_gpu()
    
    def upload_to_gpu(self):
        """رفع الشبكة إلى معالجة الرسوميات"""
        if not self.mesh.vertices:
            return
        
        # تحضير بيانات الرؤوس
        vertex_data = []
        for vertex in self.mesh.vertices:
            vertex_data.extend(vertex.position)
            vertex_data.extend(vertex.normal)
            vertex_data.extend(vertex.texcoord)
            vertex_data.extend(vertex.color)
        
        # إنشاء مخزن مؤقت للرؤوس
        self.vertex_buffer = self.ctx.buffer(
            np.array(vertex_data, dtype='f4').tobytes()
        )
        
        # إنشاء مخزن مؤقت للفهارس
        if self.mesh.indices:
            self.index_buffer = self.ctx.buffer(
                np.array(self.mesh.indices, dtype='i4').tobytes()
            )
        
        # تخطيط الرؤوس
        self.vertex_array = self.ctx.vertex_array(
            self._get_shader_program(),  # تحتاج إلى شادر
            [
                (self.vertex_buffer, '3f 3f 2f 4f', 'in_position', 'in_normal', 'in_texcoord', 'in_color')
            ],
            index_buffer=self.index_buffer if self.index_buffer else None
        )
    
    def _get_shader_program(self):
        """الحصول على برنامج الشادر"""
        # هذا يجب أن يأتي من مدير الشادرات
        # هنا نعود بقيمة افتراضية
        return None
    
    def render(self):
        """تصيير الشبكة"""
        if self.vertex_array:
            self.vertex_array.render(
                mode=self._get_primitive_mode(self.mesh.primitive_type)
            )
    
    def _get_primitive_mode(self, primitive_type: PrimitiveType):
        """الحصول على وضع الشكل الهندسي"""
        mode_map = {
            PrimitiveType.POINTS: moderngl.POINTS,
            PrimitiveType.LINES: moderngl.LINES,
            PrimitiveType.LINE_STRIP: moderngl.LINE_STRIP,
            PrimitiveType.TRIANGLES: moderngl.TRIANGLES,
            PrimitiveType.TRIANGLE_STRIP: moderngl.TRIANGLE_STRIP,
            PrimitiveType.TRIANGLE_FAN: moderngl.TRIANGLE_FAN
        }
        return mode_map.get(primitive_type, moderngl.TRIANGLES)
    
    def release(self):
        """تحرير الموارد"""
        if self.vertex_buffer:
            self.vertex_buffer.release()
        if self.index_buffer:
            self.index_buffer.release()
        if self.vertex_array:
            self.vertex_array.release()

class MeshManager:
    """مدير الشبكات"""
    
    def __init__(self, ctx: moderngl.Context):
        self.ctx = ctx
        self.meshes: Dict[str, GPUMesh] = {}
        self.load_builtin_meshes()
    
    def load_builtin_meshes(self):
        """تحميل الشبكات المضمنة"""
        # مكعب
        cube_mesh = self.create_cube_mesh()
        self.add_mesh("cube", cube_mesh)
        
        # مستوى
        plane_mesh = self.create_plane_mesh()
        self.add_mesh("plane", plane_mesh)
        
        # كرة
        sphere_mesh = self.create_sphere_mesh()
        self.add_mesh("sphere", sphere_mesh)
    
    def create_cube_mesh(self) -> Mesh:
        """إنشاء شبكة مكعب"""
        vertices = []
        indices = []
        
        # رؤوس المكعب
        cube_vertices = [
            # وجه أمامي
            Vertex((-0.5, -0.5, 0.5), (0, 0, 1), (0, 0)),
            Vertex((0.5, -0.5, 0.5), (0, 0, 1), (1, 0)),
            Vertex((0.5, 0.5, 0.5), (0, 0, 1), (1, 1)),
            Vertex((-0.5, 0.5, 0.5), (0, 0, 1), (0, 1)),
            
            # وجه خلفي
            Vertex((-0.5, -0.5, -0.5), (0, 0, -1), (1, 0)),
            Vertex((0.5, -0.5, -0.5), (0, 0, -1), (0, 0)),
            Vertex((0.5, 0.5, -0.5), (0, 0, -1), (0, 1)),
            Vertex((-0.5, 0.5, -0.5), (0, 0, -1), (1, 1)),
        ]
        
        # فهارس المكعب (مثلثات)
        cube_indices = [
            # وجه أمامي
            0, 1, 2, 2, 3, 0,
            # وجه خلفي
            4, 5, 6, 6, 7, 4,
            # وجه علوي
            3, 2, 6, 6, 7, 3,
            # وجه سفلي
            0, 1, 5, 5, 4, 0,
            # وجه أيمن
            1, 5, 6, 6, 2, 1,
            # وجه أيسر
            0, 4, 7, 7, 3, 0
        ]
        
        return Mesh(vertices=cube_vertices, indices=cube_indices)
    
    def create_plane_mesh(self, size: float = 1.0, segments: int = 1) -> Mesh:
        """إنشاء شبكة مستوى"""
        vertices = []
        indices = []
        
        half_size = size / 2
        segment_size = size / segments
        
        # إنشاء الرؤوس
        for z in range(segments + 1):
            for x in range(segments + 1):
                pos_x = -half_size + x * segment_size
                pos_z = -half_size + z * segment_size
                
                vertex = Vertex(
                    position=(pos_x, 0, pos_z),
                    normal=(0, 1, 0),
                    texcoord=(x / segments, z / segments)
                )
                vertices.append(vertex)
        
        # إنشاء الفهارس
        for z in range(segments):
            for x in range(segments):
                top_left = z * (segments + 1) + x
                top_right = top_left + 1
                bottom_left = (z + 1) * (segments + 1) + x
                bottom_right = bottom_left + 1
                
                indices.extend([top_left, bottom_left, top_right])
                indices.extend([top_right, bottom_left, bottom_right])
        
        return Mesh(vertices=vertices, indices=indices)
    
    def create_sphere_mesh(self, radius: float = 0.5, 
                          sectors: int = 32, stacks: int = 16) -> Mesh:
        """إنشاء شبكة كرة"""
        vertices = []
        indices = []
        
        # إنشاء الرؤوس
        for i in range(stacks + 1):
            stack_angle = math.pi / 2 - i * (math.pi / stacks)
            xy = radius * math.cos(stack_angle)
            z = radius * math.sin(stack_angle)
            
            for j in range(sectors + 1):
                sector_angle = j * (2 * math.pi / sectors)
                
                x = xy * math.cos(sector_angle)
                y = xy * math.sin(sector_angle)
                
                nx = x / radius
                ny = y / radius
                nz = z / radius
                
                s = j / sectors
                t = i / stacks
                
                vertex = Vertex(
                    position=(x, y, z),
                    normal=(nx, ny, nz),
                    texcoord=(s, t)
                )
                vertices.append(vertex)
        
        # إنشاء الفهارس
        for i in range(stacks):
            k1 = i * (sectors + 1)
            k2 = k1 + sectors + 1
            
            for j in range(sectors):
                if i != 0:
                    indices.extend([k1, k2, k1 + 1])
                
                if i != stacks - 1:
                    indices.extend([k1 + 1, k2, k2 + 1])
                
                k1 += 1
                k2 += 1
        
        return Mesh(vertices=vertices, indices=indices)
    
    def add_mesh(self, name: str, mesh: Mesh):
        """إضافة شبكة"""
        gpu_mesh = GPUMesh(self.ctx, mesh)
        self.meshes[name] = gpu_mesh
    
    def get_mesh(self, name: str) -> Optional[GPUMesh]:
        """الحصول على شبكة"""
        return self.meshes.get(name)
    
    def load_mesh_from_file(self, name: str, path: Path) -> bool:
        """تحميل شبكة من ملف"""
        try:
            # هنا سيتم تنفيذ تحميل الشبكة من تنسيقات مثل OBJ, FBX, etc.
            # هذا تنفيذ مبسط
            if path.suffix.lower() == '.obj':
                mesh = self._load_obj_mesh(path)
                if mesh:
                    self.add_mesh(name, mesh)
                    return True
            
        except Exception as e:
            print(f"Failed to load mesh '{name}': {e}")
        
        return False
    
    def _load_obj_mesh(self, path: Path) -> Optional[Mesh]:
        """تحميل شبكة من ملف OBJ"""
        # هذا تنفيذ مبسط لتحميل ملفات OBJ
        vertices = []
        texcoords = []
        normals = []
        faces = []
        
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                
                if parts[0] == 'v':  # رأس
                    vertices.append(tuple(map(float, parts[1:4])))
                elif parts[0] == 'vt':  # إحداثيات نسيج
                    texcoords.append(tuple(map(float, parts[1:3])))
                elif parts[0] == 'vn':  # متجه عادي
                    normals.append(tuple(map(float, parts[1:4])))
                elif parts[0] == 'f':  # وجه
                    face = []
                    for part in parts[1:]:
                        indices = part.split('/')
                        v_idx = int(indices[0]) - 1 if indices[0] else 0
                        vt_idx = int(indices[1]) - 1 if len(indices) > 1 and indices[1] else 0
                        vn_idx = int(indices[2]) - 1 if len(indices) > 2 and indices[2] else 0
                        face.append((v_idx, vt_idx, vn_idx))
                    faces.append(face)
        
        # تحويل إلى تنسيق المحرك
        mesh_vertices = []
        mesh_indices = []
        vertex_map = {}
        
        for face in faces:
            face_indices = []
            for v_idx, vt_idx, vn_idx in face:
                key = (v_idx, vt_idx, vn_idx)
                
                if key not in vertex_map:
                    vertex = Vertex(
                        position=vertices[v_idx] if v_idx < len(vertices) else (0, 0, 0),
                        normal=normals[vn_idx] if vn_idx < len(normals) else (0, 0, 1),
                        texcoord=texcoords[vt_idx] if vt_idx < len(texcoords) else (0, 0)
                    )
                    mesh_vertices.append(vertex)
                    vertex_map[key] = len(mesh_vertices) - 1
                
                face_indices.append(vertex_map[key])
            
            # تحويل المضلع إلى مثلثات
            if len(face_indices) >= 3:
                for i in range(1, len(face_indices) - 1):
                    mesh_indices.extend([face_indices[0], face_indices[i], face_indices[i + 1]])
        
        return Mesh(vertices=mesh_vertices, indices=mesh_indices)
    
    def release_mesh(self, name: str):
        """تحرير شبكة"""
        if name in self.meshes:
            self.meshes[name].release()
            del self.meshes[name]

# ============================================================================
# Camera System
# ============================================================================

class Camera:
    """فئة الكاميرا"""
    
    def __init__(self, width: int, height: int, 
                 fov: float = 60.0, near: float = 0.1, far: float = 1000.0):
        self.width = width
        self.height = height
        self.fov = fov
        self.near = near
        self.far = far
        self.aspect_ratio = width / height
        
        self.position = np.array([0.0, 0.0, 5.0], dtype='f4')
        self.target = np.array([0.0, 0.0, 0.0], dtype='f4')
        self.up = np.array([0.0, 1.0, 0.0], dtype='f4')
        
        self.view_matrix = np.identity(4, dtype='f4')
        self.projection_matrix = np.identity(4, dtype='f4')
        
        self.update_view_matrix()
        self.update_projection_matrix()
    
    def update_view_matrix(self):
        """تحديث مصفوفة العرض"""
        # حساب متجهات الكاميرا
        zaxis = self.position - self.target
        zaxis = zaxis / np.linalg.norm(zaxis)
        
        xaxis = np.cross(self.up, zaxis)
        xaxis = xaxis / np.linalg.norm(xaxis)
        
        yaxis = np.cross(zaxis, xaxis)
        
        # بناء مصفوفة العرض
        self.view_matrix = np.array([
            [xaxis[0], yaxis[0], zaxis[0], 0],
            [xaxis[1], yaxis[1], zaxis[1], 0],
            [xaxis[2], yaxis[2], zaxis[2], 0],
            [-np.dot(xaxis, self.position), 
             -np.dot(yaxis, self.position), 
             -np.dot(zaxis, self.position), 1]
        ], dtype='f4')
    
    def update_projection_matrix(self):
        """تحديث مصفوفة الإسقاط"""
        f = 1.0 / math.tan(math.radians(self.fov) / 2.0)
        
        self.projection_matrix = np.array([
            [f / self.aspect_ratio, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, (self.far + self.near) / (self.near - self.far), -1],
            [0, 0, (2 * self.far * self.near) / (self.near - self.far), 0]
        ], dtype='f4')
    
    def look_at(self, position, target, up=None):
        """توجيه الكاميرا نحو نقطة"""
        self.position = np.array(position, dtype='f4')
        self.target = np.array(target, dtype='f4')
        if up:
            self.up = np.array(up, dtype='f4')
        self.update_view_matrix()
    
    def set_position(self, position):
        """تعيين موضع الكاميرا"""
        self.position = np.array(position, dtype='f4')
        self.update_view_matrix()
    
    def set_target(self, target):
        """تعيين هدف الكاميرا"""
        self.target = np.array(target, dtype='f4')
        self.update_view_matrix()
    
    def move(self, delta):
        """تحريك الكاميرا"""
        self.position += delta
        self.target += delta
        self.update_view_matrix()
    
    def rotate_around_target(self, angle_x: float, angle_y: float):
        """دوران الكاميرا حول الهدف"""
        # هذا تنفيذ مبسط للدوران
        import math
        radius = np.linalg.norm(self.position - self.target)
        
        # حساب الزوايا الحالية
        dx = self.position[0] - self.target[0]
        dy = self.position[1] - self.target[1]
        dz = self.position[2] - self.target[2]
        
        # تحديث الزوايا
        # هذا يحتاج إلى تنفيذ كامل باستخدام الكواتيرنيونات
        pass
    
    def get_view_projection_matrix(self):
        """الحصول على مصفوفة العرض والإسقاط"""
        return self.projection_matrix @ self.view_matrix

# ============================================================================
# Render System
# ============================================================================

class RenderSystem:
    """نظام التصيير"""
    
    def __init__(self, engine):
        self.engine = engine
        self.ctx = None
        self.shader_manager = None
        self.texture_manager = None
        self.mesh_manager = None
        self.camera = None
        
        self.render_queue = []
        self.lights = []
        self.frame_buffer = None
        
        self.stats = {
            'draw_calls': 0,
            'triangle_count': 0,
            'texture_binds': 0,
            'shader_binds': 0
        }
    
    def initialize(self, width: int, height: int):
        """تهيئة نظام التصيير"""
        try:
            # إنشاء سياق ModernGL
            self.ctx = moderngl.create_context()
            
            # تهيئة المديرين
            self.shader_manager = ShaderManager(self.ctx)
            self.texture_manager = TextureManager(self.ctx)
            self.mesh_manager = MeshManager(self.ctx)
            
            # إنشاء الكاميرا
            self.camera = Camera(width, height)
            
            # إنشاء مخزن مؤقت للإطار
            self.frame_buffer = self.ctx.framebuffer(
                color_attachments=[self.ctx.texture((width, height), 4)],
                depth_attachment=self.ctx.depth_texture((width, height))
            )
            
            # إعداد OpenGL
            self.ctx.enable(moderngl.DEPTH_TEST)
            self.ctx.enable(moderngl.CULL_FACE)
            self.ctx.cull_face = 'back'
            
            print("Render system initialized")
            return True
            
        except Exception as e:
            print(f"Failed to initialize render system: {e}")
            return False
    
    def update(self, delta_time: float):
        """تحديث نظام التصيير"""
        # تحديث الكاميرا
        self.camera.update_view_matrix()
        
        # مسح الإحصائيات
        self.stats = {
            'draw_calls': 0,
            'triangle_count': 0,
            'texture_binds': 0,
            'shader_binds': 0
        }
    
    def render(self, screen):
        """التصيير"""
        if not self.ctx:
            return
        
        # مسح المخزن المؤقت
        self.frame_buffer.use()
        self.ctx.clear(0.1, 0.1, 0.1, 1.0)
        
        # تصيير قائمة الانتظار
        for render_item in self.render_queue:
            self._render_item(render_item)
        
        # مسح قائمة الانتظار
        self.render_queue.clear()
        
        # نسخ المخزن المؤقت إلى الشاشة
        self._blit_to_screen(screen)
    
    def _render_item(self, render_item):
        """تصيير عنصر"""
        try:
            mesh = self.mesh_manager.get_mesh(render_item['mesh'])
            if not mesh:
                return
            
            shader = self.shader_manager.get_shader(render_item.get('shader', 'basic'))
            if not shader:
                return
            
            # ربط الشادر
            shader.bind()
            self.stats['shader_binds'] += 1
            
            # تعيين المتغيرات المنتظمة
            shader.set_uniform('u_projection', self.camera.projection_matrix.flatten())
            shader.set_uniform('u_view', self.camera.view_matrix.flatten())
            shader.set_uniform('u_model', render_item['transform'].flatten())
            
            # ربط النسيج
            if 'texture' in render_item:
                texture = self.texture_manager.get_texture(render_item['texture'])
                if texture:
                    texture.bind(0)
                    shader.set_uniform('u_texture', 0)
                    shader.set_uniform('u_use_texture', True)
                    self.stats['texture_binds'] += 1
            
            # التصيير
            mesh.render()
            self.stats['draw_calls'] += 1
            self.stats['triangle_count'] += len(mesh.mesh.indices) // 3
            
        except Exception as e:
            print(f"Error rendering item: {e}")
    
    def _blit_to_screen(self, screen):
        """نسخ المخزن المؤقت إلى الشاشة"""
        # هذا تنفيذ مبسط
        # في التنفيذ الحقيقي، سيتم نسخ بيانات النسيج إلى سطح PyGame
        pass
    
    def queue_render(self, mesh_name: str, transform, shader: str = 'basic', 
                    texture: str = None, material: Material = None):
        """إضافة عنصر إلى قائمة انتظار التصيير"""
        self.render_queue.append({
            'mesh': mesh_name,
            'transform': transform,
            'shader': shader,
            'texture': texture,
            'material': material
        })
    
    def add_light(self, position, color, intensity: float = 1.0):
        """إضافة ضوء"""
        self.lights.append({
            'position': position,
            'color': color,
            'intensity': intensity
        })
    
    def clear_lights(self):
        """مسح الأضواء"""
        self.lights.clear()
    
    def shutdown(self):
        """إيقاف نظام التصيير"""
        if self.frame_buffer:
            self.frame_buffer.release()
        
        if self.mesh_manager:
            for mesh in self.mesh_manager.meshes.values():
                mesh.release()
        
        if self.texture_manager:
            for texture in self.texture_manager.textures.values():
                texture.release()
        
        print("Render system shutdown")