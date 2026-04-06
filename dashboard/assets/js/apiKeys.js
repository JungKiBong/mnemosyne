// dashboard/assets/js/apiKeys.js
async function loadApiKeys() {
  const container = document.getElementById('keys-list');
  if(!container) return;
  
  try {
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">Loading...</div>';
    const res = await window.moriesApi.get('security/keys');
    if (!res || !res.keys) {
      container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--accent-red)">Failed to load keys (Check backend API)</div>';
      return;
    }
    
    if (res.keys.length === 0) {
      container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">No API Keys generated yet.</div>';
      return;
    }
    
    const keysHtml = res.keys.map(keyObj => {
      let expireBadge = '';
      const hash = keyObj.key_hash || '';
      if (keyObj.expires_at) {
        const expDate = new Date(keyObj.expires_at);
        const now = new Date();
        const daysLeft = Math.ceil((expDate - now) / (1000 * 60 * 60 * 24));
        
        if (daysLeft <= 0) {
          expireBadge = `<span style="padding:2px 8px;border-radius:4px;background:rgba(239,68,68,0.2);color:var(--accent-red);border:1px solid rgba(239,68,68,0.5);font-size:10px;font-weight:bold;margin-left:8px;">🚨 EXPIRED</span>`;
        } else if (daysLeft <= 10) {
          expireBadge = `<span style="padding:2px 8px;border-radius:4px;background:rgba(249,115,22,0.2);color:var(--accent-orange);border:1px solid rgba(249,115,22,0.5);font-size:10px;font-weight:bold;margin-left:8px;animation:pulse-dot 2s infinite">⚠️ Expires in ${daysLeft} days</span>`;
        } else {
          expireBadge = `<span style="padding:2px 8px;border-radius:4px;background:rgba(34,197,94,0.1);color:var(--accent-green);border:1px solid rgba(34,197,94,0.3);font-size:10px;margin-left:8px;">Valid for ${daysLeft} days</span>`;
        }
      } else {
          expireBadge = `<span style="padding:2px 8px;border-radius:4px;background:rgba(139,92,246,0.1);color:var(--accent-purple);border:1px solid rgba(139,92,246,0.3);font-size:10px;margin-left:8px;">Never Expires</span>`;
      }

      return `
      <div class="setting-row" style="padding:16px;background:var(--bg-secondary);border-radius:8px;margin-bottom:12px;border:1px solid var(--border); ${expireBadge.includes('EXPIRED') ? 'opacity:0.6;' : ''}">
        <div>
          <div style="font-weight:600;font-size:14px;color:var(--text-primary)">
            🔑 ${keyObj.name || 'Unnamed Key'} ${expireBadge}
          </div>
          <div style="font-size:12px;margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
            ${(keyObj.allowed_scopes || []).map(s => `<span style="padding:2px 6px;border-radius:4px;background:rgba(139,92,246,0.1);color:var(--accent-purple);border:1px solid rgba(139,92,246,0.2)">${s}</span>`).join('')}
          </div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:6px;font-family:'JetBrains Mono',monospace">
            Hash: ${hash.substring(0, 12)}... | Roles: ${(keyObj.roles || []).join(', ')} | Used: ${keyObj.usage_count || 0} times
          </div>
        </div>
        <button onclick="revokeApiKey('${hash}')" style="padding:6px 12px;border-radius:6px;border:1px solid rgba(239,68,68,0.3);background:transparent;color:var(--accent-red);cursor:pointer;font-size:12px;transition:all 0.2s;font-weight:600" onmouseover="this.style.background='rgba(239,68,68,0.1)'" onmouseout="this.style.background='transparent'">
          Revoke
        </button>
      </div>
      `;
    }).join('');
    
    container.innerHTML = keysHtml;
  } catch (e) {
    container.innerHTML = `<div style="padding:20px;color:var(--accent-red)">Error: ${e.message}</div>`;
  }
}

async function createApiKey() {
  const name = document.getElementById('new-key-name').value || 'New Key';
  const rawScopes = document.getElementById('new-key-scopes').value;
  const scopes = rawScopes ? rawScopes.split(',').map(s => s.trim()) : ['personal', 'global'];
  const expires = document.getElementById('new-key-expires').value;
  
  try {
    const data = await window.moriesApi.post('security/keys', {
      owner_id: 'admin',
      name: name,
      roles: ['agent'],
      allowed_scopes: scopes,
      expires_in_days: parseInt(expires, 10)
    });
    
    if (data && data.api_key) {
      alert(`KEY CREATED SUCCESSFULLY!\n\nPlease copy this immediately, it will not be shown again:\n\n${data.api_key}`);
      document.getElementById('new-key-name').value = '';
      document.getElementById('new-key-scopes').value = '';
      loadApiKeys();
    } else {
      alert("Failed to create key: " + (data.error || "Unknown error"));
    }
  } catch (e) {
    alert("Error: " + e.message);
  }
}

async function revokeApiKey(hash) {
  if (!confirm("Are you sure you want to revoke this key?\nAgents using it will lose access immediately.")) return;
  
  try {
    await window.moriesApi.delete(`security/keys/${hash}`);
    loadApiKeys();
  } catch(e) {
    alert("Error: " + e.message);
  }
}

window.addEventListener('DOMContentLoaded', () => {
    loadApiKeys();
});

window.loadApiKeys = loadApiKeys;
window.createApiKey = createApiKey;
window.revokeApiKey = revokeApiKey;
