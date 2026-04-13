
import server_state as state
import threading
import random
from json_logger import log_event, write_state_snapshot
from api import get_question_and_answers_5


_api_password = None
_connections = {}
_connections_lock = threading.Lock()


def set_api_password(password):
    global _api_password
    _api_password = password


def register_connection(playerid, conn):
    with _connections_lock:
        _connections[playerid] = conn


def unregister_connection(playerid):
    with _connections_lock:
        _connections.pop(playerid, None)

# =========================
# GLOBAL STATE
# =========================

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


# =========================
# API
# =========================

def send_message(playerid, msg):
    try:
        payload = json.dumps(msg, ensure_ascii=False) + "\n> "
    except Exception:
        payload = json.dumps({"type": "ERROR", "reason": "SEND_SERIALIZE_FAILED"}) + "\n> "

    with _connections_lock:
        conn = _connections.get(playerid)

    if conn is None:
        print(f"[SEND to {playerid}] {payload.strip()}")
        return False

    try:
        conn.sendall(payload.encode("utf-8"))
        return True
    except Exception as e:
        print(f"[SEND ERROR to {playerid}] {e}")
        with _connections_lock:
            if _connections.get(playerid) is conn:
                _connections.pop(playerid, None)
        return False


def send_session_broadcast(sessionid, msg):
    for pid, pdata in state.players.items():
        if pdata.get("sessionId") == sessionid:
            send_message(pid, msg)


def create_or_update_user(playerid, username, addr):
    normalized_addr = _normalize_addr(addr)
    created = False
    with state.threads_lock:
        existing = state.users.get(playerid)
        if existing is not None:
            existing["username"] = username
            existing["addr"] = normalized_addr
            user_obj = dict(existing)
        else:
            created = True
            user_obj = {"username": username, "addr": normalized_addr}
            state.users[playerid] = user_obj

    if created:
        log_event("USER_CREATED", playerid=playerid, user=user_obj)
        write_state_snapshot("user_created")
    else:
        log_event("USER_UPDATED", playerid=playerid, user=user_obj)
        write_state_snapshot("user_updated")

    return state.users[playerid]


def create_session(session_name, host_playerid, host_user_obj, max_players, max_score):
    with state.threads_lock:
        if session_name in state.sessions:
            return None
        state.sessions[session_name] = {
            "players": [host_user_obj],
            "host": host_user_obj,
            "host_playerid": host_playerid,
            "scores": {},
            "question":{},
            "topics":[],
            "topics_by_player": {},
            "questions": [],
            "max_players": max_players,
            "max_score": max_score,
            "state": "LOBBY"   # nebo "INGAME"
        }
    log_event("SESSION_CREATED", session=session_name, host=host_user_obj)
    write_state_snapshot("session_created")
    return session_name


def add_user_to_session(session_name, user_obj):
    added = False
    with state.threads_lock:
        session = state.sessions.get(session_name)
        if not session:
            return {"ok": False, "reason": "SESSION_NOT_FOUND"}
        max_players = session.get("max_players", 2)
        if not isinstance(max_players, int):
            max_players = 2
        if user_obj not in session["players"] and len(session["players"]) >= max_players:
            return {
                "ok": False,
                "reason": "SESSION_FULL",
                "count": len(session["players"]),
                "maxPlayers": max_players,
            }
        if user_obj not in session["players"]:
            session["players"].append(user_obj)
            added = True
    if added:
        log_event("SESSION_PLAYER_ADDED", session=session_name, user=user_obj)
        write_state_snapshot("session_player_added")
        with state.threads_lock:
            session = state.sessions.get(session_name) or {}
            count = len(session.get("players", []))
            max_players = session.get("max_players", 2)
        send_session_broadcast(
            session_name,
            {"type": "PLAYER_JOINED", "lobby": session_name, "count": count, "maxPlayers": max_players},
        )
    return {"ok": True, "added": added}
    

