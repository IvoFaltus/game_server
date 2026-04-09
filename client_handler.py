import random
import threading

from colorama import Fore, Style
from development_translator import translate

from api import get_question_and_answers
from unityapi import receive_msg, register_player

import server
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
        b"  host <lobby_name> <you_name>  -> create lobby\n"
        b"  join <lobby_name> <your_name>  -> join lobby\n"
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


def _handle_unity_message(raw_msg, player_id, cprint):
    translated = translate(raw_msg)
    if not translated:
        return

    cprint(f"Translated: {translated}")
    receive_msg(translated, player_id)


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
    state = {"asked": False, "a1": None, "a2": None, "a3": None, "q": None}
    player_id = _get_player_id(addr)
    register_player(player_id, addr)

    _send_welcome(conn)

    buffer = b""

    while True:
        data = conn.recv(1024)

        if not data:
            cprint("Client disconnected")
            break

        buffer, lines = _read_lines(buffer, data)

        for line in lines:
            received = line.decode()
            cprint(f"Received: {received}")

            _handle_unity_message(received, player_id, cprint)

    conn.close()
