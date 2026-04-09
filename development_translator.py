import json

def translate(msg):
    parts = msg.strip().split()

    if not parts:
        return None

    cmd = parts[0].lower()

    # HOST lobbyName
    if cmd == "host" and len(parts) >= 3:
        return json.dumps({
            "type": "HOST",
            "lobby": parts[1],
            "name":parts[2]
        })

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

    # LEAVE
    elif cmd == "leave":
        return json.dumps({
            "type": "LEAVE"
        })

    else:
        print("Unknown command")
        return None
