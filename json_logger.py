import json
import os
import tempfile
import threading
from datetime import datetime, timezone

import server_state as state


_io_lock = threading.Lock()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _logs_dir():
    return os.path.join(os.path.dirname(__file__), "logs")


def _ensure_logs_dir():
    os.makedirs(_logs_dir(), exist_ok=True)


def clear_logs():
    _ensure_logs_dir()
    paths = [
        os.path.join(_logs_dir(), "events.jsonl"),
        os.path.join(_logs_dir(), "state.json"),
        os.path.join(_logs_dir(), "users.json"),
        os.path.join(_logs_dir(), "sessions.json"),
        os.path.join(_logs_dir(), "players.json"),
    ]

    with _io_lock:
        for path in paths:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("")
            except Exception:
                pass


def _normalize_addr(addr):
    if addr is None:
        return None
    if isinstance(addr, str):
        return addr
    try:
        host, port = addr
        return f"{host}:{port}"
    except Exception:
        return str(addr)


def _json_safe(obj):
    if isinstance(obj, tuple):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return repr(obj)
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(x) for x in obj]
    return obj


def log_event(event_type, **payload):
    _ensure_logs_dir()
    event = {
        "ts": _now_iso(),
        "event": event_type,
        "thread": threading.current_thread().name,
        "payload": _json_safe(payload),
    }

    path = os.path.join(_logs_dir(), "events.jsonl")
    line = json.dumps(event, ensure_ascii=False)
    with _io_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def write_state_snapshot(reason=None):
    _ensure_logs_dir()
    with state.threads_lock:
        users = _json_safe(state.users)
        sessions = _json_safe(state.sessions)
        players = _json_safe(
            {
                pid: {
                    "sessionId": pdata.get("sessionId"),
                    "addr": _normalize_addr(pdata.get("addr")),
                    "playerobj": pdata.get("playerobj"),
                }
                for pid, pdata in state.players.items()
            }
        )

    snapshot = {
        "ts": _now_iso(),
        "reason": reason,
        "users": users,
        "sessions": sessions,
        "players": players,
    }

    targets = {
        "state.json": snapshot,
        "users.json": {"ts": snapshot["ts"], "reason": reason, "users": users},
        "sessions.json": {"ts": snapshot["ts"], "reason": reason, "sessions": sessions},
        "players.json": {"ts": snapshot["ts"], "reason": reason, "players": players},
    }

    with _io_lock:
        for filename, data in targets.items():
            target = os.path.join(_logs_dir(), filename)
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    delete=False,
                    dir=_logs_dir(),
                    prefix=filename + ".",
                    suffix=".tmp",
                ) as f:
                    tmp = f.name
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, target)
            finally:
                if tmp and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass
