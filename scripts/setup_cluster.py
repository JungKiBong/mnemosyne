import paramiko
import sys
import time
import socket

def run_sudo_cmd(ssh_client, cmd, password, print_out=True):
    if print_out:
        print(f"Running: {cmd[:80]}...")
    cmd_escaped = cmd.replace("'", "'\\''")
    full_cmd = f"echo '{password}' | sudo -S bash -c '{cmd_escaped}'"
    stdin, stdout, stderr = ssh_client.exec_command(full_cmd)
    
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    
    if print_out and out:
        sys.stdout.write(out)
    if print_out and err:
        sys.stdout.write(err)
        
    return stdout.channel.recv_exit_status(), out, err

def setup_node(ip, is_server, password="1234qwer"):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(ip, username="admin", password=password, timeout=10)
        print(f"\n[{ip}] Connected successfully.")
        
        # 1. Fix netplan IP conflict just in case (if cloned from 101, it might have 101 hardcoded)
        fix_netplan_cmd = f"""
cat <<EOF > /etc/netplan/01-netcfg.yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses: [{ip}/24]
      routes:
        - to: default
          via: 192.168.35.1
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]
EOF
netplan apply
"""
        run_sudo_cmd(ssh, fix_netplan_cmd, password, print_out=False)

        # 2. Configure Nomad
        server_hcl = """
data_dir  = "/opt/nomad/data"
bind_addr = "0.0.0.0"
server {
  enabled          = true
  bootstrap_expect = 1
}
client {
  enabled = true
}
"""
        client_hcl = """
data_dir  = "/opt/nomad/data"
bind_addr = "0.0.0.0"
client {
  enabled = true
  servers = ["192.168.35.101"]
}
"""
        tgt_hcl = server_hcl if is_server else client_hcl
        
        run_sudo_cmd(ssh, f"echo '{tgt_hcl}' > /etc/nomad.d/nomad.hcl", password, print_out=False)
        run_sudo_cmd(ssh, "systemctl enable nomad && systemctl restart nomad", password)

        # 3. Configure Ray
        # Stop existing ray
        run_sudo_cmd(ssh, "ray stop -f || true", password, print_out=False)
        
        if is_server:
            cmd = "ray start --head --port=6379 --dashboard-host=0.0.0.0 --disable-usage-stats"
        else:
            cmd = "ray start --address='192.168.35.101:6379' --disable-usage-stats"

        # Start ray as admin (not root) to avoid permissions issues, but docker needs socket setup...
        # We can just start it safely with normal user:
        stdin, stdout, stderr = ssh.exec_command(f"{cmd}")
        print(stdout.read().decode('utf-8'))
        
        print(f"[{ip}] Configured and started services.")
        
    except Exception as e:
        print(f"[{ip}] FAILED: {str(e)}")
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
    
    for ip in nodes:
        is_server = (ip == "192.168.35.101")
        setup_node(ip, is_server=is_server)

if __name__ == "__main__":
    main()
