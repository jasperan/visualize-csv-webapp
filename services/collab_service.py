"""
Real-time collaboration service via WebSockets.

Manages rooms, user presence, and shared state broadcasting.
Uses Flask-SocketIO for WebSocket transport with automatic fallback to polling.
"""
import uuid
import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# In-memory room state
_rooms = {}


@dataclass
class Participant:
    sid: str
    name: str
    color: str
    joined_at: float = field(default_factory=time.time)


@dataclass
class Room:
    room_id: str
    created_by: str
    participants: dict = field(default_factory=dict)  # sid -> Participant
    shared_state: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


COLORS = [
    '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6',
    '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1',
]


def create_room(creator_name='Anonymous'):
    """Create a new collaboration room. Returns room_id."""
    room_id = uuid.uuid4().hex[:8]
    _rooms[room_id] = Room(room_id=room_id, created_by=creator_name)
    return room_id


def join_room(room_id, sid, name='Anonymous'):
    """Add a participant to a room."""
    room = _rooms.get(room_id)
    if not room:
        return None

    color = COLORS[len(room.participants) % len(COLORS)]
    participant = Participant(sid=sid, name=name, color=color)
    room.participants[sid] = participant
    return participant


def leave_room(room_id, sid):
    """Remove a participant from a room."""
    room = _rooms.get(room_id)
    if not room:
        return
    room.participants.pop(sid, None)
    # Cleanup empty rooms
    if not room.participants:
        _rooms.pop(room_id, None)


def get_room(room_id):
    """Get room info."""
    return _rooms.get(room_id)


def get_participants(room_id):
    """Get list of participants in a room."""
    room = _rooms.get(room_id)
    if not room:
        return []
    return [
        {'sid': p.sid, 'name': p.name, 'color': p.color}
        for p in room.participants.values()
    ]


def leave_all(sid):
    """Remove a participant from every room they're in.

    Returns the list of room_ids the participant was removed from, so the
    caller can broadcast departures. Iterates a snapshot because leave_room
    may delete rooms that become empty.
    """
    left = []
    for room_id in list(_rooms.keys()):
        room = _rooms.get(room_id)
        if room and sid in room.participants:
            leave_room(room_id, sid)
            left.append(room_id)
    return left


def room_exists(room_id):
    return room_id in _rooms
