import socket
import json
import struct
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes

class SecureClient:
    def __init__(self, host, port=9999):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))

        # receive server public key (plaintext)
        server_public_bytes = self.recv_msg()
        server_public_key = RSA.import_key(server_public_bytes)
        rsa_cipher = PKCS1_OAEP.new(server_public_key)

        # create AES key
        self.aes_key = get_random_bytes(32)

        # send to server (RSA encrypted with server public)
        encrypted_key = rsa_cipher.encrypt(self.aes_key)
        self.send_msg(encrypted_key)
        # all future communication is handled through AES

    def send_msg(self, data: bytes):
        self.sock.sendall(struct.pack(">I", len(data)) + data)

    def recv_msg(self):
        raw_len = self.sock.recv(4)
        if not raw_len:
            return None
        msg_len = struct.unpack(">I", raw_len)[0]
        data = b""
        while len(data) < msg_len:
            packet = self.sock.recv(msg_len - len(data))
            if not packet:
                return None
            data += packet
        return data

    def aes_encrypt(self, plaintext: bytes):
        cipher = AES.new(self.aes_key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        return cipher.nonce + tag + ciphertext

    def aes_decrypt(self, data: bytes):
        nonce = data[:16]
        tag = data[16:32]
        ciphertext = data[32:]
        cipher = AES.new(self.aes_key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)

    def request(self, payload: dict):
        js = json.dumps(payload).encode()
        encrypted = self.aes_encrypt(js)
        self.send_msg(encrypted)

        encrypted = self.recv_msg()
        plaintext = self.aes_decrypt(encrypted)
        return json.loads(plaintext.decode())

    def close(self):
        self.sock.close()
