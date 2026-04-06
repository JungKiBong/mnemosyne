import os
import glob

def replace_in_file(filepath, old, new):
    with open(filepath, 'r') as f:
        content = f.read()
    if old in content:
        content = content.replace(old, new)
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Updated {filepath}")

for root, _, files in os.walk('tests/e2e'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            replace_in_file(filepath, "'/api/memory", "'/api/v1/memory")
            replace_in_file(filepath, "\"/api/memory", "\"/api/v1/memory")
            replace_in_file(filepath, "'/api/search", "'/api/v1/search")
            replace_in_file(filepath, "\"/api/search", "\"/api/v1/search")
            replace_in_file(filepath, "'/api/query", "'/api/v1/query")
            replace_in_file(filepath, "\"/api/query", "\"/api/v1/query")
            replace_in_file(filepath, "'/api/ingest", "'/api/v1/ingest")
            replace_in_file(filepath, "\"/api/ingest", "\"/api/v1/ingest")

