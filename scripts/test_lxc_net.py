import paramiko
import sys
import time

def run_sudo_cmd(ssh_client, cmd, password):
    transport = ssh_client.get_transport()
    session = transport.open_session()
    session.get_pty()
    session.exec_command(f"sudo -S bash -c '{cmd}'")
    session.send(password + '\n')
    while not session.exit_status_ready():
        if session.recv_ready():
            sys.stdout.write(session.recv(4096).decode('utf-8'))
            sys.stdout.flush()
        if session.recv_stderr_ready():
            sys.stdout.write(session.recv_stderr(4096).decode('utf-8'))
            sys.stdout.flush()
        time.sleep(0.1)
    return session.recv_exit_status()

def main():
    ip = "192.168.35.101"
    opts = {"username": "admin", "password": "1234qwer"}
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, timeout=5, **opts)
    
    # Debug hashicorp key and list
    print("--- Hashicorp Repo Debug ---")
    st = run_sudo_cmd(ssh, "ls -la /usr/share/keyrings/hashicorp-archive-keyring.gpg && cat /etc/apt/sources.list.d/hashicorp.list && apt-get update", opts["password"])
    
    print(f"\nExit status: {st}")
    ssh.close()

if __name__ == "__main__":
    main()
