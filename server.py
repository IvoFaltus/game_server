import socket
import sys
import re
import json
import argparse
from api import get_question_and_answers
import threading
import random
from colorama import Fore, Style
import time
IP_PATTERN = r"^((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$"
PORT_PATTERN = r"^(6553[0-5]|655[0-2]\d|65[0-4]\d{2}|6[0-4]\d{3}|[1-5]?\d{1,4})$"


def getConfig(atr):
    data = None
    try:
        with open("config.json") as f:
            data = json.load(f)
            return data[atr]
    except Exception as e:
        print(e)
        return data.get(atr) if data and atr in data else None


# ---------------- ARGPARSE ----------------
parser = argparse.ArgumentParser(description="Socket server")
parser.add_argument("-H", "--host", help="Server IP address")
parser.add_argument("-P", "--port", help="Server port")
parser.add_argument("-passwd", "--password", help="api password",required=True)

args = parser.parse_args()

# Resolve host/port (CLI > config)
host = args.host if args.host else getConfig("host")
port = args.port if args.port else getConfig("port")
password = args.password 
if not host or not port:
    sys.exit("Host and port must be provided via args or config.json")

# Validate
if not re.fullmatch(IP_PATTERN, host):
    sys.exit("Invalid IP address")

if not re.fullmatch(PORT_PATTERN, str(port)):
    sys.exit("Invalid port")

port = int(port)

#-------------- thread monitor function----------
def monitor_threads():
    while True:
        time.sleep(5)

        with threads_lock:
            # clean dead threads
            alive = [t for t in threads if t.is_alive()]
            threads[:] = alive

            count = len(threads)

        with open("threads.log", "w") as f:
            f.write(f"{time.time()} Active threads: {count}\n")
# ------------- function for client's thread-----------

print_lock = threading.Lock()

def handle_client_async(conn, addr):
    
    
    colors = [
        Fore.RED, Fore.GREEN, Fore.YELLOW,
        Fore.BLUE, Fore.MAGENTA, Fore.CYAN
    ]
    color = random.choice(colors)

    def cprint(msg):
        with print_lock:
            print(f"{color}[{addr}] {msg}{Style.RESET_ALL}")

    # reset state per client
    asked = False
    a1 = a2 = a3 = q = None

    conn.sendall(
        b"\n[CONNECTED]\nType q:<topic> to get a question\n\n> "
    )

    buffer = b""

    while True:
        data = conn.recv(1024)

        if not data:
            cprint("Client disconnected")
            break

        buffer += data

        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line = line.strip(b"\r")

            if not line:
                continue

            received = line.decode()
            cprint(f"Received: {received}")

            if received.startswith("q:"):
                if asked:
                    conn.sendall(b"\n[ERROR] Question already active\n\n> ")
                    continue

                asked = True
                try:
                    obj = get_question_and_answers(received[2:], password)
                    a1 = obj["1"]
                    a2 = obj["2"]
                    a3 = obj["3"]
                    q = obj["msg"]
                    cprint(f"Generated question: {q}")
                except Exception as e:
                    cprint(f"API error: {e}")
                    asked = False
                    conn.sendall(b"\n[ERROR] Internal server error\n\n> ")
                    continue

                response = (
                    "\n"
                    "===== QUESTION =====\n"
                    f"{q}\n\n"
                    "----- OPTIONS -----\n"
                    f"1) {a1}\n"
                    f"2) {a2}\n"
                    f"3) {a3}\n"
                    "-------------------\n"
                    "Answer using: a:<your_answer>\n"
                    "\n> "
                )

                conn.sendall(response.encode())

            elif received.startswith("a:"):
                if not asked:
                    conn.sendall(b"\n[ERROR] No question yet\n\n> ")
                    continue

                if received[2:] == a3:
                    conn.sendall(b"\n[RESULT] Correct answer\n\n> ")
                    cprint("Client answered correctly")
                    asked = False
                else:
                    conn.sendall(b"\n[RESULT] Wrong answer\n\n> ")
                    cprint("Client answered incorrectly")

    conn.close()
    




# ---------------- SERVER ----------------
threads = []
threads_lock = threading.Lock()
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((host, port))
server.listen()
server.settimeout(1)
threading.Thread(target=monitor_threads, daemon=True).start()
print(f"Listening on {host}:{port}")

print("Waiting for connection...")
try:
    while True:
        try:
            conn, addr = server.accept()
        except socket.timeout:
            continue  # loop again, allows Ctrl+C to be caught

        t=threading.Thread(
            target=handle_client_async,
            args=(conn, addr),
            daemon=True,
            name=f"Client-{addr}"
        )
        t.start()
        with threads_lock:
            threads.append(t)
except KeyboardInterrupt:
    print("\nShutting down server...")
finally:
    server.close()


    




if __name__ == "__main__":
    pass