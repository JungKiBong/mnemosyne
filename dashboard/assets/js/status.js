// dashboard/assets/js/status.js
// API_BASE is now auto-detected by apiClient.js — expose for backward compatibility
window.API_BASE = window.moriesApi ? window.moriesApi.baseUrl : 'http://localhost:5001/api';

function updateSystemStatus() {
  const el = document.getElementById('sys-backend');
  if(!el) return;
  el.textContent = 'Hybrid';
  document.getElementById('sys-neo4j').textContent = 'Connected';
  document.getElementById('sys-neo4j').className = 'system-value good';
  document.getElementById('sys-sm').textContent = 'Ready';
  document.getElementById('sys-sm').className = 'system-value good';
  document.getElementById('sys-cb').textContent = 'CLOSED';
  document.getElementById('sys-outbox').textContent = '0 pending';
  document.getElementById('sys-outbox').className = 'system-value good';
  document.getElementById('sys-observers').textContent = '3/3 active';
  document.getElementById('sys-observers').className = 'system-value good';
  document.getElementById('sys-llm').textContent = 'Ollama (local)';
  document.getElementById('sys-llm').className = 'system-value good';

  document.getElementById('neo4j-status').className = 'status-dot green';
  document.getElementById('sm-status').className = 'status-dot green';
  document.getElementById('observer-status').className = 'status-dot green';
}

async function pollStatus() {
  if (!window.moriesApi) return;
  
  try {
    const h = await window.moriesApi.get('health');
    if (!h) return;

    const setDot = (id, ok) => {
      const el = document.getElementById(id);
      if(el) el.className = 'status-dot ' + (ok ? 'green' : 'red');
    };
    setDot('neo4j-status', h.neo4j === 'connected');
    setDot('sm-status', h.supermemory === 'configured');
    setDot('observer-status', h.observers > 0);

    const setVal = (id, text, ok) => {
      const el = document.getElementById(id);
      if(el) {
        el.textContent = text;
        el.className = 'system-value ' + (ok ? 'good' : 'warn');
      }
    };
    setVal('sys-backend', h.backend, true);
    setVal('sys-neo4j', h.neo4j === 'connected' ? `Connected (${h.neo4j_nodes} nodes)` : h.neo4j, h.neo4j === 'connected');
    setVal('sys-sm', h.supermemory, h.supermemory === 'configured');
    setVal('sys-cb', 'CLOSED', true);
    setVal('sys-outbox', '0 pending', true);
    setVal('sys-observers', `${h.observers}/3 active`, h.observers > 0);
    if(h.llm) {
        setVal('sys-llm', `${h.llm.provider} (${h.llm.model})`, true);
    }
    setVal('sys-adapters', `${h.adapters} registered`, true);

    const nodeStat = document.getElementById('stat-nodes');
    if(nodeStat) nodeStat.textContent = h.neo4j_nodes.toLocaleString();
  } catch(e) {
    // API not available, silent fail for polling
  }
}

window.addEventListener('DOMContentLoaded', () => {
  updateSystemStatus();
  setInterval(pollStatus, 5000);
  pollStatus();
});

window.updateSystemStatus = updateSystemStatus;
window.pollStatus = pollStatus;
