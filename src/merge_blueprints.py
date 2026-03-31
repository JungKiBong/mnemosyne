import os
import re

APP_DIR = "/Users/jungkibong/Projects/tmp/mirofish-supermemory/src/app"
API_DIR = os.path.join(APP_DIR, "api")

def read_file(name):
    with open(os.path.join(API_DIR, name), "r") as f:
        return f.read()

def write_file(name, content):
    with open(os.path.join(API_DIR, name), "w") as f:
        f.write(content)

# 1. Merge graphs.py -> graph.py
if os.path.exists(os.path.join(API_DIR, "graphs.py")):
    graph_content = read_file("graph.py")
    graphs_content = read_file("graphs.py")

    graphs_body = re.sub(r'import .*\n', '', graphs_content)
    graphs_body = re.sub(r'from flask import .*\n', '', graphs_body)
    graphs_body = re.sub(r'logger = .*\n', '', graphs_body)
    graphs_body = re.sub(r'graphs_bp = .*\n', '', graphs_body)
    
    graphs_body = graphs_body.replace('@graphs_bp.route', '@graph_bp.route')
    graphs_body = graphs_body.replace("route('',", "route('/graphs',")
    graphs_body = graphs_body.replace("route('/<graph_id>", "route('/graphs/<graph_id>")

    graph_content += "\n\n# --- Merged from graphs.py ---\n" + graphs_body
    write_file("graph.py", graph_content)
    os.remove(os.path.join(API_DIR, "graphs.py"))


# 2. Merge memory components -> memory.py
memory_content = read_file("memory.py")

merges = {
    "memory_scopes.py": "scopes_bp",
    "synaptic.py": "synaptic_bp",
    "memory_audit.py": "audit_bp",
    "permanent_memory.py": "permanent_bp"
}

prefixes = {
    "memory_scopes.py": "/scopes",
    "synaptic.py": "/synaptic",
    "memory_audit.py": "/audit",
    "permanent_memory.py": ""
}

for fname, old_bp in merges.items():
    if not os.path.exists(os.path.join(API_DIR, fname)): continue
    content = read_file(fname)
    prefix = prefixes[fname]
    
    # Simple regex to fix decorator routes: @scopes_bp.route('/something') -> @memory_bp.route('/scopes/something')
    def replace_route(match):
        route_path = match.group(1).strip("'\"")
        
        # If prefix is empty (permanent_memory), just keep the path
        if not prefix:
            new_path = route_path
        else:
            if route_path == "":
                new_path = prefix
            else:
                new_path = prefix + (route_path if route_path.startswith('/') else '/' + route_path)
                
        return f"@memory_bp.route('{new_path}'"
        
    pattern = r'@' + old_bp + r'\.route\((.*?)(?=[,\)])'
    
    body = content
    body = re.sub(pattern, replace_route, body)
    
    # Strip some standard imports and bp declarations
    lines = body.split("\n")
    final_lines = []
    for line in lines:
        if "Blueprint" in line and (old_bp in line or "from flask" in line):
            continue
        final_lines.append(line)
        
    memory_content += f"\n\n# --- Merged from {fname} ---\n"
    memory_content += "\n".join(final_lines)
    os.remove(os.path.join(API_DIR, fname))

write_file("memory.py", memory_content)

# Update __init__.py
init_path = os.path.join(APP_DIR, "__init__.py")
with open(init_path, "r") as f:
    init_content = f.read()

lines = init_content.split("\n")
new_lines = []
skip = False

for line in lines:
    # Skip imports and registers for merged blueprints
    if any(x in line for x in ["from .api.graphs import", "from .api.memory_audit import", "from .api.memory_scopes import", "from .api.synaptic import", "from .api.permanent_memory import"]):
        continue
    if any(x in line for x in ["app.register_blueprint(graphs_bp)", "app.register_blueprint(audit_bp)", "app.register_blueprint(scopes_bp)", "app.register_blueprint(synaptic_bp)", "app.register_blueprint(permanent_bp"]):
        continue
    if "Memory Audit Trail API" in line or "Memory Scopes API" in line or "Synaptic Bridge API" in line or "Permanent Memory" in line or "Graph (Project/Scope) Visibility" in line:
        continue
    new_lines.append(line)

with open(init_path, "w") as f:
    f.write("\n".join(new_lines))

print("Merges completed.")
