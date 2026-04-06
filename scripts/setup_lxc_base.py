import paramiko
import sys
import time

def run_sudo_cmd(ssh_client, cmd, password):
    print(f"Running: {cmd[:80]}...")
    cmd_escaped = cmd.replace("'", "'\\''")
    full_cmd = f"echo '{password}' | sudo -S bash -c '{cmd_escaped}'"
    stdin, stdout, stderr = ssh_client.exec_command(full_cmd)
    
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    
    if out:
        sys.stdout.write(out)
    if err:
        sys.stdout.write(err)
        
    return stdout.channel.recv_exit_status()

def main():
    ip = "192.168.35.101"
    opts = {"username": "admin", "password": "1234qwer"}
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("Connecting...")
    
    try:
        ssh.connect(ip, timeout=10, **opts)
        print("Connected!")
        
        cmds = [
            # Install Ray properly and docker python pkg
            "pip3 install -U 'ray[default]' docker paramiko",
        ]
        
        for cmd in cmds:
            st = run_sudo_cmd(ssh, cmd, opts["password"])
            if st != 0:
                print(f"FAILED on command: {cmd}")
                break
                
    finally:
        ssh.close()
        print("Done.")

if __name__ == "__main__":
    main()
