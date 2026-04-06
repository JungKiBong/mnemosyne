import paramiko

def cleanup_ray_processes():
    ip = "192.168.35.101"
    password = "1234qwer"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(ip, username="admin", password=password, timeout=10)
        
        # Kill any hanging ray or redis-server processes
        cmd = "sudo -S killall -9 ray gcs_server raylet redis-server"
        stdin, stdout, stderr = ssh.exec_command(f"echo '{password}' | {cmd}")
        print("Killall out:", stdout.read().decode('utf-8'))
        print("Killall err:", stderr.read().decode('utf-8'))
        
    except Exception as e:
        print(f"[{ip}] Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    cleanup_ray_processes()
