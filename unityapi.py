
import server
import threading

# =========================
# GLOBAL STATE
# =========================

sessions = {}
players = {}   # playerId -> { "sessionId": int or None }


# =========================
# API
# =========================

def send_message(playerid, msg):
    # TODO: implement socket send
    print(f"[SEND to {playerid}] {msg}")


def send_session_broadcast(sessionid, msg):
    for pid, pdata in players.items():
        if pdata.get("sessionId") == sessionid:
            send_message(pid, msg)


def create_user(name, addr):
    with server.threads_lock:
        next_id = (max(server.users.keys()) + 1) if server.users else 1
        user_obj = {str(next_id): {"username": name, "addr": addr}}
        server.users[next_id] = user_obj[str(next_id)]
        return user_obj


def create_session(session_name, host_user_obj):
    with server.threads_lock:
        server.sessions[session_name] = {
            "players": [host_user_obj],
            "host": host_user_obj,
            "scores": {},
            "max_score": 10,
            "state": "LOBBY"   # nebo "INGAME"
        }
    return session_name


def add_user_to_session(session_name, user_obj):
    with server.threads_lock:
        session = server.sessions.get(session_name)
        if not session:
            return False
        session["players"].append(user_obj)
        return True
    

def receive_msg(raw_msg, playerid):
    data = parse_msg(raw_msg)
    if not data:
        return

    msg_type = data.get("type")

    if msg_type == "HOST":
        handle_host(playerid, data)

    elif msg_type == "JOIN":
        handle_join(playerid, data)

    elif msg_type == "TASK_DONE":
        handle_task_done(playerid)

    else:
        print("Unknown message type")


# =========================
# MESSAGE PARSER
# =========================

import json

def parse_msg(raw_msg):
    try:
        return json.loads(raw_msg)
    except:
        print("Invalid JSON")
        return None


# =========================
# HANDLERS
# =========================

def handle_join(playerid, data):
    lobby_name = data.get("lobby")
    if not lobby_name:
        return
    username = data.get("name")
    if not username:
        return

    player = players.get(playerid)
    if not player:
        return

    addr = player.get("addr")
    user_obj = create_user(username, addr)

    if not add_user_to_session(lobby_name, user_obj):
        print(f"Session {lobby_name} not found")
        return

    current_thread = threading.current_thread()
    current_thread.session = lobby_name
    current_thread.playerobj = user_obj

    players[playerid]["sessionId"] = lobby_name
    players[playerid]["playerobj"] = user_obj

    print(f"Player {playerid} joined session {lobby_name}")


def handle_host(playerid, data):
    session_name = data.get("lobby")
    if not session_name:
        return
    username = data.get("name")
    if not username:
        return

    player = players.get(playerid)
    if not player:
        return

    addr = player.get("addr")
    user_obj = create_user(username, addr)
    create_session(session_name, user_obj)

    current_thread = threading.current_thread()
    current_thread.session = session_name
    current_thread.playerobj = user_obj

    players[playerid]["sessionId"] = session_name
    players[playerid]["playerobj"] = user_obj

    print(f"Player {playerid} hosted session {session_name}")


def handle_task_done(playerid):
    player = players.get(playerid)
    if not player:
        return

    sessionid = player["sessionId"]
    if sessionid is None:
        return

    session = server.sessions.get(sessionid)
    if not session:
        return

    # kontrola stavu
    if session["state"] != "INGAME":
        return

    # update score
    scores = session["scores"]
    scores[playerid] = scores.get(playerid, 0) + 1

    # broadcast score
    send_session_broadcast(sessionid, {
        "type": "SCORE",
        "playerId": playerid,
        "score": scores[playerid]
    })

    # win condition
    if scores[playerid] >= 10:
        send_session_broadcast(sessionid, {
            "type": "WINNER",
            "playerId": playerid
        })

        session["state"] = "LOBBY"
        reset_session(sessionid)


# =========================
# SESSION MANAGEMENT
# =========================

def find_or_create_session(lobby_name):
    # jednoduchá verze: lobby_name jako key
    if lobby_name not in server.sessions:
        server.sessions[lobby_name] = {
            "id": lobby_name,
            "players": [],
            "scores": {},
            "state": "LOBBY"
        }
    return lobby_name


def reset_session(sessionid):
    session = server.sessions.get(sessionid)
    if not session:
        return

    session["scores"] = {}
    session["players"] = []
    session["state"] = "LOBBY"


# =========================
# PLAYER CONNECT
# =========================

def register_player(playerid, addr=None):
    players[playerid] = {
        "sessionId": None,
        "addr": addr,
        "playerobj": None
    }
