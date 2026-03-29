import markdown
import re
import os

md_path = '/Users/jungkibong/Projects/tmp/mirofish-supermemory/GUIDE.md'
html_path = '/Users/jungkibong/Projects/tmp/mirofish-supermemory/dashboard/guide.html'

with open(md_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Convert markdown to html
md = markdown.Markdown(extensions=['toc', 'fenced_code', 'tables'])
html_content = md.convert(text)

# We want to build a custom sidebar based on h2 and h3
# The 'toc' extension might create a TOC, but we want our own UI.
# Let's extract headers using regex from the generated HTML
headers = []
for match in re.finditer(r'<h([23]) id="([^"]+)">([^<]+)</h[23]>', html_content):
    level = int(match.group(1))
    id_str = match.group(2)
    title = match.group(3)
    headers.append({"level": level, "id": id_str, "title": title})

sidebar_html = ""
current_h2 = None
for h in headers:
    if h['level'] == 2:
        if current_h2:
            sidebar_html += "</div></div>\n"
        sidebar_html += f'''
        <div class="cat-group">
          <div class="cat-header" onclick="this.parentElement.classList.toggle('collapsed')">
            <span><a href="#{h['id']}" style="color:inherit">{h['title']}</a></span>
            <span class="arrow">▼</span>
          </div>
          <div class="cat-items">
        '''
        current_h2 = h
    elif h['level'] == 3:
        sidebar_html += f'''
            <div class="endpoint-item" onclick="document.getElementById('{h['id']}').scrollIntoView({{behavior:'smooth'}})">{h['title']}</div>
        '''
if current_h2:
    sidebar_html += "</div></div>\n"


template = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mories Guide</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0a0e1a;
  --bg-card: #111827;
  --bg-surface: #1a2236;
  --bg-hover: #1f2b42;
  --border: #2a3550;
  --border-bright: #3b4f73;
  --text: #e2e8f0;
  --text-dim: #94a3b8;
  --text-muted: #64748b;
  --accent: #6366f1;
  --accent-glow: rgba(99,102,241,.15);
  --green: #22c55e;
  --cyan: #06b6d4;
  --radius: 10px;
  --font: 'Inter', -apple-system, sans-serif;
  --mono: 'JetBrains Mono', monospace;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: var(--font); background: var(--bg); color: var(--text); min-height: 100vh; }
a { color: var(--accent); text-decoration: none; }

/* Topbar */
.topbar { background: rgba(17,24,39,0.9); backdrop-filter: blur(10px); display: flex; align-items: center; justify-content: space-between; padding: 0 32px; height: 64px; border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 100; }
.topbar h1 { font-size: 20px; font-weight: 800; display: flex; align-items: center; gap: 8px; }
.topbar h1 span { background: linear-gradient(135deg, var(--accent), var(--cyan)); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.nav { display: flex; gap: 24px; font-size: 14px; font-weight: 500; }
.nav a { color: var(--text-dim); transition: color .2s; }
.nav a:hover, .nav a.active { color: var(--text); }

.layout { display: flex; min-height: calc(100vh - 64px); }
.sidebar { width: 320px; border-right: 1px solid var(--border); display: flex; flex-direction: column; background: var(--bg-card); flex-shrink: 0; position: sticky; top: 64px; height: calc(100vh - 64px); overflow-y: auto; }
.main { flex: 1; padding: 40px 60px; max-width: calc(100% - 320px); overflow-y: auto; scroll-behavior: smooth; }

.sidebar-header { padding: 20px; border-bottom: 1px solid var(--border); }
.sidebar-header h2 { font-size: 16px; font-weight: 600; }

.category-list { flex: 1; padding: 8px 0; }
.cat-group { margin-bottom: 2px; }
.cat-header { padding: 8px 20px; font-size: 12px; font-weight: 600; color: var(--text-dim); cursor: pointer; display: flex; justify-content: space-between; align-items: center; user-select: none; }
.cat-header:hover { background: var(--bg-hover); color: var(--text); }
.cat-group.collapsed .arrow { transform: rotate(-90deg); }
.cat-group.collapsed .cat-items { display: none; }
.endpoint-item { padding: 8px 20px 8px 32px; font-size: 13px; color: var(--text-muted); cursor: pointer; }
.endpoint-item:hover { background: var(--bg-surface); color: var(--text); }

.markdown-body { font-size: 15px; line-height: 1.7; color: var(--text); max-width: 900px; margin: 0 auto; }
.markdown-body h1 { font-size: 32px; margin-bottom: 24px; font-weight: 700; background: linear-gradient(135deg, #fff, #94a3b8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.markdown-body h2 { font-size: 24px; margin-top: 48px; margin-bottom: 16px; font-weight: 600; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
.markdown-body h3 { font-size: 18px; margin-top: 32px; margin-bottom: 12px; font-weight: 600; color: #fff; }
.markdown-body p { margin-bottom: 16px; color: var(--text-dim); }
.markdown-body ul, .markdown-body ol { margin-bottom: 16px; padding-left: 24px; color: var(--text-dim); }
.markdown-body li { margin-bottom: 8px; }
.markdown-body code { font-family: var(--mono); background: var(--bg-surface); padding: 2px 6px; border-radius: 4px; font-size: 13px; color: var(--cyan); }
.markdown-body pre { background: var(--bg-surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; overflow-x: auto; margin-bottom: 16px; }
.markdown-body pre code { background: none; padding: 0; color: #e2e8f0; font-size: 13px; line-height: 1.5; }
.markdown-body blockquote { border-left: 4px solid var(--accent); padding-left: 16px; color: var(--text-muted); margin-bottom: 16px; background: var(--bg-surface); padding: 12px 16px; border-radius: 0 8px 8px 0; }
.markdown-body hr { border: none; border-top: 1px solid var(--border); margin: 32px 0; }
.markdown-body table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px; }
.markdown-body th { text-align: left; padding: 12px; background: var(--bg-surface); color: var(--text-muted); font-weight: 600; border-bottom: 2px solid var(--border); }
.markdown-body td { padding: 12px; border-bottom: 1px solid var(--border); color: var(--text-dim); }
.markdown-body tr:hover td { background: rgba(255,255,255,0.02); color: var(--text); }
</style>
</head>
<body>

<div class="topbar">
  <h1>🧠 <span>Mories</span></h1>
  <div class="nav">
    <a href="/">Dashboard</a>
    <a href="/graph">Graph Explorer</a>
    <a href="/memory">Memory</a>
    <a href="/memory/synaptic">Synaptic</a>
    <a href="/maturity">Maturity</a>
    <a href="/api-docs">API Explorer</a>
    <a href="/workflows">Workflows</a>
    <a href="/guide" class="active">Guide</a>
  </div>
</div>

<div class="layout">
  <aside class="sidebar">
    <div class="sidebar-header">
      <h2>CONTENTS</h2>
    </div>
    <div class="category-list">
      {sidebar}
    </div>
  </aside>
  <div class="main">
    <div class="markdown-body">
      {content}
    </div>
  </div>
</div>

</body>
</html>
"""

final_html = template.replace('{sidebar}', sidebar_html).replace('{content}', html_content)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(final_html)

print("Guide HTML created successfully at", html_path)
