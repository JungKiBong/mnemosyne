import requests
import json

url = "http://100.75.95.45:5678"
email = "admin@n8n.local"
password = "Admin123!"

session = requests.Session()
res = session.post(f"{url}/rest/login", json={"emailOrLdapLoginId": email, "password": password})
if res.status_code == 200:
    print("✅ n8n Login successful")
    
    # Get workflows
    workflows_res = session.get(f"{url}/rest/workflows")
    if workflows_res.status_code == 200:
        workflows = workflows_res.json().get('data', [])
        target_wf = None
        for wf in workflows:
            if wf.get('name') == "Autonomous Laboratory: LTM Promotion Handler":
                target_wf = wf
                break
        
        if target_wf:
            wf_id = target_wf['id']
            # Make sure it's not already active before replacing
            if not target_wf.get('active'):
                target_wf['active'] = True
                update_res = session.put(f"{url}/rest/workflows/{wf_id}", json=target_wf)
                if update_res.status_code == 200:
                    print(f"✅ Workflow '{target_wf['name']}' activated successfully!")
                else:
                    print(f"❌ Failed to activate: {update_res.text}")
            else:
                print("Workflow is already active.")
        else:
            print("Workflow not found.")
else:
    print("❌ Login failed")
