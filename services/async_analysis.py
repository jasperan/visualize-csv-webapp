"""
Background analysis runner using threads.

Each analysis task runs in a thread and stores results in an in-memory cache.
The dashboard polls /api/analysis/status to check progress and fetch results.
"""
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisTask:
    name: str
    status: str = 'pending'  # pending | running | done | error
    result: Any = None
    error: str = ''
    started_at: float = 0
    finished_at: float = 0


@dataclass
class AnalysisSession:
    tasks: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


# Global store: session_key -> AnalysisSession
_sessions = {}
_lock = threading.Lock()
_MAX_SESSIONS = 100


def _cleanup_old_sessions():
    """Remove oldest sessions if over limit."""
    if len(_sessions) <= _MAX_SESSIONS:
        return
    sorted_keys = sorted(_sessions.keys(), key=lambda k: _sessions[k].created_at)
    for key in sorted_keys[:len(sorted_keys) - _MAX_SESSIONS]:
        del _sessions[key]


def get_or_create_session(session_key):
    with _lock:
        if session_key not in _sessions:
            _cleanup_old_sessions()
            _sessions[session_key] = AnalysisSession()
        return _sessions[session_key]


def clear_session(session_key):
    with _lock:
        _sessions.pop(session_key, None)


def start_analysis(session_key, task_name, func, *args, **kwargs):
    """Launch a background analysis task. Returns immediately."""
    session = get_or_create_session(session_key)

    # If already running or done, skip
    if task_name in session.tasks:
        existing = session.tasks[task_name]
        if existing.status in ('running', 'done'):
            return existing

    task = AnalysisTask(name=task_name, status='running', started_at=time.time())
    session.tasks[task_name] = task

    def runner():
        try:
            result = func(*args, **kwargs)
            task.result = result
            task.status = 'done'
        except Exception as e:
            task.error = str(e)
            task.status = 'error'
            traceback.print_exc()
        finally:
            task.finished_at = time.time()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return task


def get_task_status(session_key, task_name):
    """Get status of a specific task."""
    session = _sessions.get(session_key)
    if not session:
        return None
    return session.tasks.get(task_name)


def get_all_status(session_key):
    """Get status of all tasks for a session."""
    session = _sessions.get(session_key)
    if not session:
        return {}
    result = {}
    for name, task in session.tasks.items():
        entry = {
            'status': task.status,
            'elapsed': round(task.finished_at - task.started_at, 3) if task.finished_at else None,
        }
        if task.status == 'done':
            entry['result'] = task.result
        elif task.status == 'error':
            entry['error'] = task.error
        result[name] = entry
    return result
