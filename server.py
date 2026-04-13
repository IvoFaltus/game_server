import socket
import threading

from client_handler import handle_client_async
from server_config import load_server_settings
from thread_monitor import monitor_threads
import server_state as state
from json_logger import clear_logs, log_event, write_state_snapshot


def main():
    host, port, password = load_server_settings()
    clear_logs()
    write_state_snapshot("startup")

    threads = []

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    server.settimeout(1)

    threading.Thread(
        target=monitor_threads,
        args=(threads, state.threads_lock),
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

            log_event("SOCKET_ACCEPTED", addr=f"{addr[0]}:{addr[1]}")
            write_state_snapshot("socket_accepted")

            t = threading.Thread(
                target=handle_client_async,
                args=(conn, addr, password),
                daemon=True,
                name=f"Client-{addr}",
            )
            t.start()
            with state.threads_lock:
                threads.append(t)
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.close()


if __name__ == "__main__":
    main()
