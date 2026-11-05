import subprocess
import threading
import time
import random
import string
import sys
import os

SERVER = sys.argv[1]
TOPIC = sys.argv[2]
PASSWORD = "123"
NUM_USERS = int(sys.argv[3])
MESSAGE_INTERVAL = float(sys.argv[4])  # seconds between random messages

def random_message(length=20):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def start_user(i):
    username = f"user{i}"

    subprocess.run([
        sys.executable, "client.py",
        SERVER, "register", username, PASSWORD
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    subprocess.run([
        sys.executable, "client.py",
        SERVER, "subscribe", username, PASSWORD, TOPIC
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    proc = subprocess.Popen(
        [sys.executable, "client.py", SERVER, "start", username, PASSWORD, TOPIC],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1
    )

    print(f"[+] user{i} started")

    try:
        while True:
            msg = random_message()
            proc.stdin.write(msg + "\n")
            proc.stdin.flush()
            time.sleep(MESSAGE_INTERVAL)
    except BrokenPipeError:
        print(f"[-] user{i} disconnected")

def main():
    threads = []

    for i in range(NUM_USERS):
        t = threading.Thread(target=start_user, args=(i,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.05)  # slight staggered

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n Stopping stress test")

if __name__ == "__main__":
    main()
