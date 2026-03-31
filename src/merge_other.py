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

# Merge config
# tuple: (target_file, target_bp, target_prefix, sources: dict)
# sources: { filename: (old_bp_name, old_prefix) }

merge_jobs = [
    ("ingest.py", "ingest_bp", "/api/ingest", {
        "pipeline.py": ("pipeline_bp", "/pipeline"),
        "gateway.py": ("gateway_bp", "/gateway")
    }),
    ("analytics.py", "analytics_bp", "/api/analytics", {
        "maturity.py": ("maturity_bp", "/maturity"),
        "reconciliation.py": ("reconciliation_bp", "/reconcile"),
        "report.py": ("report_bp", "/report"),
        "data_product.py": ("data_product_bp", "/data-product")
    }),
    ("admin.py", "admin_bp", "/api/admin", {
        "security.py": ("security_bp", "/security"),
        "settings.py": ("settings_bp", "/settings"),
        "tools.py": ("tools_bp", "/tools")
    })
]

# Write headers for new blueprints
analytics_init = """import logging
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger('mirofish.api.analytics')
analytics_bp = Blueprint('analytics', __name__)
"""
write_file("analytics.py", analytics_init)

admin_init = """import logging
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger('mirofish.api.admin')
admin_bp = Blueprint('admin', __name__)
"""
write_file("admin.py", admin_init)

for target_file, target_bp, target_prefix, sources in merge_jobs:
    target_content = read_file(target_file)
    
    for fname, (old_bp, old_prefix) in sources.items():
        if not os.path.exists(os.path.join(API_DIR, fname)):
            print(f"Skip {fname}")
            continue
            
        content = read_file(fname)
        
        # Replace routes
        def replace_route(match):
            route_path = match.group(1).strip("'\"")
            
            # If the old blueprint was mounted at old_prefix, 
            # and the target is e.g. /api/analytics, the new route in the bp is old_prefix + route_path
            # Example: pipeline.py has @pipeline_bp.route('/process')
            # The target ingest.py is mounted at /api/ingest
            # So we change to @ingest_bp.route('/pipeline/process')
            
            if route_path == "" or route_path == "/":
                new_path = old_prefix
            else:
                new_path = old_prefix + (route_path if route_path.startswith('/') else '/' + route_path)
            
            return f"@{target_bp}.route('{new_path}'"
            
        pattern = r'@' + old_bp + r'\.route\((.*?)(?=[,\)])'
        body = re.sub(pattern, replace_route, content)
        
        # Skip import and bp declaration lines
        lines = body.split("\n")
        final_lines = []
        for line in lines:
            if "Blueprint" in line and (old_bp in line or "from flask" in line):
                continue
            if line.startswith("import logging") or "logger = logging.getLogger" in line:
                continue
            final_lines.append(line)
            
        target_content += f"\n\n# --- Merged from {fname} ---\n"
        target_content += "\n".join(final_lines)
        os.remove(os.path.join(API_DIR, fname))

    write_file(target_file, target_content)

# Update __init__.py again
init_path = os.path.join(APP_DIR, "__init__.py")
with open(init_path, "r") as f:
    init_content = f.read()

# Replace all old blueprint registrations with the new ones
lines = init_content.split("\n")
new_lines = []

to_skip_imports = [
    "from .api.pipeline import pipeline_bp", 
    "from .api.gateway import gateway_bp",
    "from .api.maturity import maturity_bp",
    "from .api.reconciliation import reconciliation_bp",
    "from .api.report import report_bp",
    "from .api.data_product import data_product_bp",
    "from .api.security import security_bp",
    "from .api.settings import settings_bp",
    "from .api.tools import tools_bp"
]

to_skip_registers = [
    "app.register_blueprint(pipeline_bp)",
    "app.register_blueprint(gateway_bp)",
    "app.register_blueprint(maturity_bp)",
    "app.register_blueprint(reconciliation_bp)",
    "app.register_blueprint(report_bp)",
    "app.register_blueprint(data_product_bp)",
    "app.register_blueprint(security_bp)",
    "app.register_blueprint(settings_bp)",
    "app.register_blueprint(tools_bp)",
    "External Data Gateway",
    "Pipeline API",
    "Maturity API",
    "Reconciliation API",
    "Data Product API",
    "Security API",
    "Settings API",
    "MCP Tools API (Agent-callable tools)",
    "from .api.ingest import ingest_bp",
    "app.register_blueprint(ingest_bp, url_prefix='/api/ingest')"
]

for line in lines:
    skip = False
    for s in to_skip_imports + to_skip_registers:
        if s in line:
            skip = True
            break
    if not skip:
        new_lines.append(line)

# Add new registrations before # Start Memory Scheduler
insert_idx = -1
for i, line in enumerate(new_lines):
    if "Memory Scheduler started" in line or "# Start Memory Scheduler" in line:
        insert_idx = i
        break

if insert_idx != -1:
    new_lines.insert(insert_idx, "    # Ingest API (Ingestion, Pipeline, Gateway)")
    new_lines.insert(insert_idx+1, "    from .api.ingest import ingest_bp")
    new_lines.insert(insert_idx+2, "    app.register_blueprint(ingest_bp, url_prefix='/api/ingest')")
    new_lines.insert(insert_idx+3, "    # Analytics API (Maturity, Reconciliation, Reports, Data Products)")
    new_lines.insert(insert_idx+4, "    from .api.analytics import analytics_bp")
    new_lines.insert(insert_idx+5, "    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')")
    new_lines.insert(insert_idx+6, "    # Admin API (Security, Settings, Tools)")
    new_lines.insert(insert_idx+7, "    from .api.admin import admin_bp")
    new_lines.insert(insert_idx+8, "    app.register_blueprint(admin_bp, url_prefix='/api/admin')\n")

with open(init_path, "w") as f:
    f.write("\n".join(new_lines))

print("Phase 2 merges completed.")
