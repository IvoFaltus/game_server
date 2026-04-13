import json

def translate(msg):
    parts = msg.strip().split()

    if not parts:
        return None

    cmd = parts[0].lower()

    # HOST lobbyName name maxPlayers maxScore
    if cmd == "host" and len(parts) >= 5:
        try:
            max_players = int(parts[3])
        except Exception:
            print("Invalid max_players, expected number 1-20")
            return None
        try:
            max_score = int(parts[4])
        except Exception:
            print("Invalid max_score, expected number 1-999")
            return None
        return json.dumps({
            "type": "HOST",
            "lobby": parts[1],
            "name": parts[2],
            "maxPlayers": max_players,
            "maxScore": max_score,
        })
    elif cmd == "host" and len(parts) >= 3:
        print("Usage: host <lobby_name> <you_name> <max_players 1-20> <max_score 1-999>")
        return None

    # JOIN lobbyName
    elif cmd == "join" and len(parts) >= 3:
        return json.dumps({
            "type": "JOIN",
            "lobby": parts[1],
            "name":parts[2]
        })

    # TASK_DONE
    elif cmd == "task":
        return json.dumps({
            "type": "TASK_DONE"
        })

    # STARTPREGAME (host only, requires 3/3 players)
    elif cmd == "startpregame":
        return json.dumps({"type": "STARTPREGAME"})

    # START (state-dependent: LOBBY->PREGAMELOBBY, PREGAMELOBBY->INGAME)
    elif cmd == "start":
        return json.dumps({"type": "START"})

    # ADDTOPIC <topic>
    elif cmd == "addtopic" and len(parts) >= 2:
        topic = " ".join(parts[1:]).strip()
        return json.dumps({"type": "ADDTOPIC", "topic": topic})
    elif cmd == "addtopic":
        print("Usage: addtopic <topic>")
        return None

    # ANSWER <1|2|3|4|5>
    elif cmd == "answer" and len(parts) >= 2:
        try:
            ans = int(parts[1].strip())
        except Exception:
            print("Usage: answer <1|2|3|4|5>")
            return None
        return json.dumps({"type": "ANSWER", "answer": ans})
    elif cmd == "answer":
        print("Usage: answer <1|2|3|4|5>")
        return None

    elif cmd =="question":
        return json.dumps({"type":"question"})
    # LEAVE
    elif cmd == "leave":
        return json.dumps({
            "type": "LEAVE"
        })

    else:
        print("Unknown command")
        return None
