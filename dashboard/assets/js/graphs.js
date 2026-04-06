// dashboard/assets/js/graphs.js
async function loadGraphs() {
  const container = document.getElementById('projects-list');
  if(!container) return;
  
  try {
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">Loading...</div>';
    const res = await window.moriesApi.get('graphs');
    
    if (!res || !res.graphs) {
      container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--accent-red)">Failed to load graphs</div>';
      return;
    }
    
    if (res.graphs.length === 0) {
      container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">No projects found</div>';
      return;
    }
    
    container.innerHTML = res.graphs.sort((a,b) => b.count - a.count).map(g => `
      <div class="setting-row" style="padding:16px;background:var(--bg-secondary);border-radius:8px;margin-bottom:12px;border:1px solid var(--border)">
        <div>
          <div style="font-weight:600;font-size:14px;color:var(--text-primary);display:flex;align-items:center;gap:8px">
            📁 ${g.graph_id}
            <span style="font-size:10px;padding:2px 6px;border-radius:4px;background:var(--bg-card);color:var(--text-muted);border:1px solid var(--border)">${g.count} nodes</span>
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:4px;font-family:'JetBrains Mono',monospace">Scope access required if private</div>
        </div>
        <div style="display:flex;align-items:center;gap:12px">
          <span style="font-size:12px;color:${g.is_public ? 'var(--accent-green)' : 'var(--accent-orange)'};font-family:'JetBrains Mono',monospace">
            ${g.is_public ? '🌍 Public Access' : '🔒 Private (Token Required)'}
          </span>
          <label class="toggle">
            <input type="checkbox" ${g.is_public ? 'checked' : ''} onchange="toggleGraphVisibility('${g.graph_id}', this.checked)">
            <span class="slider"></span>
          </label>
        </div>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = `<div style="padding:20px;color:var(--accent-red)">Error: ${e.message}</div>`;
  }
}

async function toggleGraphVisibility(graphId, isPublic) {
  try {
    await window.moriesApi.post(`graphs/${encodeURIComponent(graphId)}/visibility`, { is_public: isPublic });
    loadGraphs();
  } catch(e) {
    alert("Failed to change visibility: " + e.message);
  }
}

window.addEventListener('DOMContentLoaded', () => {
    loadGraphs();
});

window.loadGraphs = loadGraphs;
window.toggleGraphVisibility = toggleGraphVisibility;
