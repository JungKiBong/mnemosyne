import os
import re

DASHBOARD_DIR = '/Users/jungkibong/Projects/tmp/mirofish-supermemory/dashboard'
HTML_FILES = [
    'index.html', 'guide.html', 'maturity.html', 'graph.html',
    'workflows.html', 'memory.html', 'synaptic.html', 'api.html', 'memory_history.html'
]

CSS_DIR = os.path.join(DASHBOARD_DIR, 'assets', 'css')
os.makedirs(CSS_DIR, exist_ok=True)
TOKENS_FILE = os.path.join(CSS_DIR, 'tokens.css')

all_tokens = {}
root_regex = re.compile(r':root\s*\{([^}]+)\}', re.MULTILINE)
var_regex = re.compile(r'(--[\w-]+)\s*:\s*([^;]+);')

# Phase 1: Gather tokens
for filename in HTML_FILES:
    filepath = os.path.join(DASHBOARD_DIR, filename)
    with open(filepath, 'r') as f:
        content = f.read()
    
    match = root_regex.search(content)
    if match:
        block = match.group(1)
        for var_match in var_regex.finditer(block):
            var_name = var_match.group(1).strip()
            var_val = var_match.group(2).strip()
            if var_name not in all_tokens:
                all_tokens[var_name] = var_val
            elif all_tokens[var_name] != var_val:
                # Same variable name, different value. 
                print(f"Warning: Conflict for {var_name} in {filename}: '{all_tokens[var_name]}' != '{var_val}'")
                # We'll just keep the first one encountered (or index.html since it's first in array)

print(f"Discovered {len(all_tokens)} CSS tokens.")

# Phase 2: Write tokens.css
with open(TOKENS_FILE, 'w') as f:
    f.write('/* Mories CSS Tokens - Auto-extracted */\n')
    f.write(':root {\n')
    for k, v in sorted(all_tokens.items()):
        f.write(f'  {k}: {v};\n')
    f.write('}\n')

# Phase 3: Update HTML files
for filename in HTML_FILES:
    filepath = os.path.join(DASHBOARD_DIR, filename)
    with open(filepath, 'r') as f:
        content = f.read()

    # Remove the :root block completely
    new_content = root_regex.sub('', content)

    # If the file had a :root block, it means it was previously defining tokens.
    # Add the link tag right after the `<title>` or another <link> in <head>.
    # Wait, some files might already have a <style> containing just `* { margin:0 }` after removal.
    # Let's clean up empty <style> tags
    new_content = new_content.replace('<style>\n\n', '<style>\n')
    new_content = new_content.replace('<style>\n    \n', '<style>\n')
    
    # Add the <link> tag for tokens.css before the first <style> block, if it doesn't already have one
    if 'tokens.css' not in new_content:
        link_tag = '  <link rel="stylesheet" href="/dashboard/assets/css/tokens.css">\n  <style>'
        new_content = new_content.replace('<style>', link_tag, 1)

    with open(filepath, 'w') as f:
        f.write(new_content)

print("Done. Generated tokens.css and updated HTML files.")
