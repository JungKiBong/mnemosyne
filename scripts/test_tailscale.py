import paramiko
import sys

def main():
    ip = "192.168.35.101"
    opts = {"username": "admin", "password": "1234qwer"}
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, timeout=5, **opts)
    
    cmd = "sudo -S systemctl status tailscaled"
    full_cmd = f"echo '{opts['password']}' | {cmd}"
    stdin, stdout, stderr = ssh.exec_command(full_cmd)
    res = stdout.read().decode('utf-8')
    print(res)
    
    ssh.close()

if __name__ == "__main__":
    main()
