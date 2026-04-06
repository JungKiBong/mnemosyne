# Mories SDK

Internal Python SDK for interacting with the Mories (MiroFish x Supermemory) engine.

## Installation

```bash
pip install -e .
```

## Basic Usage

```python
from mories import MoriesClient

# Initialize client
client = MoriesClient(base_url="http://localhost:5001", token="YOUR_JWT_TOKEN")

# Verify Health
health = client.health()
print("Health:", health)

# Search Memories
results = client.search("Neo4j vector search configuration")
print(results)
```
