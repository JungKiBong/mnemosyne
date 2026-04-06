import paramiko
import sys
import threading
import time

def fix_tailscale_on_node(ip, password="1234qwer"):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"[{ip}] Connecting...")
        ssh.connect(ip, username="admin", password=password, timeout=10)
        
        cmds = [
            "sudo -S bash -c 'echo \"PORT=\\\"41641\\\"\" > /etc/default/tailscaled'",
            "sudo -S bash -c 'echo \"FLAGS=\\\"--tun=userspace-networking --socks5-server=localhost:1055 --outbound-http-proxy-listen=localhost:1055\\\"\" >> /etc/default/tailscaled'",
            "sudo -S systemctl daemon-reload",
            "sudo -S systemctl restart tailscaled",
        ]
        
        for cmd in cmds:
            full_cmd = f"echo '{password}' | {cmd}"
            ssh.exec_command(full_cmd)
            time.sleep(0.5)
            
        print(f"[{ip}] Tailscale configured for userspace networking and restarted.")
    except Exception as e:
        print(f"[{ip}] Error: {e}")
    finally:
        ssh.close()

def main():
    nodes = [
        "192.168.35.101",
        "192.168.35.105",
        "192.168.35.106",
        "192.168.35.107",
        "192.168.35.108"
    ]
    
    threads = []
    for ip in nodes:
        t = threading.Thread(target=fix_tailscale_on_node, args=(ip,))
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
