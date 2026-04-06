import paramiko
import time

def fix_hostname(ip, new_hostname, password="1234qwer"):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(ip, username="admin", password=password, timeout=10)
        
        cmds = [
            f"sudo -S hostnamectl set-hostname {new_hostname}",
            f"sudo -S bash -c 'sed -i \"s/CT101/{new_hostname}/g\" /etc/hosts'",
            "sudo -S systemctl restart nomad"
        ]
        
        for cmd in cmds:
            full_cmd = f"echo '{password}' | {cmd}"
            ssh.exec_command(full_cmd)
            time.sleep(0.5)
            
        print(f"[{ip}] Hostname changed to {new_hostname} and Nomad restarted.")
    except Exception as e:
        print(f"[{ip}] Error: {e}")
    finally:
        ssh.close()

def main():
    mapping = {
        "192.168.35.105": "CT105",
        "192.168.35.106": "CT106",
        "192.168.35.107": "CT107",
        "192.168.35.108": "CT108"
    }
    
    import threading
    threads = []
    for ip, hostname in mapping.items():
        t = threading.Thread(target=fix_hostname, args=(ip, hostname))
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
