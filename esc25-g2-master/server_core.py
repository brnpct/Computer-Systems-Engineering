import socket, sys, time, threading, json, os, shutil, secrets, struct, psutil
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA

# -------------------------------------
#               DATABASE
# -------------------------------------

# user_database
# {...,"username":{"password":password,"topics":{"topic1":last viewed post ID,"topic2":last viewed post ID}},...}

# topics
# {...,"topic1": {...,post_id:{"post":"abc","author":"name1","metadata":{"id":post_id, 'reply_to': a post_id or None}},...},...}


post_id = 1
user_database = {}
topics = {}
active_tokens = {}

total_time = []
operations = 0

user_lock = threading.Lock()
topic_lock = threading.Lock()
token_lock = threading.Lock()
stats_lock = threading.Lock()

def init_server(mode="fresh"):
    global user_database, topics, post_id

    with user_lock, topic_lock, token_lock, stats_lock:
        post_id = 1
        user_database = {}
        topics = {}
        active_tokens = {}
        total_time = []
        operations = 0

        if mode == "reboot":
            user_database = {}
            with open("users.log") as f:
                for line in f:
                    e = json.loads(line)
                    if e["event"] == "register":
                        user_database[e["user"]] = {
                            "password": e["password"],
                            "topics": {},
                            "metadata": {}
                        }
                    elif e["event"] == "subscribe":
                        user_database[e["user"]]["topics"][e["topic"]] = 0

            topics = {}
            for filename in os.listdir("topics"):
                t = filename.removesuffix(".log")
                topics[t] = {}
                with open(f"topics/{filename}") as f:
                    for line in f:
                        if line.strip():
                            e = json.loads(line)
                            if e["event"] == "post":
                                # json files turn the integer keyed entries into strings, this turns them back to integers
                                i = int(list(e["post"].keys())[0])
                                # updates the current post ID
                                post_id = max(post_id, i + 1)
                                post = {int(k): v for k, v in e["post"].items()}
                                topics[t].update(post)
        else:
            user_database = {}
            if os.path.exists("users.log"):
                    os.remove("users.log")
            open("users.log", "a").close()

            topics = {}
            for filename in os.listdir("topics"):
                t = filename.removesuffix(".log")
                topics[t] = {}
                os.remove(f"topics/{filename}")
                open(f"topics/{filename}","a").close()
            
            if os.path.exists("stats.log"):
                    os.remove("stats.log")
            open("stats.log", "a").close()

# -----------------------------
#            TOKENS
# -----------------------------

def token_from_user(username):
    global active_tokens
    token = secrets.token_hex(16)
    active_tokens[token] = username
    return token

def valid_tokenQ(token):
    return token in active_tokens

def user_from_token(token):
    return active_tokens.get(token)

# -----------------------------
#       MESSAGE PROTOCOL
# -----------------------------

def send_msg(sock, data):
    sock.sendall(struct.pack(">I", len(data)) + data)

def recv_msg(sock):
    raw = sock.recv(4)
    if not raw:
        return None
    size = struct.unpack(">I", raw)[0]
    data = b""
    while len(data) < size:
        packet = sock.recv(size - len(data))
        if not packet:
            return None
        data += packet
    return data

def aes_encrypt(key, data):
    cipher = AES.new(key, AES.MODE_GCM)
    ct, tag = cipher.encrypt_and_digest(data)
    return cipher.nonce + tag + ct

def aes_decrypt(key, data):
    nonce, tag, ct = data[:16], data[16:32], data[32:]
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ct, tag)


server_key = RSA.generate(2048)
server_private = server_key
server_public = server_key.publickey().export_key()

# -----------------------------
#          LOGGING
# -----------------------------

def log_user(event):
    with open("users.log", "a") as f:
        f.write(json.dumps(event) + "\n")

def log_topic_event(topic, event):
    with open(f"topics/{topic}.log", "a") as f:
        f.write(json.dumps(event) + "\n")

# -----------------------------
#        SERVER COMMANDS
# -----------------------------

def register(u,p):
    global user_database
    with user_lock:
        if u not in user_database:
            user_database[u] = {"password": p, "topics": {}, "metadata": {}}
            log_user({"event": "register", "user": u, "password": p})
            return "Success"
        return "Failure"

def login(u, p):
    with user_lock:
        if u not in user_database or user_database[u]["password"] != p:
            return "Failure"
    with token_lock:
        return token_from_user(u)

def subscribe(ut, t):
    global user_database
    global active_tokens
    with token_lock:
        if valid_tokenQ(ut):
            u = user_from_token(ut)
        else:
            return "Failure1"
    with topic_lock:
        if t not in topics:
            return "Failure2"
    with user_lock:
        if u not in user_database:
            return "Failure3"
        user_database[u]["topics"][t] = 0
        log_user({"event": "subscribe", "user": u, "topic": t})
        return "Success"
    

def publish(ut,t,p,reply):
    global post_id
    global topics
    with token_lock:
        if not valid_tokenQ(ut):
            return "Failure"
        user = user_from_token(ut)

    with user_lock:
        if t not in user_database[user]["topics"]:
            return "Failure"

    with topic_lock:
        if t not in topics:
            return "Failure"
        p = {post_id:{"post": p, "author": user, "metadata": {'id':post_id,'reply_to':reply} }}
        post_id += 1
        log_topic_event(t,{"event":"post","post":p})
        topics[t].update(p)
        return "Success"
        
