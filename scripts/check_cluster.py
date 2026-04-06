import paramiko
import sys

def main():
    ip = "192.168.35.101"
    opts = {"username": "admin", "password": "1234qwer"}
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, timeout=5, **opts)
    
    print("=== Nomad Cluster Status ===")
    stdin, stdout, stderr = ssh.exec_command("nomad node status")
    print(stdout.read().decode('utf-8'))
    
    print("\n=== Ray Cluster Status ===")
    stdin, stdout, stderr = ssh.exec_command("ray status")
    print(stdout.read().decode('utf-8'))
    
    ssh.close()

if __name__ == "__main__":
    main()
