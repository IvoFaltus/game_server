import random
import threading
import json

from colorama import Fore, Style
from development_translator import translate

from api import get_question_and_answers
from unityapi import (
    receive_msg,
    register_player,
    set_api_password,
    register_connection,
    unregister_connection,
    handle_client_disconnect,
)
from json_logger import log_event, write_state_snapshot

print_lock = threading.Lock()


def _make_cprint(addr):
    colors = [
        Fore.RED,
        Fore.GREEN,
        Fore.YELLOW,
        Fore.BLUE,
        Fore.MAGENTA,
        Fore.CYAN,
    ]
    color = random.choice(colors)

    def cprint(msg):
        with print_lock:
            print(f"{color}[{addr}] {msg}{Style.RESET_ALL}")

    return cprint

def _send_welcome(conn):
    conn.sendall(
        b"\n[CONNECTED]\n"
        b"Commands:\n"
        b"  host <lobby_name> <you_name> <max_players 1-20> <max_score 1-999> -> create lobby\n"
        b"  join <lobby_name> <your_name>  -> join lobby\n"
        b"  startpregame        -> host starts pregame (requires full lobby)\n"
        b"  start               -> in pregame: generate (maxScore+10) questions + start game\n"
        b"  addtopic <topic>    -> add topic in pregame (0-3 per player)\n"
        b"  answer <1|2|3|4|5>  -> answer question (5 is correct)\n"
        b"  solo                -> play alone\n"
        b"\n> "
    )

def _read_lines(buffer, data):
    buffer += data
    lines = []

    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)
        line = line.strip(b"\r")
        if line:
            lines.append(line)

    return buffer, lines


def _get_player_id(addr):
    return f"{addr[0]}:{addr[1]}"


def _handle_unity_message(raw_msg, player_id, conn, cprint):
    translated = translate(raw_msg)
    if not translated:
        return

    cprint(f"Translated: {translated}")
    response = receive_msg(translated, player_id)
    if response is not None:
        conn.sendall((json.dumps(response, ensure_ascii=False) + "\n> ").encode("utf-8"))


def _build_question_response(question, a1, a2, a3):
    return (
        "\n"
        "===== QUESTION =====\n"
        f"{question}\n\n"
        "----- OPTIONS -----\n"
        f"1) {a1}\n"
        f"2) {a2}\n"
        f"3) {a3}\n"
        "-------------------\n"
        "Answer using: a:<your_answer>\n"
        "\n> "
    )


def _handle_question(topic, conn, password, state, cprint):
    if state["asked"]:
        conn.sendall(b"\n[ERROR] Question already active\n\n> ")
        return

    state["asked"] = True
    try:
        obj = get_question_and_answers(topic, password)
        state["a1"] = obj["1"]
        state["a2"] = obj["2"]
        state["a3"] = obj["3"]
        state["q"] = obj["msg"]
        cprint(f"Generated question: {state['q']}")
    except Exception as e:
        cprint(f"API error: {e}")
        state["asked"] = False
        conn.sendall(b"\n[ERROR] Internal server error\n\n> ")
        return

    response = _build_question_response(
        state["q"], state["a1"], state["a2"], state["a3"]
    )
    conn.sendall(response.encode())


def _handle_answer(answer, conn, state, cprint):
    if not state["asked"]:
        conn.sendall(b"\n[ERROR] No question yet\n\n> ")
        return

    if answer == state["a3"]:
        conn.sendall(b"\n[RESULT] Correct answer\n\n> ")
        cprint("Client answered correctly")
        state["asked"] = False
    else:
        conn.sendall(b"\n[RESULT] Wrong answer\n\n> ")
        cprint("Client answered incorrectly")


def handle_client_async(conn, addr, password):
    cprint = _make_cprint(addr)


    state = "notconnected"
    player = {}


    player_id = _get_player_id(addr)
    log_event("CLIENT_CONNECTED", playerid=player_id, addr=f"{addr[0]}:{addr[1]}")
    register_player(player_id, addr)
    register_connection(player_id, conn)
    set_api_password(password)
    write_state_snapshot("client_connected")

    _send_welcome(conn)

    buffer = b""

    try:
        while True:
            data = conn.recv(1024)

            if not data:
                cprint("Client disconnected")
                log_event("CLIENT_DISCONNECTED", playerid=player_id, addr=f"{addr[0]}:{addr[1]}")
                write_state_snapshot("client_disconnected")
                handle_client_disconnect(player_id, reason="DISCONNECT")
                break

            buffer, lines = _read_lines(buffer, data)

            for line in lines:
                received = line.decode()
                cprint(f"Received: {received}")

                _handle_unity_message(received, player_id, conn, cprint)
    finally:
        handle_client_disconnect(player_id, reason="DISCONNECT")
        unregister_connection(player_id)
        try:
            conn.close()
        except Exception:
            pass
