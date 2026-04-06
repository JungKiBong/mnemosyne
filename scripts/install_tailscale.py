import paramiko
import sys
import time
import threading

def install_tailscale_on_node(ip, password="1234qwer"):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"[{ip}] Connecting...")
        ssh.connect(ip, username="admin", password=password, timeout=10)
        
        # Install Tailscale
        print(f"[{ip}] Installing Tailscale...")
        cmd = "curl -fsSL https://tailscale.com/install.sh | sudo sh"
        
        transport = ssh.get_transport()
        session = transport.open_session()
        session.get_pty()
        session.exec_command(f"sudo -S bash -c '{cmd}'")
        session.send(password + '\n')
        
        while not session.exit_status_ready():
            time.sleep(0.5)
            
        print(f"[{ip}] Tailscale installed successfully.")
        
        # We don't run 'tailscale up' here because it blocks and requires interactive browser login.
        # We will inform the user of the command to run.
        
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
        t = threading.Thread(target=install_tailscale_on_node, args=(ip,))
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
