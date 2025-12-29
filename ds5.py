"""
GameEnginePro - Network Module
نظام الشبكة متعدد اللاعبين
"""

import socket
import threading
import queue
import pickle
import zlib
import hashlib
import time
import struct
from typing import Dict, List, Tuple, Optional, Any, Union
from enum import Enum, auto
from dataclasses import dataclass, field
import json
import base64
from collections import defaultdict, deque
import select
import errno

# ============================================================================
# Network Types
# ============================================================================

class NetworkRole(Enum):
    """أدوار الشبكة"""
    SERVER = auto()
    CLIENT = auto()
    PEER = auto()

class MessageType(Enum):
    """أنواع الرسائل"""
    # رسائل التحكم
    CONNECT_REQUEST = auto()
    CONNECT_RESPONSE = auto()
    DISCONNECT = auto()
    HEARTBEAT = auto()
    
    # رسائل اللعبة
    PLAYER_JOINED = auto()
    PLAYER_LEFT = auto()
    PLAYER_STATE = auto()
    ENTITY_STATE = auto()
    INPUT_STATE = auto()
    CHAT_MESSAGE = auto()
    
    # رسائل العالم
    WORLD_STATE = auto()
    ENTITY_CREATE = auto()
    ENTITY_DESTROY = auto()
    ENTITY_UPDATE = auto()
    
    # رسائل النظام
    PING = auto()
    PONG = auto()
    ERROR = auto()
    COMMAND = auto()

class ConnectionState(Enum):
    """حالات الاتصال"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    AUTHENTICATED = auto()
    IN_GAME = auto()

@dataclass
class NetworkPlayer:
    """لاعب شبكة"""
    player_id: int
    username: str
    connection_id: int
    address: Tuple[str, int]
    ping: float = 0.0
    last_heartbeat: float = 0.0
    state: ConnectionState = ConnectionState.DISCONNECTED
    custom_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class NetworkEntity:
    """كيان شبكة"""
    entity_id: int
    owner_id: int  # صاحب الكيان (0 للخادم)
    prefab_name: str
    position: Tuple[float, float, float]
    rotation: Tuple[float, float, float, float]  # كواتيرنيون
    components: Dict[str, Any] = field(default_factory=dict)
    dirty: bool = True  # يحتاج إلى مزامنة
    last_update: float = 0.0

@dataclass
class NetworkMessage:
    """رسالة شبكة"""
    message_id: int
    message_type: MessageType
    sender_id: int
    target_id: int = 0  # 0 للجميع
    data: Any = None
    timestamp: float = field(default_factory=time.time)
    reliable: bool = False
    sequence: int = 0
    ack_required: bool = False
    
    def serialize(self) -> bytes:
        """تسلسل الرسالة"""
        try:
            # إنشاء رأس الرسالة
            header = struct.pack(
                '!IIIHHII',
                self.message_id,
                self.sender_id,
                self.target_id,
                self.message_type.value,
                1 if self.reliable else 0,
                self.sequence,
                int(self.timestamp * 1000)  # تحويل إلى مللي ثانية
            )
            
            # تسلسل البيانات
            if self.data is None:
                data_bytes = b''
            elif isinstance(self.data, (dict, list)):
                data_bytes = json.dumps(self.data, ensure_ascii=False).encode('utf-8')
            else:
                data_bytes = pickle.dumps(self.data)
            
            # ضغط البيانات
            if len(data_bytes) > 100:  # ضغط البيانات الكبيرة فقط
                data_bytes = zlib.compress(data_bytes)
                compressed = 1
            else:
                compressed = 0
            
            # إضافة طول البيانات وعلامة الضغط
            data_header = struct.pack('!IB', len(data_bytes), compressed)
            
            # حساب checksum
            checksum_data = header + data_header + data_bytes
            checksum = hashlib.md5(checksum_data).digest()[:4]
            
            return header + data_header + checksum + data_bytes
            
        except Exception as e:
            print(f"Failed to serialize message: {e}")
            return b''
    
    @classmethod
    def deserialize(cls, data: bytes) -> Optional['NetworkMessage']:
        """إلغاء تسلسل الرسالة"""
        try:
            if len(data) < 29:  # الحد الأدنى للحجم
                return None
            
            # قراءة الرأس
            header = data[:24]
            message_id, sender_id, target_id, msg_type_val, reliable_flag, sequence, timestamp_ms = struct.unpack('!IIIHHII', header)
            
            # قراءة رأس البيانات
            data_header = data[24:29]
            data_length, compressed = struct.unpack('!IB', data_header)
            
            # قراءة checksum
            checksum = data[29:33]
            
            # قراءة البيانات
            data_start = 33
            data_end = data_start + data_length
            
            if data_end > len(data):
                return None
            
            data_bytes = data[data_start:data_end]
            
            # التحقق من checksum
            checksum_data = header + data_header + data_bytes
            expected_checksum = hashlib.md5(checksum_data).digest()[:4]
            
            if checksum != expected_checksum:
                print("Checksum mismatch")
                return None
            
            # فك ضغط البيانات إذا لزم الأمر
            if compressed:
                try:
                    data_bytes = zlib.decompress(data_bytes)
                except:
                    print("Failed to decompress data")
                    return None
            
            # تحليل البيانات
            if data_bytes:
                try:
                    # محاولة تحليل JSON أولاً
                    data_obj = json.loads(data_bytes.decode('utf-8'))
                except:
                    try:
                        # ثم محاولة pickle
                        data_obj = pickle.loads(data_bytes)
                    except:
                        data_obj = data_bytes
            else:
                data_obj = None
            
            return cls(
                message_id=message_id,
                message_type=MessageType(msg_type_val),
                sender_id=sender_id,
                target_id=target_id,
                data=data_obj,
                timestamp=timestamp_ms / 1000.0,
                reliable=reliable_flag == 1,
                sequence=sequence
            )
            
        except Exception as e:
            print(f"Failed to deserialize message: {e}")
            return None

# ============================================================================
# Reliable Messaging
# ============================================================================

class ReliableChannel:
    """قناة اتصال موثوقة"""
    
    def __init__(self, channel_id: int, max_sequence: int = 65535):
        self.channel_id = channel_id
        self.max_sequence = max_sequence
        self.next_send_sequence = 1
        self.next_receive_sequence = 1
        self.sent_packets = {}
        self.received_packets = {}
        self.ack_bits = 0
        self.acks = []
        
        # الإحصائيات
        self.stats = {
            'packets_sent': 0,
            'packets_received': 0,
            'packets_lost': 0,
            'bytes_sent': 0,
            'bytes_received': 0
        }
    
    def send_message(self, message: NetworkMessage) -> int:
        """إرسال رسالة موثوقة"""
        sequence = self.next_send_sequence
        message.sequence = sequence
        message.reliable = True
        
        self.sent_packets[sequence] = {
            'message': message,
            'timestamp': time.time(),
            'retries': 0,
            'acked': False
        }
        
        self.next_send_sequence = (self.next_send_sequence + 1) % self.max_sequence
        self.stats['packets_sent'] += 1
        self.stats['bytes_sent'] += len(message.serialize())
        
        return sequence
    
    def receive_message(self, message: NetworkMessage) -> bool:
        """استقبال رسالة موثوقة"""
        if message.sequence < self.next_receive_sequence:
            # تسلسل قديم
            return False
        
        self.received_packets[message.sequence] = {
            'message': message,
            'timestamp': time.time()
        }
        
        # تحديث تسلسل الاستقبال
        while self.next_receive_sequence in self.received_packets:
            self.next_receive_sequence = (self.next_receive_sequence + 1) % self.max_sequence
        
        self.stats['packets_received'] += 1
        self.stats['bytes_received'] += len(message.serialize())
        
        return True
    
    def process_ack(self, ack_sequence: int, ack_bits: int):
        """معالجة تأكيد الاستلام"""
        # التحقق من الرزم المؤكدة
        for sequence in list(self.sent_packets.keys()):
            if sequence <= ack_sequence:
                diff = ack_sequence - sequence
                if diff < 32:  # ضمن نطاق 32 رزمة
                    acked = (ack_bits >> diff) & 1
                    if acked:
                        self.sent_packets[sequence]['acked'] = True
        
        # إزالة الرزم المؤكدة القديمة
        oldest = ack_sequence - 32
        for sequence in list(self.sent_packets.keys()):
            if sequence < oldest:
                if not self.sent_packets[sequence]['acked']:
                    self.stats['packets_lost'] += 1
                del self.sent_packets[sequence]
    
    def generate_ack(self) -> Tuple[int, int]:
        """توليد تأكيد استلام"""
        ack_sequence = (self.next_receive_sequence - 1) % self.max_sequence
        ack_bits = 0
        
        for i in range(32):
            sequence = (ack_sequence - i) % self.max_sequence
            if sequence in self.received_packets:
                ack_bits |= (1 << i)
        
        return ack_sequence, ack_bits
    
    def resend_packets(self, timeout: float = 0.5):
        """إعادة إرسال الرزم المنتهية صلاحيتها"""
        current_time = time.time()
        to_resend = []
        
        for sequence, packet in self.sent_packets.items():
            if packet['acked']:
                continue
            
            elapsed = current_time - packet['timestamp']
            if elapsed > timeout:
                packet['retries'] += 1
                packet['timestamp'] = current_time
                to_resend.append(packet['message'])
                
                if packet['retries'] > 5:  # الحد الأقصى للمحاولات
                    del self.sent_packets[sequence]
                    self.stats['packets_lost'] += 1
        
        return to_resend
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات القناة"""
        unacked = sum(1 for p in self.sent_packets.values() if not p['acked'])
        
        return {
            **self.stats,
            'unacked_packets': unacked,
            'sent_packets_buffer': len(self.sent_packets),
            'received_packets_buffer': len(self.received_packets),
            'next_send_sequence': self.next_send_sequence,
            'next_receive_sequence': self.next_receive_sequence
        }