def receive_msg(raw_msg, playerid):
    data = parse_msg(raw_msg)
    if not data:
        return {"type": "ERROR", "reason": "INVALID_JSON"}

    msg_type = data.get("type")

    if msg_type == "HOST":
        return handle_host(playerid, data)

    elif msg_type == "JOIN":
        return handle_join(playerid, data)

    elif msg_type == "STARTPREGAME":
        return handle_startpregame(playerid)

    elif msg_type == "START":
        return handle_start(playerid)

    elif msg_type == "ADDTOPIC":
        return handle_addtopic(playerid, data)

    elif msg_type == "ANSWER":
        return handle_answer(playerid, data)

    elif msg_type == "LEAVE":
        handle_client_disconnect(playerid, reason="LEAVE")
        return {"type": "LEAVE_OK"}

    elif msg_type == "TASK_DONE":
        # legacy: treat as choosing answer 5 (correct)
        return handle_answer(playerid, {"answer": 5})

    else:
        print("Unknown message type")
        return {"type": "ERROR", "reason": "UNKNOWN_TYPE"}


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
        return {"type": "JOIN_ERROR", "reason": "MISSING_LOBBY"}
    username = data.get("name")
    if not username:
        return {"type": "JOIN_ERROR", "reason": "MISSING_NAME"}
    username = str(username).strip()
    if not username:
        return {"type": "JOIN_ERROR", "reason": "EMPTY_NAME"}

    player = state.players.get(playerid)
    if not player:
        return {"type": "JOIN_ERROR", "reason": "PLAYER_NOT_REGISTERED"}

    with state.threads_lock:
        if lobby_name not in state.sessions:
            print(f"Session {lobby_name} not found")
            return {"type": "JOIN_ERROR", "reason": "SESSION_NOT_FOUND"}
        session = state.sessions.get(lobby_name) or {}
        # Username must be unique within this session (case-insensitive)
        requested = username.lower()
        for p in session.get("players", []):
            if isinstance(p, dict) and str(p.get("username", "")).strip().lower() == requested:
                return {"type": "JOIN_ERROR", "reason": "USERNAME_TAKEN", "name": username}

    addr = player.get("addr")
    user_obj = create_or_update_user(playerid, username, addr)

    result = add_user_to_session(lobby_name, user_obj)
    if not result.get("ok"):
        log_event("JOIN_DENIED", playerid=playerid, session=lobby_name, result=result)
        write_state_snapshot("join_denied")
        return {"type": "JOIN_ERROR", **{k: v for k, v in result.items() if k != "ok"}}

    current_thread = threading.current_thread()
    current_thread.session = lobby_name
    current_thread.playerobj = user_obj

    state.players[playerid]["sessionId"] = lobby_name
    state.players[playerid]["playerobj"] = user_obj

    with state.threads_lock:
        session = state.sessions.get(lobby_name)
        if session:
            session.setdefault("scores", {})
            session["scores"].setdefault(playerid, 0)
            session.setdefault("player_current_question", {})
            if session.get("state") == "INGAME":
                session["player_current_question"].setdefault(playerid, 1)
            else:
                session["player_current_question"].setdefault(playerid, 0)

    print(f"Player {playerid} joined session {lobby_name}")
    log_event("JOIN_OK", playerid=playerid, session=lobby_name, user=user_obj)
    write_state_snapshot("join_ok")
    with state.threads_lock:
        session = state.sessions.get(lobby_name) or {}
        if session.get("state") == "INGAME":
            qmsg = _build_current_question_message(session, playerid)
            if qmsg is not None:
                send_message(playerid, qmsg)
        return {
            "type": "JOIN_OK",
            "lobby": lobby_name,
            "count": len(session.get("players", [])),
            "maxPlayers": session.get("max_players", 2),
        }


