import paramiko
import threading
import time

def setup_wasm_and_stop_ray(ip, password="1234qwer"):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"[{ip}] Connecting...")
        ssh.connect(ip, username="admin", password=password, timeout=10)
        
        cmds = [
            # 1. Stop and disable native Ray service
            "sudo -S systemctl stop ray",
            "sudo -S systemctl disable ray",
            
            # 2. Install Wasmtime
            "curl https://wasmtime.dev/install.sh -sSf | bash",
            
            # 3. Add to path for all users
            "sudo -S bash -c 'echo \"export PATH=\\\"/home/admin/.wasmtime/bin:$PATH\\\"\" > /etc/profile.d/wasmtime.sh'",
        ]
        
        for cmd in cmds:
            full_cmd = f"echo '{password}' | {cmd}"
            ssh.exec_command(full_cmd)
            time.sleep(0.5)
            
        print(f"[{ip}] Native Ray stopped. Wasmtime installed.")
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
        t = threading.Thread(target=setup_wasm_and_stop_ray, args=(ip,))
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
