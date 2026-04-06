import paramiko
import time

nodes = [
    "192.168.35.101",
    "192.168.35.105",
    "192.168.35.106",
    "192.168.35.107",
    "192.168.35.108"
]

password = "1234qwer"
user = "root"

def check_node(ip):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"Connecting to {ip}...")
        client.connect(ip, username=user, password=password, timeout=5)
        stdin, stdout, stderr = client.exec_command('uname -a')
        output = stdout.read().decode('utf-8').strip()
        print(f"[OK] {ip}: {output}")
        client.close()
        return True
    except Exception as e:
        print(f"[FAIL] {ip}: {str(e)}")
        return False

for node in nodes:
    check_node(node)
