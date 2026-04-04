import requests
import json
import os

url = "http://100.75.95.45:5678"
email = "admin@n8n.local"
password = "Admin123!"

session = requests.Session()
res = session.post(f"{url}/rest/login", json={"emailOrLdapLoginId": email, "password": password})
if res.status_code == 200:
    print("✅ n8n (100.75.95.45) Login successful")
    
    # Read the local workflow file
    file_path = "n8n_workflows/16_autonomous_lab_webhook.json"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            workflow_data = json.load(f)
            
        # Push the workflow to the remote server
        push_res = session.post(f"{url}/rest/workflows", json=workflow_data)
        if push_res.status_code == 200:
            print("✅ 워크플로우를 원격 서버에 성공적으로 생성했습니다!")
            
            # Now let's print the recent executions just in case
            execs = session.get(f"{url}/rest/executions?limit=1")
            data = execs.json()
            if 'data' in data and 'results' in data['data']:
                latest = data['data']['results'][0]
                print(f"📌 최신 실행 기록: {latest.get('workflowName')} (상태: {latest.get('status')})")
        else:
            print(f"❌ 워크플로우 생성 실패: {push_res.status_code} - {push_res.text}")
    else:
        print("Workflow file not found.")
else:
    print("❌ Login failed")
