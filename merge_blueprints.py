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
graph_content = read_file("graph.py")
graphs_content = read_file("graphs.py")

# Extract imports from graphs.py (only those not in graph.py)
# Actually, graph.py already has most things. We can just append the functions.
# Remove imports and blueprint definition
graphs_body = re.sub(r'import .*\n(?:from .*\n)*', '', graphs_content)
graphs_body = re.sub(r'logger = .*\n', '', graphs_body)
graphs_body = re.sub(r'graphs_bp = .*\n', '', graphs_body)
graphs_body = graphs_body.replace('@graphs_bp.route', '@graph_bp.route')
graphs_body = graphs_body.replace("route('',", "route('/graphs',")
graphs_body = graphs_body.replace("route('/", "route('/graphs/")

graph_content += "\n\n# --- Merged from graphs.py ---\n" + graphs_body
write_file("graph.py", graph_content)
os.remove(os.path.join(API_DIR, "graphs.py"))

# 2. Merge memory components -> memory.py
memory_content = read_file("memory.py")

# Define mappings
merges = {
    "memory_scopes.py": "/scopes",
    "synaptic.py": "/synaptic",
    "memory_audit.py": "/audit",
    "permanent_memory.py": "" # registered directly on /api/memory
}

for fname, prefix in merges.items():
    if not os.path.exists(os.path.join(API_DIR, fname)): continue
    content = read_file(fname)
    # Remove imports & bp declaration
    body = content.split("bp = Blueprint")[1]
    body = body.split("\n", 1)[1] # skip the rest of the line
    
    # We also need to keep specific imports if they are unique. Instead of complex regex,
    # let's just append the body and fix decorators.
    if fname == "memory_scopes.py":
        body = body.replace('@scopes_bp', '@memory_bp')
    elif fname == "synaptic.py":
        body = body.replace('@synaptic_bp', '@memory_bp')
    elif fname == "memory_audit.py":
        body = body.replace('@audit_bp', '@memory_bp')
    elif fname == "permanent_memory.py":
        body = body.replace('@permanent_bp', '@memory_bp')
        
    # fix route prefixes
    def replace_route(match):
        route_path = match.group(1)
        if route_path == "''" or route_path == '""':
            new_path = f"'{prefix}'" if prefix else "''"
        else:
            old_str = route_path.strip("'\"")
            new_path = f"'{prefix}{old_str}'"
        return f"@memory_bp.route({new_path}"
        
    body = re.sub(r'@memory_bp\.route\((.*?)(?=[,\)])', replace_route, body)
    
    # Add imports that might be needed
    imports = []
    for line in content.split("\n"):
        if (line.startswith("import ") or line.startswith("from ")) and "Blueprint" not in line and "logging" not in line and "logger =" not in line:
            imports.append(line)
            
    memory_content += f"\n\n# --- Merged from {fname} ---\n"
    memory_content += "\n".join(imports) + "\n" + body
    os.remove(os.path.join(API_DIR, fname))

write_file("memory.py", memory_content)

# Update __init__.py
init_path = os.path.join(APP_DIR, "__init__.py")
with open(init_path, "r") as f:
    init_content = f.read()

# Remove the old blueprint registrations
lines = init_content.split("\n")
new_lines = []
skip = False
for line in lines:
    if "from .api.graphs import graphs_bp" in line or "from .api.memory_audit import audit_bp" in line or "from .api.memory_scopes import scopes_bp" in line or "from .api.synaptic import synaptic_bp" in line or "from .api.permanent_memory import permanent_bp" in line:
        continue
    if "app.register_blueprint(graphs_bp)" in line or "app.register_blueprint(audit_bp)" in line or "app.register_blueprint(scopes_bp)" in line or "app.register_blueprint(synaptic_bp)" in line or "app.register_blueprint(permanent_bp" in line:
        continue
    new_lines.append(line)

with open(init_path, "w") as f:
    f.write("\n".join(new_lines))

print("Merges completed.")
