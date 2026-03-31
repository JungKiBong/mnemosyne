import hmac
import hashlib
import json
import time
import requests
import argparse
import sys

def create_signature(secret: str, payload: dict) -> str:
    payload_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    signature = hmac.new(
        secret.encode('utf-8'),
        payload_json,
        hashlib.sha256
    ).hexdigest()
    return signature

def send_webhook(url: str, secret: str, event_type: str):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    if event_type == "memory.promoted":
        payload = {
            "event": "memory.promoted",
            "timestamp": timestamp,
            "payload": {
                "stm_id": "test_stm_12345",
                "ltm_uuid": "ltm_idx_7890",
                "salience": 0.95,
                "scope": "personal"
            }
        }
    elif event_type == "memory.decayed":
        payload = {
            "event": "memory.decayed",
            "timestamp": timestamp,
            "payload": {
                "removed_count": 5,
                "weakened_count": 12,
                "cycle_id": "cycle_888"
            }
        }
    elif event_type == "batch_completed":
         payload = {
             "event": "batch_completed",
             "timestamp": timestamp,
             "payload": {
                 "job_id": "job_001",
                 "status": "completed",
                 "processed": 10
             }
         }
    else:
        print(f"Unknown event type: {event_type}")
        return

    # Calculate exactly like WebhookPublisher does
    payload_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    signature = hmac.new(secret.encode('utf-8'), payload_json, hashlib.sha256).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "X-Mories-Signature": signature
    }

    try:
        print(f"Sending [{event_type}] to {url}...")
        res = requests.post(url, data=payload_json, headers=headers, timeout=5)
        print(f"Response: {res.status_code} {res.text}")
    except Exception as e:
        print(f"Failed to send webhook: {e}", file=sys.stderr)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Mories Webhook Harness")
    parser.add_argument("--url", required=True, help="n8n Webhook URL (e.g. http://localhost:5678/webhook-test/mories-events)")
    parser.add_argument("--secret", default="my-development-secret", help="HMAC Secret Key (default: my-development-secret)")
    parser.add_argument("--event", choices=["memory.promoted", "memory.decayed", "batch_completed", "all"], default="all", help="Event type to send")
    
    args = parser.parse_args()
    
    events_to_send = ["memory.promoted", "memory.decayed", "batch_completed"] if args.event == "all" else [args.event]
    
    for ev in events_to_send:
        send_webhook(args.url, args.secret, ev)
        time.sleep(1)
