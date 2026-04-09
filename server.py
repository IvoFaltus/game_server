import socket
import threading

from client_handler import handle_client_async
from server_config import load_server_settings
from thread_monitor import monitor_threads


threads_lock = threading.Lock()

sessions={}
#example 
# server.sessions[session_name] ={
    # "players": [user_obj],
    # "host": [user_obj],
    # "scores": [],
    # "max_score":10,
    # "state": "LOBBY"   # nebo "INGAME"
    # } 


users={}


def main():
    host, port, password = load_server_settings()

    threads = []

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    server.settimeout(1)

    threading.Thread(
        target=monitor_threads,
        args=(threads, threads_lock),
        daemon=True,
    ).start()

    print(f"Listening on {host}:{port}")
    print("Waiting for connection...")

    try:
        while True:
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue

            t = threading.Thread(
                target=handle_client_async,
                args=(conn, addr, password),
                daemon=True,
                name=f"Client-{addr}",
            )
            t.start()
            with threads_lock:
                threads.append(t)
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.close()


if __name__ == "__main__":
    main()