# ============================================================================
# Network Client
# ============================================================================

class NetworkClient:
    """عميل الشبكة"""
    
    def __init__(self, server_address: str = "127.0.0.1", server_port: int = 7777):
        self.server_address = server_address
        self.server_port = server_port
        self.socket = None
        self.state = ConnectionState.DISCONNECTED
        self.player_id = 0
        self.username = ""
        
        # القنوات
        self.channels: Dict[int, ReliableChannel] = {
            0: ReliableChannel(0),  # قناة التحكم
            1: ReliableChannel(1),  # قناة اللعبة
            2: ReliableChannel(2)   # قناة الصوت
        }
        
        # الطوابير
        self.incoming_queue = queue.Queue()
        self.outgoing_queue = queue.Queue()
        self.event_queue = queue.Queue()
        
        # الخيوط
        self.receive_thread = None
        self.send_thread = None
        self.process_thread = None
        self.running = False
        
        # التوقيت
        self.last_heartbeat = 0
        self.ping = 0.0
        self.last_ping_time = 0
        
        # الإحصائيات
        self.stats = {
            'total_messages_sent': 0,
            'total_messages_received': 0,
            'connection_time': 0,
            'start_time': 0
        }
        
        # المعالجات
        self.message_handlers = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """تسجيل المعالجات الافتراضية"""
        self.message_handlers[MessageType.CONNECT_RESPONSE] = self._handle_connect_response
        self.message_handlers[MessageType.DISCONNECT] = self._handle_disconnect
        self.message_handlers[MessageType.HEARTBEAT] = self._handle_heartbeat
        self.message_handlers[MessageType.PLAYER_JOINED] = self._handle_player_joined
        self.message_handlers[MessageType.PLAYER_LEFT] = self._handle_player_left
        self.message_handlers[MessageType.ENTITY_STATE] = self._handle_entity_state
        self.message_handlers[MessageType.WORLD_STATE] = self._handle_world_state
        self.message_handlers[MessageType.PONG] = self._handle_pong
    
    def connect(self, username: str, password: str = "") -> bool:
        """الاتصال بالخادم"""
        if self.state != ConnectionState.DISCONNECTED:
            return False
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(1.0)
            self.socket.setblocking(False)
            
            self.username = username
            self.state = ConnectionState.CONNECTING
            
            # إرسال طلب الاتصال
            connect_msg = NetworkMessage(
                message_id=1,
                message_type=MessageType.CONNECT_REQUEST,
                sender_id=0,
                data={
                    'username': username,
                    'password': password,
                    'version': '1.0.0'
                },
                reliable=True
            )
            
            self._send_message(connect_msg)
            
            # بدء الخيوط
            self.running = True
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
            self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
            
            self.receive_thread.start()
            self.send_thread.start()
            self.process_thread.start()
            
            self.stats['start_time'] = time.time()
            
            print(f"Connecting to {self.server_address}:{self.server_port}...")
            return True
            
        except Exception as e:
            print(f"Failed to connect: {e}")
            self.disconnect()
            return False
    
    def disconnect(self, reason: str = "Client disconnected"):
        """قطع الاتصال"""
        self.running = False
        
        # إرسال رسالة قطع الاتصال
        if self.state != ConnectionState.DISCONNECTED:
            disconnect_msg = NetworkMessage(
                message_id=0,
                message_type=MessageType.DISCONNECT,
                sender_id=self.player_id,
                data={'reason': reason},
                reliable=True
            )
            
            try:
                self._send_message(disconnect_msg)
            except:
                pass
        
        # إيقاف الخيوط
        if self.receive_thread:
            self.receive_thread.join(timeout=1)
        if self.send_thread:
            self.send_thread.join(timeout=1)
        if self.process_thread:
            self.process_thread.join(timeout=1)
        
        # إغلاق المقبس
        if self.socket:
            self.socket.close()
            self.socket = None
        
        self.state = ConnectionState.DISCONNECTED
        self.stats['connection_time'] = time.time() - self.stats['start_time']
        
        print(f"Disconnected: {reason}")
    
    def _receive_loop(self):
        """حلقة الاستقبال"""
        while self.running:
            try:
                # التحقق من البيانات الواردة
                ready = select.select([self.socket], [], [], 0.1)
                if not ready[0]:
                    continue
                
                data, addr = self.socket.recvfrom(8192)
                
                if addr[0] != self.server_address or addr[1] != self.server_port:
                    continue  # تجاهل الرسائل من عناوين أخرى
                
                # إلغاء تسلسل الرسالة
                message = NetworkMessage.deserialize(data)
                if not message:
                    continue
                
                # وضع الرسالة في قائمة الانتظار
                self.incoming_queue.put(message)
                self.stats['total_messages_received'] += 1
                
            except socket.timeout:
                continue
            except socket.error as e:
                if e.errno != errno.EAGAIN:
                    print(f"Socket error in receive loop: {e}")
                    break
            except Exception as e:
                print(f"Error in receive loop: {e}")
                break
    
    def _send_loop(self):
        """حلقة الإرسال"""
        while self.running:
            try:
                # إعادة إرسال الرزم الموثوقة المنتهية الصلاحية
                for channel in self.channels.values():
                    resend_messages = channel.resend_packets()
                    for message in resend_messages:
                        self.outgoing_queue.put(message)
                
                # إرسال الرزم في قائمة الانتظار
                while not self.outgoing_queue.empty():
                    message = self.outgoing_queue.get_nowait()
                    
                    # تسلسل الرسالة
                    data = message.serialize()
                    if not data:
                        continue
                    
                    try:
                        self.socket.sendto(data, (self.server_address, self.server_port))
                        self.stats['total_messages_sent'] += 1
                    except Exception as e:
                        print(f"Failed to send message: {e}")
                
                # إرسال نبضات القلب
                current_time = time.time()
                if current_time - self.last_heartbeat > 1.0:  # كل ثانية
                    self._send_heartbeat()
                    self.last_heartbeat = current_time
                
                time.sleep(0.01)  # 10ms
                
            except Exception as e:
                print(f"Error in send loop: {e}")
                break
    
    def _process_loop(self):
        """حلقة المعالجة"""
        while self.running:
            try:
                # معالجة الرسائل الواردة
                while not self.incoming_queue.empty():
                    message = self.incoming_queue.get_nowait()
                    self._process_message(message)
                
                time.sleep(0.001)  # 1ms
                
            except Exception as e:
                print(f"Error in process loop: {e}")
                break
    
    def _process_message(self, message: NetworkMessage):
        """معالجة رسالة"""
        # معالجة الرسائل الموثوقة
        if message.reliable:
            channel = self.channels.get(message.sender_id % 3, self.channels[0])
            if not channel.receive_message(message):
                return  # رسالة مكررة أو خارج التسلسل
        
        # استدعاء المعالج المناسب
        handler = self.message_handlers.get(message.message_type)
        if handler:
            handler(message)
        
        # وضع الحدث في قائمة الانتظار
        self.event_queue.put({
            'type': message.message_type,
            'data': message.data,
            'sender': message.sender_id,
            'timestamp': message.timestamp
        })
    
    def _send_message(self, message: NetworkMessage):
        """إرسال رسالة"""
        if message.reliable:
            channel = self.channels.get(message.sender_id % 3, self.channels[0])
            channel.send_message(message)
        
        self.outgoing_queue.put(message)
    
    def send_chat_message(self, text: str):
        """إرسال رسالة محادثة"""
        if self.state != ConnectionState.IN_GAME:
            return
        
        chat_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.CHAT_MESSAGE,
            sender_id=self.player_id,
            data={'text': text},
            reliable=True
        )
        
        self._send_message(chat_msg)
    
    def send_player_state(self, state_data: Dict[str, Any]):
        """إرسال حالة اللاعب"""
        if self.state != ConnectionState.IN_GAME:
            return
        
        state_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.PLAYER_STATE,
            sender_id=self.player_id,
            data=state_data,
            reliable=False  # غير موثوق لأننا نرسله بشكل متكرر
        )
        
        self._send_message(state_msg)
    
    def send_input_state(self, input_data: Dict[str, Any]):
        """إرسال حالة الإدخال"""
        if self.state != ConnectionState.IN_GAME:
            return
        
        input_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.INPUT_STATE,
            sender_id=self.player_id,
            data=input_data,
            reliable=False
        )
        
        self._send_message(input_msg)
    
    def _send_heartbeat(self):
        """إرسال نبضة قلب"""
        heartbeat_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.HEARTBEAT,
            sender_id=self.player_id,
            data={'timestamp': time.time()},
            reliable=False
        )
        
        self._send_message(heartbeat_msg)
        
        # إرسال ping كل 5 ثواني
        if time.time() - self.last_ping_time > 5.0:
            self._send_ping()
            self.last_ping_time = time.time()
    
    def _send_ping(self):
        """إرسال ping"""
        ping_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.PING,
            sender_id=self.player_id,
            data={'send_time': time.time()},
            reliable=False
        )
        
        self._send_message(ping_msg)
    
    # معالجات الرسائل
    def _handle_connect_response(self, message: NetworkMessage):
        """معالجة استجابة الاتصال"""
        if self.state != ConnectionState.CONNECTING:
            return
        
        if message.data.get('success'):
            self.player_id = message.data['player_id']
            self.state = ConnectionState.CONNECTED
            print(f"Connected as player {self.player_id}")
            
            # الانتقال إلى حالة المصادقة
            self.state = ConnectionState.AUTHENTICATED
            
            # الانتقال إلى حالة اللعبة
            self.state = ConnectionState.IN_GAME
            print("Entered game state")
        else:
            reason = message.data.get('reason', 'Unknown error')
            print(f"Connection failed: {reason}")
            self.disconnect(reason)
    
    def _handle_disconnect(self, message: NetworkMessage):
        """معالجة قطع الاتصال"""
        reason = message.data.get('reason', 'Server disconnected')
        print(f"Server disconnected: {reason}")
        self.disconnect(reason)
    
    def _handle_heartbeat(self, message: NetworkMessage):
        """معالجة نبضة القلب"""
        # تحديث وقت آخر اتصال
        pass
    
    def _handle_player_joined(self, message: NetworkMessage):
        """معالجة انضمام لاعب"""
        player_id = message.data['player_id']
        username = message.data['username']
        print(f"Player {username} (ID: {player_id}) joined the game")
    
    def _handle_player_left(self, message: NetworkMessage):
        """معالجة مغادرة لاعب"""
        player_id = message.data['player_id']
        reason = message.data.get('reason', 'Disconnected')
        print(f"Player {player_id} left: {reason}")
    
    def _handle_entity_state(self, message: NetworkMessage):
        """معالجة حالة كيان"""
        # سيتم معالجتها في اللعبة
        pass
    
    def _handle_world_state(self, message: NetworkMessage):
        """معالجة حالة العالم"""
        # سيتم معالجتها في اللعبة
        pass
    
    def _handle_pong(self, message: NetworkMessage):
        """معالجة pong"""
        send_time = message.data.get('send_time')
        if send_time:
            self.ping = (time.time() - send_time) * 1000  # مللي ثانية
    
    def get_event(self) -> Optional[Dict[str, Any]]:
        """الحصول على حدث من قائمة الانتظار"""
        try:
            return self.event_queue.get_nowait()
        except queue.Empty:
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات العميل"""
        channel_stats = {}
        for channel_id, channel in self.channels.items():
            channel_stats[f'channel_{channel_id}'] = channel.get_statistics()
        
        return {
            **self.stats,
            'state': self.state.name,
            'player_id': self.player_id,
            'username': self.username,
            'ping': self.ping,
            'channels': channel_stats,
            'queues': {
                'incoming': self.incoming_queue.qsize(),
                'outgoing': self.outgoing_queue.qsize(),
                'events': self.event_queue.qsize()
            }
        }

# ============================================================================
# Network Server
# ============================================================================

class NetworkServer:
    """خادم الشبكة"""
    
    def __init__(self, port: int = 7777, max_players: int = 16):
        self.port = port
        self.max_players = max_players
        self.socket = None
        self.running = False
        
        # اللاعبون
        self.players: Dict[int, NetworkPlayer] = {}
        self.next_player_id = 1
        
        # الاتصالات
        self.connections: Dict[Tuple[str, int], int] = {}  # عنوان -> معرف لاعب
        
        # القنوات
        self.channels: Dict[int, ReliableChannel] = {}
        
        # الطوابير
        self.incoming_queue = queue.Queue()
        self.outgoing_queue = queue.Queue()
        self.broadcast_queue = queue.Queue()
        
        # الخيوط
        self.receive_thread = None
        self.send_thread = None
        self.process_thread = None
        
        # التوقيت
        self.start_time = time.time()
        
        # الإحصائيات
        self.stats = {
            'total_connections': 0,
            'current_connections': 0,
            'total_messages_received': 0,
            'total_messages_sent': 0,
            'bytes_received': 0,
            'bytes_sent': 0
        }
        
        # المعالجات
        self.message_handlers = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """تسجيل المعالجات الافتراضية"""
        self.message_handlers[MessageType.CONNECT_REQUEST] = self._handle_connect_request
        self.message_handlers[MessageType.DISCONNECT] = self._handle_disconnect
        self.message_handlers[MessageType.HEARTBEAT] = self._handle_heartbeat
        self.message_handlers[MessageType.CHAT_MESSAGE] = self._handle_chat_message
        self.message_handlers[MessageType.PLAYER_STATE] = self._handle_player_state
        self.message_handlers[MessageType.INPUT_STATE] = self._handle_input_state
        self.message_handlers[MessageType.PING] = self._handle_ping
    
    def start(self) -> bool:
        """بدء الخادم"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('0.0.0.0', self.port))
            self.socket.setblocking(False)
            
            self.running = True
            
            # بدء الخيوط
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
            self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
            
            self.receive_thread.start()
            self.send_thread.start()
            self.process_thread.start()
            
            print(f"Server started on port {self.port}")
            return True
            
        except Exception as e:
            print(f"Failed to start server: {e}")
            return False
    
    def stop(self):
        """إيقاف الخادم"""
        self.running = False
        
        # إرسال رسائل قطع الاتصال لجميع اللاعبين
        for player in list(self.players.values()):
            self._disconnect_player(player.player_id, "Server shutting down")
        
        # إيقاف الخيوط
        if self.receive_thread:
            self.receive_thread.join(timeout=1)
        if self.send_thread:
            self.send_thread.join(timeout=1)
        if self.process_thread:
            self.process_thread.join(timeout=1)
        
        # إغلاق المقبس
        if self.socket:
            self.socket.close()
            self.socket = None
        
        print("Server stopped")
    
    def _receive_loop(self):
        """حلقة الاستقبال"""
        while self.running:
            try:
                # التحقق من البيانات الواردة
                ready = select.select([self.socket], [], [], 0.1)
                if not ready[0]:
                    continue
                
                data, addr = self.socket.recvfrom(8192)
                
                # إلغاء تسلسل الرسالة
                message = NetworkMessage.deserialize(data)
                if not message:
                    continue
                
                # ربط الرسالة باللاعب
                player_id = self.connections.get(addr, 0)
                message.sender_id = player_id
                
                # تحديث وقت آخر اتصال للاعب
                if player_id in self.players:
                    self.players[player_id].last_heartbeat = time.time()
                
                # وضع الرسالة في قائمة الانتظار
                self.incoming_queue.put((message, addr))
                self.stats['total_messages_received'] += 1
                self.stats['bytes_received'] += len(data)
                
            except socket.timeout:
                continue
            except socket.error as e:
                if e.errno != errno.EAGAIN:
                    print(f"Socket error in receive loop: {e}")
                    break
            except Exception as e:
                print(f"Error in receive loop: {e}")
                break
    
    def _send_loop(self):
        """حلقة الإرسال"""
        while self.running:
            try:
                # إرسال الرسائل في قوائم الانتظار
                self._process_outgoing_queue()
                self._process_broadcast_queue()
                
                # إعادة إرسال الرزم الموثوقة المنتهية الصلاحية
                for channel in self.channels.values():
                    resend_messages = channel.resend_packets()
                    for message in resend_messages:
                        self.outgoing_queue.put((message, None))  # None يعني إرسال للجميع
                
                # التحقق من اللاعبين غير النشطين
                self._check_inactive_players()
                
                time.sleep(0.01)  # 10ms
                
            except Exception as e:
                print(f"Error in send loop: {e}")
                break
    
    def _process_outgoing_queue(self):
        """معالجة قائمة انتظار الإرسال"""
        while not self.outgoing_queue.empty():
            message, target = self.outgoing_queue.get_nowait()
            
            # تسلسل الرسالة
            data = message.serialize()
            if not data:
                continue
            
            try:
                if target:  # إرسال لهدف محدد
                    self.socket.sendto(data, target)
                    self.stats['total_messages_sent'] += 1
                    self.stats['bytes_sent'] += len(data)
                else:  # بث للجميع
                    for player in self.players.values():
                        if player.state == ConnectionState.IN_GAME:
                            self.socket.sendto(data, player.address)
                            self.stats['total_messages_sent'] += 1
                            self.stats['bytes_sent'] += len(data)
                
            except Exception as e:
                print(f"Failed to send message: {e}")
    
    def _process_broadcast_queue(self):
        """معالجة قائمة انتظار البث"""
        while not self.broadcast_queue.empty():
            message = self.broadcast_queue.get_nowait()
            
            # إرسال للجميع
            data = message.serialize()
            if not data:
                continue
            
            try:
                for player in self.players.values():
                    if player.state == ConnectionState.IN_GAME and player.player_id != message.sender_id:
                        self.socket.sendto(data, player.address)
                        self.stats['total_messages_sent'] += 1
                        self.stats['bytes_sent'] += len(data)
                
            except Exception as e:
                print(f"Failed to broadcast message: {e}")
    
    def _process_loop(self):
        """حلقة المعالجة"""
        while self.running:
            try:
                # معالجة الرسائل الواردة
                while not self.incoming_queue.empty():
                    message, addr = self.incoming_queue.get_nowait()
                    self._process_message(message, addr)
                
                time.sleep(0.001)  # 1ms
                
            except Exception as e:
                print(f"Error in process loop: {e}")
                break
    
    def _process_message(self, message: NetworkMessage, addr: Tuple[str, int]):
        """معالجة رسالة"""
        # إنشاء قناة إذا لزم الأمر
        if message.sender_id not in self.channels:
            self.channels[message.sender_id] = ReliableChannel(message.sender_id)
        
        channel = self.channels[message.sender_id]
        
        # معالجة الرسائل الموثوقة
        if message.reliable:
            if not channel.receive_message(message):
                return  # رسالة مكررة أو خارج التسلسل
            
            # إرسال تأكيد الاستلام
            ack_sequence, ack_bits = channel.generate_ack()
            # (سيتم إرسال ACK في الرسالة التالية)
        
        # استدعاء المعالج المناسب
        handler = self.message_handlers.get(message.message_type)
        if handler:
            handler(message, addr)
    
    def _check_inactive_players(self):
        """التحقق من اللاعبين غير النشطين"""
        current_time = time.time()
        to_remove = []
        
        for player in self.players.values():
            if current_time - player.last_heartbeat > 10.0:  # 10 ثواني
                to_remove.append(player.player_id)
        
        for player_id in to_remove:
            self._disconnect_player(player_id, "Timeout")
    
    def _handle_connect_request(self, message: NetworkMessage, addr: Tuple[str, int]):
        """معالجة طلب الاتصال"""
        # التحقق من عدد اللاعبين
        if len(self.players) >= self.max_players:
            response = NetworkMessage(
                message_id=message.message_id,
                message_type=MessageType.CONNECT_RESPONSE,
                sender_id=0,
                target_id=0,
                data={
                    'success': False,
                    'reason': 'Server is full'
                },
                reliable=True
            )
            self.outgoing_queue.put((response, addr))
            return
        
        # التحقق من النسخة
        client_version = message.data.get('version', '0.0.0')
        if client_version != '1.0.0':
            response = NetworkMessage(
                message_id=message.message_id,
                message_type=MessageType.CONNECT_RESPONSE,
                sender_id=0,
                target_id=0,
                data={
                    'success': False,
                    'reason': f'Version mismatch. Server: 1.0.0, Client: {client_version}'
                },
                reliable=True
            )
            self.outgoing_queue.put((response, addr))
            return
        
        # إنشاء لاعب جديد
        player_id = self.next_player_id
        self.next_player_id += 1
        
        username = message.data.get('username', f'Player{player_id}')
        
        player = NetworkPlayer(
            player_id=player_id,
            username=username,
            connection_id=0,
            address=addr,
            ping=0.0,
            last_heartbeat=time.time(),
            state=ConnectionState.CONNECTED
        )
        
        self.players[player_id] = player
        self.connections[addr] = player_id
        self.stats['total_connections'] += 1
        self.stats['current_connections'] = len(self.players)
        
        # إرسال استجابة الاتصال
        response = NetworkMessage(
            message_id=message.message_id,
            message_type=MessageType.CONNECT_RESPONSE,
            sender_id=0,
            target_id=player_id,
            data={
                'success': True,
                'player_id': player_id,
                'message': 'Welcome to the server!'
            },
            reliable=True
        )
        
        self.outgoing_queue.put((response, addr))
        
        # إعلام اللاعبين الآخرين
        join_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.PLAYER_JOINED,
            sender_id=player_id,
            data={
                'player_id': player_id,
                'username': username
            },
            reliable=True
        )
        
        self.broadcast_queue.put(join_msg)
        
        print(f"Player {username} (ID: {player_id}) connected from {addr[0]}:{addr[1]}")
    
    def _handle_disconnect(self, message: NetworkMessage, addr: Tuple[str, int]):
        """معالجة قطع الاتصال"""
        player_id = message.sender_id
        if player_id in self.players:
            reason = message.data.get('reason', 'Disconnected')
            self._disconnect_player(player_id, reason)
    
    def _handle_heartbeat(self, message: NetworkMessage, addr: Tuple[str, int]):
        """معالجة نبضة القلب"""
        # تم تحديث last_heartbeat في _process_message
        pass
    
    def _handle_chat_message(self, message: NetworkMessage, addr: Tuple[str, int]):
        """معالجة رسالة محادثة"""
        player_id = message.sender_id
        if player_id not in self.players:
            return
        
        text = message.data.get('text', '')
        if not text.strip():
            return
        
        # بث رسالة المحادثة
        chat_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.CHAT_MESSAGE,
            sender_id=player_id,
            data={
                'player_id': player_id,
                'username': self.players[player_id].username,
                'text': text,
                'timestamp': time.time()
            },
            reliable=True
        )
        
        self.broadcast_queue.put(chat_msg)
        
        print(f"[CHAT] {self.players[player_id].username}: {text}")
    
    def _handle_player_state(self, message: NetworkMessage, addr: Tuple[str, int]):
        """معالجة حالة اللاعب"""
        player_id = message.sender_id
        if player_id not in self.players:
            return
        
        # تحديث حالة اللاعب
        # (سيتم معالجتها في اللعبة)
        
        # بث حالة اللاعب للآخرين
        state_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.PLAYER_STATE,
            sender_id=player_id,
            data=message.data,
            reliable=False
        )
        
        self.broadcast_queue.put(state_msg)
    
    def _handle_input_state(self, message: NetworkMessage, addr: Tuple[str, int]):
        """معالجة حالة الإدخال"""
        player_id = message.sender_id
        if player_id not in self.players:
            return
        
        # بث حالة الإدخال للآخرين (للتوقع على الجانب الآخر)
        input_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.INPUT_STATE,
            sender_id=player_id,
            data=message.data,
            reliable=False
        )
        
        self.broadcast_queue.put(input_msg)
    
    def _handle_ping(self, message: NetworkMessage, addr: Tuple[str, int]):
        """معالجة ping"""
        player_id = message.sender_id
        if player_id not in self.players:
            return
        
        # إرسال pong
        pong_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.PONG,
            sender_id=0,
            target_id=player_id,
            data={
                'send_time': message.data.get('send_time', time.time())
            },
            reliable=False
        )
        
        self.outgoing_queue.put((pong_msg, addr))
    
    def _disconnect_player(self, player_id: int, reason: str):
        """قطع اتصال لاعب"""
        if player_id not in self.players:
            return
        
        player = self.players[player_id]
        
        # إزالة من القوائم
        for addr, pid in list(self.connections.items()):
            if pid == player_id:
                del self.connections[addr]
                break
        
        if player_id in self.channels:
            del self.channels[player_id]
        
        del self.players[player_id]
        
        self.stats['current_connections'] = len(self.players)
        
        # إعلام اللاعبين الآخرين
        left_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.PLAYER_LEFT,
            sender_id=player_id,
            data={
                'player_id': player_id,
                'username': player.username,
                'reason': reason
            },
            reliable=True
        )
        
        self.broadcast_queue.put(left_msg)
        
        print(f"Player {player.username} (ID: {player_id}) disconnected: {reason}")
    
    def broadcast_message(self, message: NetworkMessage, exclude_player_id: int = 0):
        """بث رسالة لجميع اللاعبين"""
        if exclude_player_id:
            message.target_id = 0  # للجميع
            # سيتم استبعاد exclude_player_id في _process_broadcast_queue
        self.broadcast_queue.put(message)
    
    def send_to_player(self, player_id: int, message: NetworkMessage):
        """إرسال رسالة إلى لاعب محدد"""
        if player_id not in self.players:
            return
        
        player = self.players[player_id]
        message.target_id = player_id
        self.outgoing_queue.put((message, player.address))
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات الخادم"""
        player_stats = []
        for player in self.players.values():
            player_stats.append({
                'player_id': player.player_id,
                'username': player.username,
                'address': f"{player.address[0]}:{player.address[1]}",
                'ping': player.ping,
                'state': player.state.name,
                'connection_time': time.time() - player.last_heartbeat
            })
        
        channel_stats = {}
        for channel_id, channel in self.channels.items():
            channel_stats[f'channel_{channel_id}'] = channel.get_statistics()
        
        return {
            **self.stats,
            'uptime': time.time() - self.start_time,
            'players': player_stats,
            'channels': channel_stats,
            'queues': {
                'incoming': self.incoming_queue.qsize(),
                'outgoing': self.outgoing_queue.qsize(),
                'broadcast': self.broadcast_queue.qsize()
            }
        }

# ============================================================================
# Network System
# ============================================================================

class NetworkSystem:
    """نظام الشبكة"""
    
    def __init__(self, engine, role: NetworkRole = NetworkRole.CLIENT):
        self.engine = engine
        self.role = role
        self.client = None
        self.server = None
        
        # حالات الكيانات
        self.network_entities: Dict[int, NetworkEntity] = {}
        self.local_to_network: Dict[int, int] = {}  # محلي -> شبكة
        self.network_to_local: Dict[int, int] = {}  # شبكة -> محلي
        
        # المزامنة
        self.sync_rate = 0.033  # 30 مرة في الثانية
        self.last_sync_time = 0
        self.interpolation_buffer = defaultdict(deque)
        
        # الإحصائيات
        self.stats = {
            'entities_synced': 0,
            'updates_sent': 0,
            'updates_received': 0,
            'bandwidth_in': 0,
            'bandwidth_out': 0
        }
        
        # التسجيلات
        self._register_event_handlers()
    
    def _register_event_handlers(self):
        """تسجيل معالجات الأحداث"""
        event_bus = self.engine.event_bus
        
        # أحداث الكيانات
        event_bus.subscribe(EventType.ENTITY_CREATED, self._on_entity_created)
        event_bus.subscribe(EventType.ENTITY_DESTROYED, self._on_entity_destroyed)
        event_bus.subscribe(EventType.COMPONENT_ADDED, self._on_component_changed)
        event_bus.subscribe(EventType.COMPONENT_REMOVED, self._on_component_changed)
    
    def initialize(self, address: str = "127.0.0.1", port: int = 7777, 
                  username: str = "Player") -> bool:
        """تهيئة النظام"""
        if self.role == NetworkRole.CLIENT:
            self.client = NetworkClient(address, port)
            return self.client.connect(username)
        elif self.role == NetworkRole.SERVER:
            self.server = NetworkServer(port)
            return self.server.start()
        
        return False
    
    def update(self, delta_time: float):
        """تحديث النظام"""
        if self.role == NetworkRole.CLIENT and self.client:
            self._update_client(delta_time)
        elif self.role == NetworkRole.SERVER and self.server:
            self._update_server(delta_time)
    
    def _update_client(self, delta_time: float):
        """تحديث العميل"""
        # معالجة الأحداث الواردة
        while True:
            event = self.client.get_event()
            if not event:
                break
            
            self._handle_network_event(event)
        
        # مزامنة الكيانات
        current_time = time.time()
        if current_time - self.last_sync_time >= self.sync_rate:
            self._sync_entities()
            self.last_sync_time = current_time
        
        # تطبيق الاستيفاء
        self._apply_interpolation(delta_time)
    
    def _update_server(self, delta_time: float):
        """تحديث الخادم"""
        # تحديث الخادم يتم في خيوط منفصلة
        # هنا يمكننا معالجة منطق اللعبة الخاص بالخادم
        
        # مزامنة الكيانات
        current_time = time.time()
        if current_time - self.last_sync_time >= self.sync_rate:
            self._broadcast_entity_updates()
            self.last_sync_time = current_time
    
    def _handle_network_event(self, event: Dict[str, Any]):
        """معالجة حدث شبكة"""
        event_type = event['type']
        data = event['data']
        sender = event['sender']
        
        if event_type == MessageType.ENTITY_CREATE:
            self._handle_entity_create(data)
        elif event_type == MessageType.ENTITY_DESTROY:
            self._handle_entity_destroy(data)
        elif event_type == MessageType.ENTITY_UPDATE:
            self._handle_entity_update(data, sender)
        elif event_type == MessageType.WORLD_STATE:
            self._handle_world_state(data)
        elif event_type == MessageType.CHAT_MESSAGE:
            self._handle_chat_message(data)
        elif event_type == MessageType.PLAYER_JOINED:
            self._handle_player_joined(data)
        elif event_type == MessageType.PLAYER_LEFT:
            self._handle_player_left(data)
    
    def _handle_entity_create(self, data: Dict[str, Any]):
        """معالجة إنشاء كيان"""
        network_id = data['network_id']
        owner_id = data['owner_id']
        prefab_name = data['prefab_name']
        position = data['position']
        rotation = data['rotation']
        components = data.get('components', {})
        
        # إنشاء الكيان محلياً
        entity = self.engine.entity_manager.create_entity([prefab_name])
        
        # إضافة مكون التحويل
        from .math import Vector3, Quaternion
        from .components import TransformComponent
        
        transform = TransformComponent()
        transform.position = Vector3(*position)
        transform.rotation = Quaternion(*rotation)
        
        entity.add_component(ComponentType.TRANSFORM, transform)
        
        # إضافة المكونات الأخرى
        for comp_name, comp_data in components.items():
            # سيتم تنفيذ هذا بناءً على نظام المكونات
            pass
        
        # التسجيل
        self.local_to_network[entity.id] = network_id
        self.network_to_local[network_id] = entity.id
        
        # إنشاء كيان شبكة
        network_entity = NetworkEntity(
            entity_id=network_id,
            owner_id=owner_id,
            prefab_name=prefab_name,
            position=position,
            rotation=rotation,
            components=components
        )
        
        self.network_entities[network_id] = network_entity
        self.stats['updates_received'] += 1
    
    def _handle_entity_destroy(self, data: Dict[str, Any]):
        """معالجة تدمير كيان"""
        network_id = data['network_id']
        
        if network_id in self.network_to_local:
            entity_id = self.network_to_local[network_id]
            
            # تدمير الكيان محلياً
            self.engine.entity_manager.destroy_entity(entity_id)
            
            # إزالة من التسجيلات
            del self.local_to_network[entity_id]
            del self.network_to_local[network_id]
        
        if network_id in self.network_entities:
            del self.network_entities[network_id]
    
    def _handle_entity_update(self, data: Dict[str, Any], sender: int):
        """معالجة تحديث كيان"""
        network_id = data['network_id']
        position = data.get('position')
        rotation = data.get('rotation')
        components = data.get('components', {})
        
        if network_id not in self.network_to_local:
            return
        
        entity_id = self.network_to_local[network_id]
        entity = self.engine.entity_manager.get_entity(entity_id)
        
        if not entity:
            return
        
        # تحديث التحويل
        if position and entity.has_component(ComponentType.TRANSFORM):
            transform = entity.get_component(ComponentType.TRANSFORM)
            transform.position.x = position[0]
            transform.position.y = position[1]
            transform.position.z = position[2]
        
        if rotation and entity.has_component(ComponentType.TRANSFORM):
            transform = entity.get_component(ComponentType.TRANSFORM)
            transform.rotation.x = rotation[0]
            transform.rotation.y = rotation[1]
            transform.rotation.z = rotation[2]
            transform.rotation.w = rotation[3]
        
        # تخزين للتطبيق المتأخر (للاستيفاء)
        if position or rotation:
            self.interpolation_buffer[network_id].append({
                'position': position,
                'rotation': rotation,
                'timestamp': time.time()
            })
        
        # الاحتفاظ بآخر 3 تحديثات فقط
        while len(self.interpolation_buffer[network_id]) > 3:
            self.interpolation_buffer[network_id].popleft()
        
        self.stats['updates_received'] += 1
    
    def _handle_world_state(self, data: Dict[str, Any]):
        """معالجة حالة العالم"""
        # تحديث حالة العالم
        # (سيتم تنفيذها بناءً على متطلبات اللعبة)
        pass
    
    def _handle_chat_message(self, data: Dict[str, Any]):
        """معالجة رسالة محادثة"""
        player_id = data['player_id']
        username = data['username']
        text = data['text']
        timestamp = data['timestamp']
        
        print(f"[{time.strftime('%H:%M:%S', time.localtime(timestamp))}] {username}: {text}")
    
    def _handle_player_joined(self, data: Dict[str, Any]):
        """معالجة انضمام لاعب"""
        player_id = data['player_id']
        username = data['username']
        
        print(f"Player {username} joined the game")
    
    def _handle_player_left(self, data: Dict[str, Any]):
        """معالجة مغادرة لاعب"""
        player_id = data['player_id']
        username = data['username']
        reason = data['reason']
        
        print(f"Player {username} left: {reason}")
    
    def _sync_entities(self):
        """مزامنة الكيانات المحلية مع الخادم"""
        if not self.client or self.role != NetworkRole.CLIENT:
            return
        
        # إرسال تحديثات الكيانات المملوكة
        for local_id, network_id in self.local_to_network.items():
            entity = self.engine.entity_manager.get_entity(local_id)
            if not entity:
                continue
            
            # التحقق من ملكية الكيان
            network_entity = self.network_entities.get(network_id)
            if not network_entity or network_entity.owner_id != self.client.player_id:
                continue
            
            # التحقق من وجود تغييرات
            if not network_entity.dirty:
                continue
            
            # إرسال التحديث
            transform = entity.get_component(ComponentType.TRANSFORM)
            if transform:
                position = (transform.position.x, transform.position.y, transform.position.z)
                rotation = (transform.rotation.x, transform.rotation.y, 
                          transform.rotation.z, transform.rotation.w)
                
                update_msg = NetworkMessage(
                    message_id=0,
                    message_type=MessageType.ENTITY_UPDATE,
                    sender_id=self.client.player_id,
                    data={
                        'network_id': network_id,
                        'position': position,
                        'rotation': rotation
                    },
                    reliable=False
                )
                
                self.client._send_message(update_msg)
                network_entity.dirty = False
                self.stats['updates_sent'] += 1
    
    def _broadcast_entity_updates(self):
        """بث تحديثات الكيانات من الخادم"""
        if not self.server or self.role != NetworkRole.SERVER:
            return
        
        # إرسال تحديثات جميع الكيانات
        for network_id, entity in self.network_entities.items():
            if not entity.dirty:
                continue
            
            # بث التحديث لجميع اللاعبين
            update_msg = NetworkMessage(
                message_id=0,
                message_type=MessageType.ENTITY_UPDATE,
                sender_id=0,  # الخادم
                data={
                    'network_id': network_id,
                    'position': entity.position,
                    'rotation': entity.rotation,
                    'components': entity.components
                },
                reliable=False
            )
            
            self.server.broadcast_message(update_msg)
            entity.dirty = False
            self.stats['updates_sent'] += 1
    
    def _apply_interpolation(self, delta_time: float):
        """تطبيق الاستيفاء على الكيانات"""
        current_time = time.time()
        
        for network_id, buffer in self.interpolation_buffer.items():
            if len(buffer) < 2:
                continue
            
            if network_id not in self.network_to_local:
                continue
            
            entity_id = self.network_to_local[network_id]
            entity = self.engine.entity_manager.get_entity(entity_id)
            
            if not entity or not entity.has_component(ComponentType.TRANSFORM):
                continue
            
            transform = entity.get_component(ComponentType.TRANSFORM)
            
            # البحث عن أقرب تحديثين للوقت الحالي
            update1 = None
            update2 = None
            
            for i in range(len(buffer) - 1):
                if buffer[i]['timestamp'] <= current_time <= buffer[i + 1]['timestamp']:
                    update1 = buffer[i]
                    update2 = buffer[i + 1]
                    break
            
            if not update1 or not update2:
                continue
            
            # حساب عامل الاستيفاء
            t = (current_time - update1['timestamp']) / \
                (update2['timestamp'] - update1['timestamp'])
            t = max(0, min(1, t))
            
            # تطبيق الاستيفاء على الموقع
            if update1['position'] and update2['position']:
                pos1 = update1['position']
                pos2 = update2['position']
                
                transform.position.x = pos1[0] + (pos2[0] - pos1[0]) * t
                transform.position.y = pos1[1] + (pos2[1] - pos1[1]) * t
                transform.position.z = pos1[2] + (pos2[2] - pos1[2]) * t
            
            # تطبيق الاستيفاء على الدوران (SLERP للكواتيرنيونات)
            if update1['rotation'] and update2['rotation']:
                rot1 = update1['rotation']
                rot2 = update2['rotation']
                
                # تطبيق SLERP مبسط
                transform.rotation.x = rot1[0] + (rot2[0] - rot1[0]) * t
                transform.rotation.y = rot1[1] + (rot2[1] - rot1[1]) * t
                transform.rotation.z = rot1[2] + (rot2[2] - rot1[2]) * t
                transform.rotation.w = rot1[3] + (rot2[3] - rot1[3]) * t
                
                # تطبيع الكواتيرنيون
                length = math.sqrt(
                    transform.rotation.x ** 2 +
                    transform.rotation.y ** 2 +
                    transform.rotation.z ** 2 +
                    transform.rotation.w ** 2
                )
                
                if length > 0:
                    transform.rotation.x /= length
                    transform.rotation.y /= length
                    transform.rotation.z /= length
                    transform.rotation.w /= length
    
    def _on_entity_created(self, event: Event):
        """معالجة إنشاء كيان"""
        if self.role != NetworkRole.SERVER:
            return
        
        entity_id = event.data['entity_id']
        
        # تعيين معرف شبكة
        network_id = len(self.network_entities) + 1
        
        # الحصول على الكيان
        entity = self.engine.entity_manager.get_entity(entity_id)
        if not entity:
            return
        
        # إنشاء كيان شبكة
        transform = entity.get_component(ComponentType.TRANSFORM)
        position = (0, 0, 0)
        rotation = (0, 0, 0, 1)
        
        if transform:
            position = (transform.position.x, transform.position.y, transform.position.z)
            rotation = (transform.rotation.x, transform.rotation.y,
                       transform.rotation.z, transform.rotation.w)
        
        network_entity = NetworkEntity(
            entity_id=network_id,
            owner_id=0,  # الخادم
            prefab_name=entity.tags[0] if entity.tags else "unknown",
            position=position,
            rotation=rotation
        )
        
        # التسجيل
        self.local_to_network[entity_id] = network_id
        self.network_to_local[network_id] = entity_id
        self.network_entities[network_id] = network_entity
        
        # بث إنشاء الكيان
        create_msg = NetworkMessage(
            message_id=0,
            message_type=MessageType.ENTITY_CREATE,
            sender_id=0,
            data={
                'network_id': network_id,
                'owner_id': 0,
                'prefab_name': network_entity.prefab_name,
                'position': position,
                'rotation': rotation
            },
            reliable=True
        )
        
        self.server.broadcast_message(create_msg)
        self.stats['entities_synced'] += 1
    
    def _on_entity_destroyed(self, event: Event):
        """معالجة تدمير كيان"""
        if self.role != NetworkRole.SERVER:
            return
        
        entity_id = event.data['entity_id']
        
        if entity_id in self.local_to_network:
            network_id = self.local_to_network[entity_id]
            
            # بث تدمير الكيان
            destroy_msg = NetworkMessage(
                message_id=0,
                message_type=MessageType.ENTITY_DESTROY,
                sender_id=0,
                data={'network_id': network_id},
                reliable=True
            )
            
            self.server.broadcast_message(destroy_msg)
            
            # الإزالة من التسجيلات
            del self.local_to_network[entity_id]
            del self.network_to_local[network_id]
            
            if network_id in self.network_entities:
                del self.network_entities[network_id]
    
    def _on_component_changed(self, event: Event):
        """معالجة تغيير مكون"""
        entity_id = event.data['entity_id']
        
        if entity_id in self.local_to_network:
            network_id = self.local_to_network[entity_id]
            
            if network_id in self.network_entities:
                self.network_entities[network_id].dirty = True
    
    def send_chat_message(self, text: str):
        """إرسال رسالة محادثة"""
        if self.role == NetworkRole.CLIENT and self.client:
            self.client.send_chat_message(text)
    
    def send_player_state(self, state_data: Dict[str, Any]):
        """إرسال حالة اللاعب"""
        if self.role == NetworkRole.CLIENT and self.client:
            self.client.send_player_state(state_data)
    
    def send_input_state(self, input_data: Dict[str, Any]):
        """إرسال حالة الإدخال"""
        if self.role == NetworkRole.CLIENT and self.client:
            self.client.send_input_state(input_data)
    
    def shutdown(self):
        """إيقاف النظام"""
        if self.role == NetworkRole.CLIENT and self.client:
            self.client.disconnect()
        elif self.role == NetworkRole.SERVER and self.server:
            self.server.stop()
        
        print("Network system shutdown")
    
    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات النظام"""
        if self.role == NetworkRole.CLIENT and self.client:
            client_stats = self.client.get_statistics()
            return {**self.stats, **client_stats}
        elif self.role == NetworkRole.SERVER and self.server:
            server_stats = self.server.get_statistics()
            return {**self.stats, **server_stats}
        
        return self.stats