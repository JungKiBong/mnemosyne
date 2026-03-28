import os
import sys

try:
    from supermemory import Supermemory
    print("Successfully imported Supermemory")
except ImportError as e:
    print(f"Failed to import Supermemory: {e}")
    sys.exit(1)

# Initialize with placeholder or real key from env
api_key = os.environ.get("SUPERMEMORY_API_KEY", "test_key")

try:
    client = Supermemory(api_key=api_key)
    print("Client initialized:", client)
except Exception as e:
    print("Error initializing client:", e)

# Let's inspect the `client`
print("Attributes on client:", dir(client))
