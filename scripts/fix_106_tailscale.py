import paramiko
import time

def fix_dpkg_106():
    ip = "192.168.35.106"
    password = "1234qwer"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(ip, username="admin", password=password, timeout=10)
        
        # 1. Fix broken dpkg with force-confold so it keeps our config
        cmd = "sudo -S DEBIAN_FRONTEND=noninteractive dpkg --configure -a --force-confold"
        stdin, stdout, stderr = ssh.exec_command(f"echo '{password}' | {cmd}")
        print("DPKG OUT:", stdout.read().decode('utf-8'))
        print("DPKG ERR:", stderr.read().decode('utf-8'))
        
        # 2. Restart and check status
        cmds_fix = [
            "sudo -S systemctl daemon-reload",
            "sudo -S systemctl restart tailscaled",
            "sudo -S systemctl status tailscaled | grep Active",
        ]
        for cmd in cmds_fix:
            full_cmd = f"echo '{password}' | {cmd}"
            stdin, stdout, stderr = ssh.exec_command(full_cmd)
            stdout_str = stdout.read().decode('utf-8').strip()
            print(stdout_str)
            time.sleep(0.5)
            
    except Exception as e:
        print(f"[{ip}] Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    fix_dpkg_106()