def handle_host(playerid, data):
    session_name = data.get("lobby")
    if not session_name:
        return {"type": "HOST_ERROR", "reason": "MISSING_LOBBY"}
    username = data.get("name")
    if not username:
        return {"type": "HOST_ERROR", "reason": "MISSING_NAME"}
    max_players_raw = (
        data.get("maxPlayers")
        if data.get("maxPlayers") is not None
        else (data.get("max_players") if data.get("max_players") is not None else data.get("limit"))
    )
    if max_players_raw is None:
        return {"type": "HOST_ERROR", "reason": "MISSING_MAX_PLAYERS"}
    try:
        max_players = int(max_players_raw)
    except Exception:
        return {"type": "HOST_ERROR", "reason": "INVALID_MAX_PLAYERS"}
    if max_players < 1 or max_players > 20:
        return {"type": "HOST_ERROR", "reason": "MAX_PLAYERS_OUT_OF_RANGE", "min": 1, "max": 20}

    max_score_raw = (
        data.get("maxScore")
        if data.get("maxScore") is not None
        else (data.get("max_score") if data.get("max_score") is not None else data.get("maxscore"))
    )
    if max_score_raw is None:
        return {"type": "HOST_ERROR", "reason": "MISSING_MAX_SCORE"}
    try:
        max_score = int(max_score_raw)
    except Exception:
        return {"type": "HOST_ERROR", "reason": "INVALID_MAX_SCORE"}
    if max_score < 1 or max_score > 999:
        return {"type": "HOST_ERROR", "reason": "MAX_SCORE_OUT_OF_RANGE", "min": 1, "max": 999}

    player = state.players.get(playerid)
    if not player:
        return {"type": "HOST_ERROR", "reason": "PLAYER_NOT_REGISTERED"}

    with state.threads_lock:
        if session_name in state.sessions:
            print(f"Session {session_name} already exists")
            return {"type": "HOST_ERROR", "reason": "SESSION_ALREADY_EXISTS"}

    addr = player.get("addr")
    user_obj = create_or_update_user(playerid, username, addr)
    created = create_session(session_name, playerid, user_obj, max_players, max_score)
    if created is None:
        print(f"Session {session_name} already exists")
        return {"type": "HOST_ERROR", "reason": "SESSION_ALREADY_EXISTS"}

    current_thread = threading.current_thread()
    current_thread.session = session_name
    current_thread.playerobj = user_obj

    state.players[playerid]["sessionId"] = session_name
    state.players[playerid]["playerobj"] = user_obj

    with state.threads_lock:
        session = state.sessions.get(session_name)
        if session:
            session.setdefault("scores", {})
            session["scores"].setdefault(playerid, 0)
            session.setdefault("player_current_question", {})
            session["player_current_question"].setdefault(playerid, 0)

    print(f"Player {playerid} hosted session {session_name}")
    log_event("HOST_OK", playerid=playerid, session=session_name, user=user_obj)
    write_state_snapshot("host_ok")
    send_session_broadcast(
        session_name,
        {"type": "PLAYER_JOINED", "lobby": session_name, "count": 1, "maxPlayers": max_players},
    )
    return {"type": "HOST_OK", "lobby": session_name, "count": 1, "maxPlayers": max_players, "maxScore": max_score}

def handle_startpregame(playerid):
    player = state.players.get(playerid)
    if not player:
        return {"type": "STARTPREGAME_ERROR", "reason": "PLAYER_NOT_REGISTERED"}

    sessionid = player.get("sessionId")
    if not sessionid:
        return {"type": "STARTPREGAME_ERROR", "reason": "NOT_IN_SESSION"}

    with state.threads_lock:
        session = state.sessions.get(sessionid)
        if not session:
            return {"type": "STARTPREGAME_ERROR", "reason": "SESSION_NOT_FOUND"}
        if session.get("host_playerid") != playerid:
            return {"type": "STARTPREGAME_ERROR", "reason": "ONLY_HOST_CAN_START"}

        max_players = session.get("max_players", 2)
        if not isinstance(max_players, int):
            max_players = 2

        players_count = len(session.get("players", []))
        if players_count < max_players:
            return {
                "type": "STARTPREGAME_ERROR",
                "reason": "SESSION_NOT_FULL",
                "count": players_count,
                "maxPlayers": max_players,
            }

        if session.get("state") != "LOBBY":
            return {"type": "STARTPREGAME_ERROR", "reason": "INVALID_STATE", "state": session.get("state")}

        session["state"] = "PREGAMELOBBY"
        session.setdefault("topics", [])
        session.setdefault("topics_by_player", {})

    log_event("PREGAME_STARTED", playerid=playerid, session=sessionid)
    write_state_snapshot("pregame_started")
    return {"type": "STARTPREGAME_OK", "lobby": sessionid, "state": "PREGAMELOBBY"}


