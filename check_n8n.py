import requests
import json

url = "http://100.75.95.45:5678"
email = "admin@n8n.local"
password = "Admin123!"

try:
    session = requests.Session()
    res = session.post(f"{url}/rest/login", json={"emailOrLdapLoginId": email, "password": password})
    if res.status_code == 200:
        print("✅ n8n (100.75.95.45) Login successful")
        execs = session.get(f"{url}/rest/executions?limit=3")
        if execs.status_code == 200:
            data = execs.json()
            print(f"📌 Raw n8n execution data: {json.dumps(data.get('data', {}), indent=2)[:500]}")
        else:
            print(f"Failed to fetch executions: {execs.status_code}")
    else:
        print(f"❌ Login failed: {res.status_code} - {res.text}")
except Exception as e:
    print(f"Error connecting to n8n: {e}")