def refresh(ut,t,old):
    with token_lock:
        if not valid_tokenQ(ut):
            return "Failure"
        user = user_from_token(ut)

    with user_lock:
        if t not in user_database[user]["topics"]:
            return "Failure"
        last = user_database[user]["topics"][t]

    with topic_lock:
        if t not in topics:
            return "Failure"
        ids =  sorted(sorted(map(int, topics[t].keys()), reverse=True)[:200])
        if old == True:
            posts = [topics[t][id] for id in ids if id <= last]
        else:
            posts = [topics[t][id] for id in ids if id > last]
    with user_lock:
        if old == False:
            if ids != []:
                user_database[user]["topics"][t] = ids[-1]
    return posts

def listusers():
    with user_lock:
        return  [username for username in user_database]

def listtopics():
    with topic_lock:
        result = []
        for topic in topics:
            post_count = len(topics[topic])
            result.append([topic, post_count])
        return result

def stats():
    with user_lock:
        uc = len(user_database)
    tc = 0
    pc = 0
    with topic_lock:
        for topic in topics:
                tc += 1
                pc += len(topics[topic]) # counting this using post_id would overcount in some cases (e.g. post deletion if implemented)
    with stats_lock:
        lat = (sum(total_time)/min(200,len(total_time)))*1000 # miliseconds
        op = operations
    return [uc,tc,pc,lat,op]

def profile(username):
    with user_lock:
        if username in user_database:
            topics_list = list(user_database[username]["topics"].keys())
            return {'topics': topics_list, 'metadata': user_database[username]['metadata']}
        else:
            return {'topics':[],'metadata':{}}

# -----------------------------
#        CLIENT HANDLER
# -----------------------------

def handle_client(conn):
    global post_id, operations, total_time
    global user_database
    global active_tokens

    # send server public key (plaintext)
    send_msg(conn, server_public)

    # receive and decrypt client AES key (RSA encrypted with server public)
    aes_key = PKCS1_OAEP.new(server_private).decrypt(recv_msg(conn))
    # all future communication is handled through AES

    while True:
        encrypted = recv_msg(conn)
        start = time.perf_counter()

        if not encrypted:
            break

        try:
            inc = json.loads(aes_decrypt(aes_key, encrypted))
        except:
            break

    
        if inc["c"] == "register":
            res = register(inc["u"], inc["p"])
            msg = {"result": res}

        elif inc["c"] == "login":
            res = login(inc["u"], inc["p"])
            msg = {"result": res}
        
        elif inc["c"] == "subscribe":
            # I'm creating a temporary token here (then deleting it) since the project requested that: 
            # -> subscribe() be called with a token server side
            # -> 'subscribe' be called with username+password on client side
            # all of this before a usertoken has been assigned from the 'start' command
            temp_token = login(inc['u'],inc['p'])
            if temp_token != "Failure":
                res = subscribe(temp_token,inc['t'])
                with token_lock:
                    del active_tokens[temp_token]
                msg = {"result":res}
            else:
                msg = {"result":"Failure"}

        elif inc["c"] == "publish":
            res = publish(inc['ut'],inc['t'],inc['post'],inc['r'])
            msg = {"result": res}

        elif inc["c"] == "refresh":
            res = refresh(inc['ut'],inc['t'],inc['old'])
            if res != "Failure":
                msg = {'result':'Success','posts':res}
            else:
                msg = {'result':'Failure'}

        elif inc['c'] == 'listusers':
            msg = {'result':listusers()}

        elif inc['c'] == 'listtopics':
            msg = {'result':listtopics()}

        elif inc['c'] == 'stats':
            msg = {'result':stats()}
        
        elif inc['c'] == 'profile':
            msg = {'result':profile(inc['u'])}

        else:
            msg = {"result":"Failure"}

        encrypted_out = aes_encrypt(aes_key, json.dumps(msg).encode())
        send_msg(conn, encrypted_out)
        with stats_lock:
            operations += 1
            total_time.append(time.perf_counter() - start)
            total_time[:] = total_time[-300:]

    conn.close()


# -----------------------------
# SERVER LOOP
# -----------------------------

def run_server(stop_event,method):
    init_server(method)
    sock = socket.socket()
    sock.bind(("", 9999))
    sock.listen()
    sock.settimeout(1)

    last_stats = time.time()

    while not stop_event.is_set():

        # write stats every 2 seconds
        if time.time() - last_stats >= 2:
            log_stats()
            last_stats = time.time()

        try:
            conn, _ = sock.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
        except socket.timeout:
            continue

    sock.close()

# -----------------------------
# STATS SNAPSHOT
# -----------------------------

def log_stats():

    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    with user_lock,topic_lock,stats_lock:
        st =  {
            "time": time.time(),

            # application stats
            "users": len(user_database),
            "topics": len(topics),
            "posts": sum(len(t) for t in topics.values()),
            "operations": operations,
            "avg_latency_ms": (sum(total_time) / min(len(total_time),300) * 1000) if total_time else 0,

            # system stats
            "cpu_percent": cpu,
            "memory": {
                "total_mb": mem.total // (1024 * 1024),
                "used_mb": mem.used // (1024 * 1024),
                "percent": mem.percent
            },
            "disk": {
                "total_mb": disk.total // (1024 * 1024),
                "used_mb": disk.used // (1024 * 1024),
                "percent": disk.percent
            }
        }

    with open("stats.log", "a") as f:
        f.write(json.dumps(st) + "\n")