def handle_addtopic(playerid, data):
    topic = data.get("topic")
    if not isinstance(topic, str):
        return {"type": "ADDTOPIC_ERROR", "reason": "MISSING_TOPIC"}
    topic = topic.strip()
    if not topic:
        return {"type": "ADDTOPIC_ERROR", "reason": "EMPTY_TOPIC"}

    player = state.players.get(playerid)
    if not player:
        return {"type": "ADDTOPIC_ERROR", "reason": "PLAYER_NOT_REGISTERED"}

    sessionid = player.get("sessionId")
    if not sessionid:
        return {"type": "ADDTOPIC_ERROR", "reason": "NOT_IN_SESSION"}

    with state.threads_lock:
        session = state.sessions.get(sessionid)
        if not session:
            return {"type": "ADDTOPIC_ERROR", "reason": "SESSION_NOT_FOUND"}
        if session.get("state") != "PREGAMELOBBY":
            return {"type": "ADDTOPIC_ERROR", "reason": "INVALID_STATE", "state": session.get("state")}

        topics = session.setdefault("topics", [])
        topics_by_player = session.setdefault("topics_by_player", {})
        per_player = topics_by_player.setdefault(playerid, [])
        if len(per_player) >= 3:
            return {"type": "ADDTOPIC_ERROR", "reason": "TOPIC_LIMIT_REACHED", "limit": 3}

        # Don't count duplicates for the same player
        if topic in per_player:
            return {"type": "ADDTOPIC_OK", "topic": topic, "alreadyAdded": True, "count": len(topics)}

        per_player.append(topic)
        if topic not in topics:
            topics.append(topic)

        total = len(topics)

    log_event("TOPIC_ADDED", playerid=playerid, session=sessionid, topic=topic)
    write_state_snapshot("topic_added")
    with state.threads_lock:
        session = state.sessions.get(sessionid) or {}
        topics_count = len(session.get("topics", []))
        user = state.users.get(playerid) or {}
        username = user.get("username") if isinstance(user, dict) else None
    send_session_broadcast(
        sessionid,
        {"type": "TOPIC_ADDED", "lobby": sessionid, "topic": topic, "by": username, "count": topics_count},
    )
    return {"type": "ADDTOPIC_OK", "topic": topic, "count": total}


def handle_start(playerid):
    player = state.players.get(playerid)
    if not player:
        return {"type": "START_ERROR", "reason": "PLAYER_NOT_REGISTERED"}

    sessionid = player.get("sessionId")
    if not sessionid:
        return {"type": "START_ERROR", "reason": "NOT_IN_SESSION"}

    with state.threads_lock:
        session = state.sessions.get(sessionid)
        if not session:
            return {"type": "START_ERROR", "reason": "SESSION_NOT_FOUND"}
        current_state = session.get("state")

    if str(current_state).upper() == "LOBBY":
        return handle_startpregame(playerid)
    if str(current_state).upper() == "PREGAMELOBBY":
        return handle_start_ingame(playerid, sessionid)

    return {"type": "START_ERROR", "reason": "INVALID_STATE", "state": current_state}


