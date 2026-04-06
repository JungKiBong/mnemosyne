import paramiko

def check_ray_status():
    ip = "192.168.35.101"
    password = "1234qwer"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(ip, username="admin", password=password, timeout=10)
        
        # Get standard output of docker exec for ray head container
        cmd = "sudo -S docker ps | grep rayproject/ray | awk '{print $1}' | head -n 1"
        stdin, stdout, stderr = ssh.exec_command(f"echo '{password}' | {cmd}")
        container_id = stdout.read().decode('utf-8').strip()
        
        if container_id:
            cmd_status = f"sudo -S docker exec {container_id} ray status"
            stdin, stdout, stderr = ssh.exec_command(f"echo '{password}' | {cmd_status}")
            print(stdout.read().decode('utf-8'))
        else:
            print("Ray head container not found.")
            
    except Exception as e:
        print(f"[{ip}] Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    check_ray_status()
