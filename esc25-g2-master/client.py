import sys
import socket
import json
import threading
import time
import struct
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP

def send_msg(sock, data: bytes):
    sock.sendall(struct.pack(">I", len(data)) + data)

def recv_msg(sock):
    raw_len = sock.recv(4)
    if not raw_len:
        return None
    msg_len = struct.unpack(">I", raw_len)[0]

    data = b""
    while len(data) < msg_len:
        packet = sock.recv(msg_len - len(data))
        if not packet:
            return None
        data += packet
    return data

def aes_encrypt(key, plaintext: bytes):
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return cipher.nonce + tag + ciphertext

def aes_decrypt(key, data: bytes):
    nonce = data[:16]
    tag = data[16:32]
    ciphertext = data[32:]
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

usertoken = None

sock.connect((sys.argv[1],9999))

# receive server public key (plaintext)
server_public_bytes = recv_msg(sock)
server_public_key = RSA.import_key(server_public_bytes)
rsa_cipher = PKCS1_OAEP.new(server_public_key)

# create AES key
aes_key = get_random_bytes(32)

# send to server (RSA encrypted with server public)
encrypted_key = rsa_cipher.encrypt(aes_key)
send_msg(sock, encrypted_key)
# all future communication is handled through AES

if sys.argv[2] == 'register':
        msg = {'c':'register','u':sys.argv[3],'p':sys.argv[4]}
        js = json.dumps(msg).encode()
        encrypted = aes_encrypt(aes_key, js)
        send_msg(sock, encrypted)

        encrypted = recv_msg(sock)
        plaintext = aes_decrypt(aes_key, encrypted)
        inc = json.loads(plaintext.decode())
        print(inc['result'])
        sock.close()
        sys.exit()

elif sys.argv[2] == 'subscribe':
        msg = {'c':'subscribe','u':sys.argv[3],'p':sys.argv[4],'t':sys.argv[5]}
        js = json.dumps(msg).encode()
        encrypted = aes_encrypt(aes_key, js)
        send_msg(sock, encrypted)

        encrypted = recv_msg(sock)
        plaintext = aes_decrypt(aes_key, encrypted)
        inc = json.loads(plaintext.decode())
        print(inc['result'])
        sock.close()
        sys.exit()

elif sys.argv[2] == 'listusers':
        msg = {'c':'listusers'}
        js = json.dumps(msg).encode()
        encrypted = aes_encrypt(aes_key, js)
        send_msg(sock, encrypted)

        encrypted = recv_msg(sock)
        plaintext = aes_decrypt(aes_key, encrypted)
        inc = json.loads(plaintext.decode())
        print(inc['result'])
        sock.close()
        sys.exit()

elif sys.argv[2] == 'listtopics':
        msg = {'c':'listtopics'}
        js = json.dumps(msg).encode()
        encrypted = aes_encrypt(aes_key, js)
        send_msg(sock, encrypted)

        encrypted = recv_msg(sock)
        plaintext = aes_decrypt(aes_key, encrypted)
        inc = json.loads(plaintext.decode())
        print(inc['result'])
        sock.close()
        sys.exit()

elif sys.argv[2] == 'stats':
        msg = {'c':'stats'}
        js = json.dumps(msg).encode()
        encrypted = aes_encrypt(aes_key, js)
        send_msg(sock, encrypted)

        encrypted = recv_msg(sock)
        plaintext = aes_decrypt(aes_key, encrypted)
        inc = json.loads(plaintext.decode())
        print(inc['result'])
        sock.close()
        sys.exit()

if sys.argv[2] != 'start':
        print('invalid command')
        sock.close()
        sys.exit()

msg = {'c':'login','u':sys.argv[3],'p':sys.argv[4],'t':sys.argv[5]}
js = json.dumps(msg).encode()
encrypted = aes_encrypt(aes_key, js)
send_msg(sock, encrypted)

encrypted = recv_msg(sock)
plaintext = aes_decrypt(aes_key, encrypted)
inc = json.loads(plaintext.decode())

if inc['result'] == 'Failure':
        print('invalid login')
        sock.close()
        sys.exit()
else:
        usertoken = inc['result']
        topic = sys.argv[5]

socket_lock = threading.Lock()

cont = True
def stdin_reader():
        global cont
        for line in sys.stdin:
                if str(line.strip()) == "exit":
                        with socket_lock:
                                sock.close()
                        cont = False
                        break
                line = line.strip()

                # this erases the last input line from terminal so it only shows the formatted one
                sys.stdout.write("\033[F")  # moves the cursor up one line
                sys.stdout.write("\033[K")  # clears the line
                sys.stdout.flush()  
                
                msg = {'c':'publish','ut':usertoken,'t':topic,'post':line,'r':None}
                js = json.dumps(msg).encode()
                encrypted = aes_encrypt(aes_key, js)
                with socket_lock:
                        send_msg(sock, encrypted)

                        encrypted = recv_msg(sock)
                plaintext = aes_decrypt(aes_key, encrypted)
                inc = json.loads(plaintext.decode())
                if inc['result'] == 'Failure':
                        print('publish error')


def refresher():
        global cont
        while cont:
                msg = {'c':'refresh','ut':usertoken,'t':topic,'old':False}
                js = json.dumps(msg).encode()
                encrypted = aes_encrypt(aes_key, js)
                with socket_lock:
                        start = time.perf_counter()
                        send_msg(sock, encrypted)

                        encrypted = recv_msg(sock)
                        end = time.perf_counter()
                plaintext = aes_decrypt(aes_key, encrypted)
                inc = json.loads(plaintext.decode())
                if inc['result'] == 'Success' and inc['posts']!=[]:
                        for p in inc['posts']:
                                print(f"{p['metadata']['id']} | {p['author']}: {p['post']}")
                if end - start > 0.5:
                        time.sleep(0.5)
                else:
                        time.sleep(0.1)


reader_tr = threading.Thread(target=stdin_reader)
reader_tr.start()

refresh_tr = threading.Thread(target=refresher)
refresh_tr.start()