def handle_start_ingame(playerid, sessionid):
    if _api_password is None:
        return {"type": "START_ERROR", "reason": "MISSING_API_PASSWORD"}

    with state.threads_lock:
        session = state.sessions.get(sessionid)
        if not session:
            return {"type": "START_ERROR", "reason": "SESSION_NOT_FOUND"}
        if session.get("host_playerid") != playerid:
            return {"type": "START_ERROR", "reason": "ONLY_HOST_CAN_START"}

        max_players = session.get("max_players", 2)
        if not isinstance(max_players, int):
            max_players = 2
        players_count = len(session.get("players", []))
        if players_count < max_players:
            return {
                "type": "START_ERROR",
                "reason": "SESSION_NOT_FULL",
                "count": players_count,
                "maxPlayers": max_players,
            }

        if str(session.get("state")).upper() != "PREGAMELOBBY":
            return {"type": "START_ERROR", "reason": "INVALID_STATE", "state": session.get("state")}

        topics = list(session.get("topics", []))
        if len(topics) < 1:
            return {"type": "START_ERROR", "reason": "NO_TOPICS"}

        max_score = session.get("max_score", 10)
        if not isinstance(max_score, int) or max_score < 1:
            max_score = 10
        questions_to_generate = max_score + 10

        # Mark as generating so clients can't add topics mid-generation
        session["state"] = "GENERATING"

    questions = []
    try:
        for i in range(questions_to_generate):
            chosen_topic = random.choice(topics)
            obj = get_question_and_answers_5(chosen_topic, _api_password)
            questions.append(
                {
                    "number": i + 1,
                    "topic": chosen_topic,
                    "msg": obj.get("msg"),
                    "1": obj.get("1"),
                    "2": obj.get("2"),
                    "3": obj.get("3"),
                    "4": obj.get("4"),
                    "5": obj.get("5"),
                }
            )
    except Exception as e:
        with state.threads_lock:
            session = state.sessions.get(sessionid)
            if session and str(session.get("state")).upper() == "GENERATING":
                session["state"] = "PREGAMELOBBY"
        log_event("INGAME_START_FAILED", playerid=playerid, session=sessionid, error=str(e))
        write_state_snapshot("ingame_start_failed")
        return {"type": "START_ERROR", "reason": "API_ERROR", "error": str(e), "generated": len(questions)}

    with state.threads_lock:
        session = state.sessions.get(sessionid)
        if not session:
            return {"type": "START_ERROR", "reason": "SESSION_NOT_FOUND"}
        # If something changed, don't overwrite
        if session.get("host_playerid") != playerid:
            session["state"] = "PREGAMELOBBY"
            return {"type": "START_ERROR", "reason": "ONLY_HOST_CAN_START"}

        session["questions"] = questions
        session.setdefault("scores", {})
        session.setdefault("player_current_question", {})
        # init per-player progress (1-based question number)
        for pid, pdata in state.players.items():
            if pdata.get("sessionId") == sessionid:
                session["scores"].setdefault(pid, 0)
                session["player_current_question"][pid] = 1
        session["state"] = "INGAME"
        session["current_question_index"] = 0

    log_event("INGAME_STARTED", playerid=playerid, session=sessionid, questions=questions_to_generate)
    write_state_snapshot("ingame_started")

    with state.threads_lock:
        session = state.sessions.get(sessionid) or {}
        player_ids = [pid for pid, pdata in state.players.items() if pdata.get("sessionId") == sessionid]

    for pid in player_ids:
        qmsg = _build_current_question_message(session, pid)
        if qmsg is not None:
            send_message(pid, qmsg)
    return {"type": "START_OK", "lobby": sessionid, "state": "INGAME", "questions": questions_to_generate}


def handle_answer(playerid, data):
    player = state.players.get(playerid)
    if not player:
        return {"type": "ANSWER_ERROR", "reason": "PLAYER_NOT_REGISTERED"}

    sessionid = player.get("sessionId")
    if not sessionid:
        return {"type": "ANSWER_ERROR", "reason": "NOT_IN_SESSION"}

    answer_raw = data.get("answer")
    if answer_raw is None:
        return {"type": "ANSWER_ERROR", "reason": "MISSING_ANSWER"}
    try:
        answer = int(answer_raw)
    except Exception:
        return {"type": "ANSWER_ERROR", "reason": "INVALID_ANSWER"}
    if answer < 1 or answer > 5:
        return {"type": "ANSWER_ERROR", "reason": "ANSWER_OUT_OF_RANGE", "min": 1, "max": 5}
    correct = (answer == 5)

    winner_payload = None

    with state.threads_lock:
        session = state.sessions.get(sessionid)
        if not session:
            return {"type": "ANSWER_ERROR", "reason": "SESSION_NOT_FOUND"}
        if session.get("state") != "INGAME":
            return {"type": "ANSWER_ERROR", "reason": "INVALID_STATE", "state": session.get("state")}

        session.setdefault("scores", {})
        session.setdefault("player_current_question", {})

        current = session["player_current_question"].get(playerid, 1)
        if not isinstance(current, int) or current < 1:
            current = 1

        total_questions = len(session.get("questions", []))
        if total_questions and current > total_questions:
            return {"type": "ANSWER_ERROR", "reason": "GAME_FINISHED", "current": current, "total": total_questions}

        max_score = session.get("max_score", 10)
        if not isinstance(max_score, int) or max_score < 1:
            max_score = 10

        if correct:
            session["scores"][playerid] = session["scores"].get(playerid, 0) + 1

        # increment progress regardless of correctness
        session["player_current_question"][playerid] = current + 1
        score_now = session["scores"].get(playerid, 0)
        next_q = session["player_current_question"][playerid]

        if correct and score_now >= max_score:
            winner_username = None
            user = state.users.get(playerid)
            if isinstance(user, dict):
                winner_username = user.get("username")
            if not winner_username:
                winner_username = str(playerid)

            winner_payload = {
                "type": "WINNER",
                "lobby": sessionid,
                "playerId": playerid,
                "username": winner_username,
                "score": score_now,
                "maxScore": max_score,
            }

            # stop game + reset round state (keep players in session)
            session["state"] = "LOBBY"
            session["questions"] = []
            session["topics"] = []
            session["topics_by_player"] = {}
            session["current_question_index"] = 0
            for pid, pdata in state.players.items():
                if pdata.get("sessionId") == sessionid:
                    session["scores"][pid] = 0
                    session["player_current_question"][pid] = 0

    log_event(
        "ANSWER_RECORDED",
        playerid=playerid,
        session=sessionid,
        answer=answer,
        correct=correct,
        next_question=next_q,
        score=score_now,
    )
    write_state_snapshot("answer_recorded")

    if winner_payload is not None:
        send_session_broadcast(sessionid, winner_payload)
        return {
            "type": "ANSWER_OK",
            "answer": answer,
            "correct": correct,
            "score": score_now,
            "nextQuestion": next_q,
            "winner": winner_payload,
        }

    with state.threads_lock:
        session = state.sessions.get(sessionid) or {}
        qmsg = _build_current_question_message(session, playerid)
    if qmsg is not None:
        send_message(playerid, qmsg)
    return {
        "type": "ANSWER_OK",
        "answer": answer,
        "correct": correct,
        "score": score_now,
        "nextQuestion": next_q,
    }


