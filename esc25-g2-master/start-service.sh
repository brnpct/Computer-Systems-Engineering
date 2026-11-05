#!/usr/bin/env bash
set -e

source ./config.sh

KEY_PATH="esc25keypair.pem"

# Ensure INSTANCE_OUTPUT is echoed even on error
trap 'echo "[!] Script stopped. Last instance output:"; echo "$INSTANCE_OUTPUT"' EXIT

echo "[+] Launching EC2 instance..."
INSTANCE_OUTPUT=$(python3 instance.py launch)

echo "$INSTANCE_OUTPUT"

INSTANCE_IP=$(echo "$INSTANCE_OUTPUT" | grep "Public IP:" | awk '{print $3}')
echo "[+] Instance launched: $INSTANCE_IP"

echo "[+] Waiting for instance..."
sleep 10

echo "[+] Uploading server..."
scp -i "$KEY_PATH" -o StrictHostKeyChecking=no "server_core.py" "ubuntu@$INSTANCE_IP:~/server_core.py"
scp -i "$KEY_PATH" -o StrictHostKeyChecking=no "controller.py" "ubuntu@$INSTANCE_IP:~/controller.py"
scp -i "$KEY_PATH" -o StrictHostKeyChecking=no -r templates "ubuntu@$INSTANCE_IP:~/templates"
scp -i "$KEY_PATH" -o StrictHostKeyChecking=no -r topics "ubuntu@$INSTANCE_IP:~/topics"

# Setup virtual environment and run server
ssh -i "$KEY_PATH" ubuntu@$INSTANCE_IP << EOF
set -e
sudo apt update
sudo apt install -y python3-pip python3-venv

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install pycryptodome flask psutil matplotlib

# Run server in background so SSH doesn't block
python3 controller.py
EOF

# This will always run when the script exits
echo "[+] Instance setup complete. Last instance output:"
echo "$INSTANCE_OUTPUT"
