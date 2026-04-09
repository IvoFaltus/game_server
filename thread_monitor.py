import time


def monitor_threads(threads, threads_lock):
    while True:
        time.sleep(5)

        with threads_lock:
            alive = [t for t in threads if t.is_alive()]
            threads[:] = alive
            count = len(threads)

        with open("threads.log", "w") as f:
            f.write(f"{time.time()} Active threads: {count}\n")