def _build_current_question_message(session, playerid):
    try:
        progress = session.get("player_current_question", {}).get(playerid, 1)
        if not isinstance(progress, int) or progress < 1:
            progress = 1

        questions = session.get("questions", [])
        if not isinstance(questions, list) or len(questions) == 0:
            return None

        if progress > len(questions):
            return {"type": "NO_MORE_QUESTIONS", "number": progress, "total": len(questions)}

        q = questions[progress - 1]
        return {
            "type": "QUESTION",
            "number": q.get("number", progress),
            "topic": q.get("topic"),
            "msg": q.get("msg"),
            "answers": {
                "1": q.get("1"),
                "2": q.get("2"),
                "3": q.get("3"),
                "4": q.get("4"),
                "5": q.get("5"),
            },
        }
    except Exception:
        return {"type": "ERROR", "reason": "BUILD_QUESTION_FAILED"}


def handle_client_disconnect(playerid, reason="DISCONNECT"):
    with state.threads_lock:
        player = state.players.get(playerid)
        if not player:
            return
        sessionid = player.get("sessionId")
    if not sessionid:
        return
    terminate_session(sessionid, by_playerid=playerid, reason=reason)


def terminate_session(sessionid, by_playerid=None, reason="PLAYER_LEFT"):
    with state.threads_lock:
        session = state.sessions.get(sessionid)
        if not session:
            return False

        affected = [pid for pid, pdata in state.players.items() if pdata.get("sessionId") == sessionid]

        # delete session
        try:
            del state.sessions[sessionid]
        except Exception:
            state.sessions.pop(sessionid, None)

        # reset all players in this session as "just connected" (still registered, but not in any session)
        for pid in affected:
            pdata = state.players.get(pid)
            if not pdata:
                continue
            pdata["sessionId"] = None
            pdata["playerobj"] = None

    payload = {"type": "SESSION_TERMINATED", "lobby": sessionid, "reason": reason, "by": by_playerid}
    for pid in affected:
        send_message(pid, payload)

    log_event("SESSION_TERMINATED", session=sessionid, by=by_playerid, reason=reason, affected=affected)
    write_state_snapshot("session_terminated")
    return True


def handle_task_done(playerid):
    player = state.players.get(playerid)
    if not player:
        return

    sessionid = player["sessionId"]
    if sessionid is None:
        return

    session = state.sessions.get(sessionid)
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
    if lobby_name not in state.sessions:
        state.sessions[lobby_name] = {
            "players": [],
            "host": None,
            "scores": {},
            "max_score": 10,
            "state": "LOBBY",
        }
    return lobby_name


def reset_session(sessionid):
    session = state.sessions.get(sessionid)
    if not session:
        return

    session["scores"] = {}
    session["players"] = []
    session["state"] = "LOBBY"


# =========================
# PLAYER CONNECT
# =========================

def register_player(playerid, addr=None):
    state.players[playerid] = {
        "sessionId": None,
        "addr": _normalize_addr(addr),
        "playerobj": None
    }
    log_event("PLAYER_REGISTERED", playerid=playerid, addr=_normalize_addr(addr))
    write_state_snapshot("player_registered")
