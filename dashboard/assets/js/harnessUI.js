(function(){
'use strict';

const BASE = 'analytics/harness';
let allPatterns = [];
let overviewData = null;

// ── Init ──
document.addEventListener('DOMContentLoaded', async () => {
  setupTabs();
  addToolRow();
  addToolRow();
  await loadData();
  window.applyI18n();
});

// ── Tab switching ──
function setupTabs() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    });
  });
}

// ── Fetch data ──
async function loadData() {
  window._harness_loadData = loadData;
  try {
    const [overviewRes, listRes] = await Promise.all([
      window.moriesApi.get(BASE + '/overview'),
      window.moriesApi.get(BASE + '/list'),
    ]);
    overviewData = overviewRes.overview || {};
    allPatterns = listRes.patterns || [];

    renderStats();
    renderOverviewCharts();
    renderPatternGrid();
    buildDomainFilter();
    renderRecentTable();
    loadTrendChart();
    loadToolsChart();
  } catch (e) {
    console.error('Harness load error:', e);
    toast(window.t('harness.loadError'), 'error');
  }
}

async function loadTrendChart() {
  try {
    const data = await window.moriesApi.get('harness/analytics/trend?days=30');
    if (data.status === 'ok' && data.data) {
      renderTrendChart(data.data);
    }
  } catch (e) {
    console.warn('Trend chart load failed:', e);
  }
}

async function loadToolsChart() {
  try {
    const data = await window.moriesApi.get('harness/analytics/tools?limit=5');
    if (data.status === 'ok' && data.tools) {
      renderToolsChart(data.tools);
    }
  } catch (e) {
    console.warn('Tools chart load failed:', e);
  }
}

function renderTrendChart(runs) {
  const container = document.getElementById('trendChartContainer');
  if (!container || runs.length === 0) {
    if (container) container.innerHTML = '<div style="color:var(--muted);font-size:13px;text-align:center;width:100%">No execution data</div>';
    return;
  }
  const reversed = [...runs].reverse(); // oldest first
  const maxMs = Math.max(...reversed.map(r => r.elapsed_ms || 1), 1);
  
  container.innerHTML = reversed.map((r, i) => {
    const h = Math.max(8, ((r.elapsed_ms || 0) / maxMs) * 90);
    const color = r.success ? '#22c55e' : '#ef4444';
    const bg = r.success ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)';
    const ts = r.timestamp ? new Date(r.timestamp).toLocaleString() : '';
    return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;" title="${ts}\n${r.success?'✅ Success':'❌ Failed'}\n${(r.elapsed_ms||0).toLocaleString()}ms">
      <div style="font-size:9px;color:${color};margin-bottom:2px;">${r.success?'✓':'✗'}</div>
      <div style="width:100%;height:${h}%;background:${bg};border:1px solid ${color};border-radius:3px;min-height:4px;transition:height 0.3s;"></div>
    </div>`;
  }).join('');
}

function renderToolsChart(tools) {
  const container = document.getElementById('toolsChartContainer');
  if (!container || tools.length === 0) {
    if (container) container.innerHTML = '<div style="color:var(--muted);font-size:13px;text-align:center;">No tool data yet</div>';
    return;
  }
  
  // tools array contains { name, total_uses, success_rate (0-100) }
  const colors = ['c0', 'c1', 'c2', 'c3', 'c4'];
  container.innerHTML = tools.map((t, i) => {
    const rate = Math.round(t.success_rate || 0);
    return `
      <div class="bar-row">
        <div class="bar-label" title="${t.total_uses} uses">${t.name}</div>
        <div class="bar-track">
          <div class="bar-fill ${colors[i % colors.length]}" style="width:${Math.max(rate, 5)}%">${rate}%</div>
        </div>
      </div>
    `;
  }).join('');
}

// ── Stats cards ──
function renderStats() {
  const ov = overviewData;
  document.getElementById('statPatterns').textContent = ov.total_patterns || 0;
  document.getElementById('statExec').textContent = (ov.total_executions || 0).toLocaleString();
  document.getElementById('statSuccess').textContent = ((ov.avg_success_rate || 0) * 100).toFixed(1) + '%';
  document.getElementById('statDomains').textContent = Object.keys(ov.domains || {}).length;
}

// ── Charts ──
function renderOverviewCharts() {
  renderBarChart('domainChart', overviewData.domains || {});
  renderBarChart('typeChart', overviewData.process_types || {});
}

function renderBarChart(containerId, data) {
  const container = document.getElementById(containerId);
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(e => e[1]), 1);
  const colors = ['c0','c1','c2','c3','c4','c5'];

  if (entries.length === 0) {
    container.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:20px;text-align:center">No data</div>';
    return;
  }

  container.innerHTML = entries.map(([label, count], i) => `
    <div class="bar-row">
      <div class="bar-label">${label}</div>
      <div class="bar-track">
        <div class="bar-fill ${colors[i % colors.length]}" style="width:${(count/max*100).toFixed(1)}%">${count}</div>
      </div>
    </div>
  `).join('');
}

// ── Recent exec table ──
function renderRecentTable() {
  const sorted = [...allPatterns]
    .filter(p => p.execution_count > 0)
    .sort((a, b) => b.execution_count - a.execution_count)
    .slice(0, 8);

  const container = document.getElementById('recentExecTable');
  if (sorted.length === 0) {
    container.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:20px;text-align:center">No executions yet</div>';
    return;
  }

  container.innerHTML = `
    <table style="width:100%;border-collapse:collapse;margin-top:12px">
      <thead>
        <tr style="border-bottom:1px solid var(--border)">
          <th style="text-align:left;padding:8px;font-size:11px;color:var(--muted);text-transform:uppercase">${window.t('harness.domain')}</th>
          <th style="text-align:left;padding:8px;font-size:11px;color:var(--muted);text-transform:uppercase">${window.t('harness.trigger')}</th>
          <th style="text-align:center;padding:8px;font-size:11px;color:var(--muted);text-transform:uppercase">${window.t('harness.execCount')}</th>
          <th style="text-align:center;padding:8px;font-size:11px;color:var(--muted);text-transform:uppercase">${window.t('harness.successRate')}</th>
        </tr>
      </thead>
      <tbody>
        ${sorted.map(p => {
          const pct = (p.success_rate * 100).toFixed(0);
          const cls = p.success_rate >= .8 ? 'good' : p.success_rate >= .5 ? 'warn' : 'bad';
          return `<tr style="border-bottom:1px solid var(--border);cursor:pointer" onclick="openDetail('${p.uuid}')">
            <td style="padding:8px;font-size:13px;font-weight:600">${p.domain}</td>
            <td style="padding:8px;font-size:13px;color:var(--muted)">${p.trigger}</td>
            <td style="padding:8px;text-align:center;font-size:13px">${p.execution_count}</td>
            <td style="padding:8px;text-align:center">
              <span class="${cls}" style="font-weight:600">${pct}%</span>
              <div class="success-bar"><div class="success-bar-fill ${cls}" style="width:${pct}%"></div></div>
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>
  `;
}

// ── Pattern Grid ──
function renderPatternGrid(filter) {
  const grid = document.getElementById('patternGrid');
  let list = allPatterns;

  if (filter) {
    const q = filter.toLowerCase();
    list = list.filter(p =>
      p.domain?.toLowerCase().includes(q) ||
      p.trigger?.toLowerCase().includes(q) ||
      p.name?.toLowerCase().includes(q) ||
      (p.tags || []).some(t => t.toLowerCase().includes(q))
    );
  }

  const domainFilter = document.getElementById('filterDomain')?.value;
  if (domainFilter) {
    list = list.filter(p => p.domain === domainFilter);
  }

  if (list.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="icon">♞</div>
        <p data-i18n="harness.noPatterns">${window.t('harness.noPatterns')}</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = list.map(p => {
    const pct = (p.success_rate * 100).toFixed(0);
    const cls = p.success_rate >= .8 ? 'good' : p.success_rate >= .5 ? 'warn' : 'bad';
    const tags = (p.tags || []).map(t => `<span class="tag tag-custom">${t}</span>`).join('');
    return `
      <div class="pattern-card" onclick="openDetail('${p.uuid}')">
        <div class="p-header">
          <h3>${escHtml(p.name || p.trigger)}</h3>
          <span class="p-version">v${p.version}</span>
        </div>
        <span class="p-domain">${p.domain}</span>
        <div class="p-trigger">${escHtml(p.trigger)}</div>
        <div class="p-meta">
          <span class="tag tag-type">${p.process_type}</span>
          <span class="tag tag-scope">${p.scope}</span>
          ${tags}
        </div>
        ${p.success_rate < 0.8 && p.execution_count > 0 ? `<div style="margin: 8px 0; color: #f44336; font-size: 12px; font-weight: bold; background: rgba(244, 67, 54, 0.1); padding: 4px 8px; border-radius: 4px; display: inline-block;">⚠️ Failure Alert: Attention Needed</div>` : ''}
        <div class="p-stats">
          <span>🔧 ${p.tool_count} tools</span>
          <span>▶ ${p.execution_count}x</span>
          <span class="${cls}">
            ${pct}%
            <span class="success-bar"><span class="success-bar-fill ${cls}" style="width:${pct}%"></span></span>
          </span>
        </div>
      </div>
    `;
  }).join('');
}

// ── Domain filter ──
function buildDomainFilter() {
  const select = document.getElementById('filterDomain');
  const domains = [...new Set(allPatterns.map(p => p.domain))].sort();
  select.innerHTML = `<option value="">${window.t('harness.allDomains')}</option>` +
    domains.map(d => `<option value="${d}">${d}</option>`).join('');
  select.onchange = () => renderPatternGrid(document.getElementById('searchInput').value);
}

// ── Search ──
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('searchInput');
  if (input) input.addEventListener('input', e => renderPatternGrid(e.target.value));
});

// ── Detail modal ──
function renderTree(node, isRoot = false) {
    if (!node) return '';
    let html = '';
    
    let icon = '📂';
    if (node.level === 'run') icon = node.metadata?.success ? '✅' : '❌';
    if (node.level === 'step') icon = node.metadata?.success ? '🔸' : '🔻';
    
    let metaHtml = '';
    if (node.metadata) {
      if (node.metadata.elapsed_ms) metaHtml += `<span style="font-size: 11px; color: var(--muted); margin-left: 8px">${node.metadata.elapsed_ms}ms</span>`;
      if (node.metadata.total_ms) metaHtml += `<span style="font-size: 11px; color: var(--muted); margin-left: 8px">${node.metadata.total_ms}ms</span>`;
      
      // v4 Badges
      const st = node.metadata.step_type;
      if (st) {
        if (st === 'branch') metaHtml += `<span class="v-badge" style="background:#3b82f6; margin-left:8px">🔀 Branch</span>`;
        else if (st === 'loop') metaHtml += `<span class="v-badge" style="background:#8b5cf6; margin-left:8px">🔁 Loop</span>`;
        else if (st === 'parallel') metaHtml += `<span class="v-badge" style="background:#f59e0b; margin-left:8px">⏸ Parallel</span>`;
        else if (st === 'container_exec') metaHtml += `<span class="v-badge" style="background:#0ea5e9; margin-left:8px">🐳 Docker</span>`;
        else if (st === 'ray') metaHtml += `<span class="v-badge" style="background:#14b8a6; margin-left:8px">☀️ Ray</span>`;
        else if (st === 'nomad') metaHtml += `<span class="v-badge" style="background:#ec4899; margin-left:8px">⬡ Nomad</span>`;
        else if (st === 'hitl_gate') {
           const isSus = node.metadata.status === 'suspended';
           metaHtml += `<span class="v-badge" style="background:${isSus ? '#f59e0b' : '#10b981'}; margin-left:8px">👨‍💻 HITL ${isSus?'(Wait)':'(Done)'}</span>`;
        }
      }
      if (node.metadata.status === 'healed') {
        metaHtml += `<span class="v-badge" style="background:#10b981; margin-left:8px">✨ Healed</span>`;
      }
    }

    const hasChildren = node.children && Object.keys(node.children).length > 0;
    
    if (hasChildren) {
        // v4: indent logic is slightly larger for visual grouping
        html += `<details ${isRoot || node.level === 'domain' || node.level === 'workflow' ? 'open' : ''} style="margin-left: ${isRoot ? '0' : '20px'}; border-left: 2px dashed rgba(255,255,255,0.1); padding-left: 8px; margin-bottom: 6px;">`;
        html += `<summary style="cursor: pointer; padding: 4px 0; outline: none; user-select: none;">
          <span style="font-size: 12px; margin-right: 4px">${icon}</span>
          <span style="font-size: 13px; font-weight: 600;">${escHtml(node.name)}</span>
          <span style="font-size: 11px; color: var(--muted); margin-left: 8px">[${node.level}]</span>
          ${metaHtml}
        </summary>`;
        html += `<div style="margin-top: 4px; padding-bottom: 4px;">`;
        for (const [key, childNode] of Object.entries(node.children)) {
            html += renderTree(childNode, false);
        }
        html += `</div></details>`;
    } else {
        html += `<div style="margin-left: ${isRoot ? '0' : '20px'}; border-left: 2px dashed rgba(255,255,255,0.1); padding: 4px 0 4px 8px; margin-bottom: 4px;">
          <span style="font-size: 12px; margin-right: 4px">${icon}</span>
          <span style="font-size: 13px; font-weight: 600;">${escHtml(node.name)}</span>
          <span style="font-size: 11px; color: var(--muted); margin-left: 8px">[${node.level}]</span>
          ${metaHtml}
        </div>`;
    }
    return html;
}

async function fetchAndRenderTree(uuid) {
    try {
        const data = await window.moriesApi.get(`${BASE}/${uuid}/tree`);
        if (data && data.tree && Object.keys(data.tree.children || {}).length > 0) {
            return `
              <h4 style="margin:20px 0 8px;font-size:14px">🌴 Execution Tree</h4>
              <div style="background:var(--bg); border-radius: 8px; padding: 12px; max-height: 300px; overflow-y: auto;">
                  ${renderTree(data.tree, true)}
              </div>
            `;
        }
    } catch (e) {
        console.error("ExecutionTree fetch failed", e);
    }
    return '';
}

window.suggestEvolve = async function(uuid) {
    const btn = document.querySelector(`button[onclick="suggestEvolve('${uuid}')"]`);
    const resultDiv = document.getElementById('aiEvolveResult');
    
    if (btn) {
        btn.disabled = true;
        btn.textContent = '제안 생성 중...';
    }
    
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div style="color:var(--muted); font-size:12px;">LLM이 과거 실행 트리를 분석하여 개선안을 도출하고 있습니다 (수십초 소요)...</div>';
    
    try {
        const data = await window.moriesApi.post(`analytics/harness/${uuid}/suggest_evolution`, { context: "Please analyze the tree to provide failure suggestions." });
        
        if (data.error) {
            resultDiv.innerHTML = `<div style="color:red; font-size:12px;">오류: ${escHtml(data.error)}</div>`;
            return;
        }
        
        const suggestion = data.suggested_evolution;
        
        let html = `<div style="background: rgba(139, 92, 246, 0.1); border: 1px solid var(--accent); padding: 12px; border-radius: 8px;">`;
        html += `<h5 style="margin:0 0 8px 0; color:var(--text);">💡 진화 아이디어</h5>`;
        
        if (suggestion.new_tool_chain && suggestion.new_tool_chain.length > 0) {
            html += `<div style="font-size:13px; font-weight:bold; margin-bottom:4px;">새로운 Tool Chain:</div>`;
            html += `<ul style="margin:0 0 8px 24px; font-size:12px;">`;
            suggestion.new_tool_chain.forEach(t => html += `<li>${escHtml(t)}</li>`);
            html += `</ul>`;
        }
        
        if (suggestion.conditionals && suggestion.conditionals.length > 0) {
            html += `<div style="font-size:13px; font-weight:bold; margin-bottom:4px;">제안된 Conditionals:</div>`;
            html += `<ul style="margin:0 0 8px 24px; font-size:12px;">`;
            suggestion.conditionals.forEach(c => html += `<li>[${c.type}] ${escHtml(c.condition)} → ${escHtml(c.then_action)}</li>`);
            html += `</ul>`;
        }
        
        html += `<div style="font-size:12px; color:var(--text); margin-top: 8px;"><strong>사유:</strong> ${escHtml(suggestion.reason)}</div>`;
        html += `</div>`;
        
        resultDiv.innerHTML = html;
        
    } catch (e) {
        resultDiv.innerHTML = `<div style="color:red; font-size:12px;">요청 실패: ${escHtml(e.message)}</div>`;
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '제안 받기';
        }
    }
}

window.openDetail = async function(uuid) {
  try {
    const data = await window.moriesApi.get(`${BASE}/${uuid}`);
    if (data.error) { toast(data.error, 'error'); return; }

    const h = data.harness || {};
    const stats = h.stats || {};
    const evolution = h.evolution || {};
    const extraction = h.extraction || {};
    const dataFlow = h.data_flow || {};
    
    window.currentHarnessDetail = h;
    window.currentHarnessUuid = uuid;

    document.getElementById('modalTitle').textContent = h.name || h.trigger || uuid;

    let body = '';

    // Summary
    body += `<div style="margin-bottom:20px">
      <p style="color:var(--muted);font-size:13px;margin-bottom:8px">${escHtml(h.description || '')}</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <span class="tag tag-type">${h.process_type || '-'}</span>
        <span class="tag tag-scope">${h.scope || '-'}</span>
        ${(h.tags || []).map(t => `<span class="tag tag-custom">${t}</span>`).join('')}
      </div>
    </div>`;

    // Tool Chain
    const chain = h.tool_chain || [];
    if (chain.length > 0) {
      body += `<h4 style="margin-bottom:8px;font-size:14px">${window.t('harness.toolChain')}</h4>`;
      body += '<div class="tc-flow">';
      chain.forEach((tool, i) => {
        if (i > 0) body += '<span class="tc-arrow">→</span>';
        body += `<div class="tc-node">
          <span class="step">#${i+1}</span>
          <span class="tool-name">${escHtml(tool.tool_name || tool.name || '?')}</span>
          <span class="tool-type">${tool.tool_type || tool.type || ''}</span>
        </div>`;
      });
      body += '</div>';
    }

    // Data Flow
    if (dataFlow.input || (dataFlow.intermediate && dataFlow.intermediate.length) || dataFlow.output) {
      body += `<h4 style="margin:16px 0 8px;font-size:14px">${window.t('harness.dataFlow')}</h4>`;
      body += '<div class="df-visual">';
      if (dataFlow.input) body += `<span class="df-node df-input">📥 ${dataFlow.input}</span>`;
      (dataFlow.intermediate || []).forEach(s => {
        body += `<span class="df-arrow">→</span><span class="df-node df-inter">${s}</span>`;
      });
      if (dataFlow.output) body += `<span class="df-arrow">→</span><span class="df-node df-output">📤 ${dataFlow.output}</span>`;
      body += '</div>';
    }

    // Conditionals (Orchestration & Fallback Logic)
    const conditionals = h.conditionals || [];
    if (conditionals.length > 0) {
      body += `<h4 style="margin:16px 0 8px;font-size:14px">${window.t ? window.t('harness.conditionals') || '조건부 & 오케스트레이션 로직' : '조건부 & 오케스트레이션 로직'}</h4>`;
      body += '<div class="evo-timeline" style="border-left: 3px solid var(--border);">';
      
      conditionals.forEach(cond => {
        let typeColor = '#ff9800'; // Default Fallback (orange)
        let typeLabel = cond.type ? cond.type.toUpperCase() : 'FALLBACK';
        let icon = '⚠️';
        let bgStyle = 'rgba(255, 152, 0, 0.05)';
        
        if (cond.type === 'fallback' || !cond.type) {
            typeColor = '#ff9800';
            icon = '⚠️';
            bgStyle = 'rgba(255, 152, 0, 0.05)';
        } else if (cond.type === 'retry') {
            typeColor = '#2196f3';
            icon = '🔄';
            bgStyle = 'rgba(33, 150, 243, 0.05)';
        } else if (cond.type === 'handoff') {
            typeColor = '#9c27b0';
            icon = '🤝';
            bgStyle = 'rgba(156, 39, 176, 0.05)';
        }

        body += `<div class="evo-entry" style="border-left: none; background: ${bgStyle}; margin-bottom: 8px;">
          <span class="v-badge" style="background:${typeColor};">${escHtml(typeLabel)}</span>
          <div class="v-info">
            <div style="font-size:13px; font-weight:600;">${icon} ${escHtml(cond.condition)}</div>
            <div class="reason" style="color:var(--muted); margin-top:4px;">
              → <strong>${window.t ? window.t('harness.thenAction') || 'Then action:' : 'Then action:'}</strong> ${escHtml(cond.then_action)}
              ${cond.target ? `<span style="background:var(--bg); border: 1px solid var(--border); padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-left: 6px;">🎯 ${escHtml(cond.target)}</span>` : ''}
            </div>
          </div>
        </div>`;
      });
      body += '</div>';
    }

    // Stats
    body += `<h4 style="margin:20px 0 8px;font-size:14px">📊 ${window.t ? window.t('harness.statsTitle') || 'Stats' : 'Stats'}</h4>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px">
      <div style="background:var(--bg);padding:10px;border-radius:8px;text-align:center">
        <div style="font-size:20px;font-weight:800">${stats.execution_count || 0}</div>
        <div style="font-size:11px;color:var(--muted)">${window.t('harness.execCount') || 'Exec Count'}</div>
      </div>
      <div style="background:var(--bg);padding:10px;border-radius:8px;text-align:center">
        <div style="font-size:20px;font-weight:800;color:var(--green)">${((stats.success_rate || 0)*100).toFixed(1)}%</div>
        <div style="font-size:11px;color:var(--muted)">${window.t('harness.successRate') || 'Success Rate'}</div>
      </div>
      <div style="background:var(--bg);padding:10px;border-radius:8px;text-align:center">
        <div style="font-size:20px;font-weight:800">${stats.avg_execution_time_ms || 0}ms</div>
        <div style="font-size:11px;color:var(--muted)">Avg Time</div>
      </div>
      <div style="background:var(--bg);padding:10px;border-radius:8px;text-align:center">
        <div style="font-size:20px;font-weight:800">$${(stats.total_cost_usd || 0).toFixed(4)}</div>
        <div style="font-size:11px;color:var(--muted)">Total Cost</div>
      </div>
      <div style="background:var(--bg);padding:10px;border-radius:8px;text-align:center">
        <div style="font-size:20px;font-weight:800">${evolution.current_version || 1}</div>
        <div style="font-size:11px;color:var(--muted)">${window.t('harness.version') || 'Version'}</div>
      </div>
    </div>`;

    // Evolution history — with rollback visualization
    const history = evolution.history || [];
    if (history.length > 0) {
      body += `<h4 style="margin:20px 0 8px;font-size:14px">${window.t('harness.evolution')}</h4>`;
      body += '<div class="evo-timeline">';
      history.slice().reverse().forEach(ev => {
        const isRollback = (ev.change_reason || '').toLowerCase().includes('rollback');
        const rollbackClass = isRollback ? ' rollback' : '';
        const icon = isRollback ? '⏪' : '';
        body += `<div class="evo-entry${rollbackClass}">
          <span class="v-badge">v${ev.version}</span>
          <div class="v-info">
            <span class="rate">${((ev.success_rate || 0)*100).toFixed(1)}% success</span>
            <div class="reason">${icon} ${escHtml(ev.change_reason || '-')}</div>
            <div style="font-size:11px;color:var(--muted);margin-top:2px">${ev.created_at || ''}</div>
          </div>
        </div>`;
      });
      body += '</div>';

      // Rollback UI button (if version > 1)
      if (evolution.current_version > 1) {
        body += `<div style="margin-top:12px;display:flex;gap:8px;align-items:center">
          <select id="rollbackVersion" style="background:var(--card);border:1px solid var(--border);border-radius:8px;color:var(--text);padding:6px 12px;font-size:13px">
            ${history.filter(h => h.version !== evolution.current_version && h.tool_chain).map(h => 
              `<option value="${h.version}">v${h.version} — ${escHtml((h.change_reason || '').substring(0,40))}</option>`
            ).join('')}
          </select>
          <button class="btn btn-sm btn-danger" onclick="doRollback('${uuid}')">⏪ Rollback</button>
        </div>`;
      }
    }

    // Fetch and render Execution Tree
    body += await fetchAndRenderTree(uuid);

    // Extraction info
    if (extraction.auto_extracted) {
      body += `<div style="margin-top:16px;padding:12px;background:rgba(245,158,11,.1);border-radius:10px;font-size:12px">
        ⚡ Auto-extracted (confidence: ${((extraction.extraction_confidence || 0)*100).toFixed(0)}%)
        ${extraction.user_verified ? '✅ User verified' : '⏳ Pending verification'}
      </div>`;
    }

    // AI Evolution Suggestion Area
    body += `
    <div id="aiEvolveArea" style="margin-top:20px; padding:12px; background:var(--bg); border:1px solid var(--accent); border-radius:10px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div>
          <h4 style="margin:0; font-size:14px; display:flex; align-items:center; gap:6px;">✨ AI 진화 제안</h4>
          <p style="margin:4px 0 0 0; font-size:12px; color:var(--muted);">성공률이 낮거나 오래된 패턴인가요? LLM이 더 나은 워크플로우를 제안합니다.</p>
        </div>
        <button class="btn btn-sm btn-outline" style="border-color:var(--accent); color:var(--accent);" onclick="suggestEvolve('${uuid}')">제안 받기</button>
      </div>
      <div id="aiEvolveResult" style="margin-top: 12px; display: none;"></div>
    </div>`;

    document.getElementById('modalFooter').innerHTML = `
      <button class="btn btn-primary" onclick="openEditMode()">Edit</button>
      <button class="btn btn-outline" onclick="closeModal()" data-i18n="close">닫기</button>
    `;

    document.getElementById('modalBody').innerHTML = body;
    document.getElementById('detailModal').classList.add('show');
  } catch (e) {
    toast('Failed to load detail', 'error');
    console.error(e);
  }
};

window.openEditMode = function() {
  const h = window.currentHarnessDetail;
  const uuid = window.currentHarnessUuid;
  
  let html = `<div style="margin-bottom: 12px;">
    <label style="display:block; font-size:12px; font-weight:600; margin-bottom:4px;">Domain</label>
    <input type="text" id="editDomain" class="harness-input" value="${escHtml(h.domain || '')}" style="width:100%; padding:8px; border-radius:6px; border:1px solid var(--border); background:var(--card); color:var(--text);"/>
  </div>
  <div style="margin-bottom: 12px;">
    <label style="display:block; font-size:12px; font-weight:600; margin-bottom:4px;">Description</label>
    <textarea id="editDescription" style="width:100%; padding:8px; border-radius:6px; border:1px solid var(--border); background:var(--card); color:var(--text); min-height:60px;">${escHtml(h.description || '')}</textarea>
  </div>
  <div style="margin-bottom: 12px;">
    <label style="display:block; font-size:12px; font-weight:600; margin-bottom:4px;">Trigger</label>
    <input type="text" id="editTrigger" class="harness-input" value="${escHtml(h.trigger || '')}" style="width:100%; padding:8px; border-radius:6px; border:1px solid var(--border); background:var(--card); color:var(--text);"/>
  </div>
  <div style="margin-bottom: 12px;">
    <label style="display:block; font-size:12px; font-weight:600; margin-bottom:4px;">Tags (comma separated)</label>
    <input type="text" id="editTags" class="harness-input" value="${escHtml((h.tags || []).join(', '))}" style="width:100%; padding:8px; border-radius:6px; border:1px solid var(--border); background:var(--card); color:var(--text);"/>
  </div>`;
  
  document.getElementById('modalBody').innerHTML = html;
  document.getElementById('modalFooter').innerHTML = `
    <button class="btn btn-primary" onclick="submitEditHarness()">Save</button>
    <button class="btn btn-outline" onclick="openDetail(window.currentHarnessUuid)">Cancel</button>
  `;
};

window.submitEditHarness = async function() {
  const uuid = window.currentHarnessUuid;
  const updates = {
    domain: document.getElementById('editDomain').value,
    description: document.getElementById('editDescription').value,
    trigger: document.getElementById('editTrigger').value,
    tags: document.getElementById('editTags').value.split(',').map(s => s.trim()).filter(s => s)
  };
  
  try {
    const data = await window.moriesApi.put(`${BASE}/${uuid}`, updates);
    if (data.error) throw new Error(data.error);
    toast('Harness updated successfully', 'success');
    openDetail(uuid); // refresh
  } catch (e) {
    toast(e.message || 'Update failed', 'error');
  }
};

function closeModal() {
  document.getElementById('detailModal').classList.remove('show');
}
window.closeModal = closeModal;

// ── Tool chain builder ──
let toolRowId = 0;
window.addToolRow = function() {
  const list = document.getElementById('toolChainList');
  const id = ++toolRowId;
  const row = document.createElement('div');
  row.className = 'tool-chain-item';
  row.id = 'tool-row-' + id;
  row.innerHTML = `
    <span class="step-num">${list.children.length + 1}</span>
    <input type="text" class="tc-name" data-i18n-placeholder="harness.toolNamePH" placeholder="도구명">
    <select class="tc-type">
      <option value="mcp">MCP</option>
      <option value="api">API</option>
      <option value="python">Python</option>
      <option value="shell">Shell</option>
      <option value="workflow">Workflow</option>
      <option value="agent">Agent</option>
    </select>
    <button class="remove-btn" onclick="removeToolRow('tool-row-${id}')" data-i18n="harness.removeTool">삭제</button>
  `;
  list.appendChild(row);
  renumberSteps();
  window.applyI18n(row);
};

window.removeToolRow = function(rowId) {
  document.getElementById(rowId)?.remove();
  renumberSteps();
};

function renumberSteps() {
  document.querySelectorAll('#toolChainList .tool-chain-item').forEach((row, i) => {
    const stepEl = row.querySelector('.step-num');
    if (stepEl) stepEl.textContent = i + 1;
  });
}

// ── Submit record ──
window.submitRecord = async function() {
  const domain = document.getElementById('recDomain').value.trim();
  const trigger = document.getElementById('recTrigger').value.trim();
  if (!domain || !trigger) { toast('Domain and Trigger are required', 'error'); return; }

  const toolChain = [];
  document.querySelectorAll('#toolChainList .tool-chain-item').forEach(row => {
    const name = row.querySelector('.tc-name').value.trim();
    const type = row.querySelector('.tc-type').value;
    if (name) toolChain.push({ tool_name: name, tool_type: type });
  });

  if (toolChain.length === 0) { toast('Add at least one tool', 'error'); return; }

  const tagsStr = document.getElementById('recTags').value.trim();
  const body = {
    domain,
    trigger,
    tool_chain: toolChain,
    description: document.getElementById('recDesc').value.trim(),
    process_type: document.getElementById('recProcessType').value,
    tags: tagsStr ? tagsStr.split(',').map(t => t.trim()).filter(Boolean) : [],
    scope: document.getElementById('recScope').value,
    agent_id: document.getElementById('recAgent').value.trim() || 'system',
  };

  try {
    const data = await window.moriesApi.post(BASE + '/record', body);
    if (data.error) { toast(data.error, 'error'); return; }
    if (data.status === 'merged') {
      toast(`🔄 기존 패턴에 머지됨: ${data.uuid}`, 'success');
    } else {
      toast(`✅ Pattern recorded: ${data.uuid}`, 'success');
    }
    // Reset form
    document.getElementById('recDomain').value = '';
    document.getElementById('recTrigger').value = '';
    document.getElementById('recDesc').value = '';
    document.getElementById('recTags').value = '';
    // Reload
    await loadData();
    // Switch to patterns tab
    document.querySelector('[data-tab="patterns"]').click();
  } catch (e) {
    toast('Record failed: ' + e.message, 'error');
  }
};

// ── Toast ──
function toast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show ' + type;
  setTimeout(() => el.classList.remove('show'), 3000);
}

// ── Escape HTML ──
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

})();

// ── Recommend Search (global scope) ──
async function searchRecommend() {
  const q = document.getElementById('recommendInput').value.trim();
  if (!q) return;
  const container = document.getElementById('recommendResults');
  container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--muted)">Searching...</div>';

  try {
    const data = await window.moriesApi.get(`analytics/harness/recommend?q=${encodeURIComponent(q)}&limit=8`);
    if (!data.recommendations || data.recommendations.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="icon">🤷</div><p>일치하는 패턴이 없습니다. 다른 키워드로 다시 시도해보세요.</p></div>';
      return;
    }
    container.innerHTML = data.recommendations.map(r => {
      const pct = (r.success_rate * 100).toFixed(0);
      const cls = r.success_rate >= .8 ? 'good' : r.success_rate >= .5 ? 'warn' : 'bad';
      const tokens = (r.match_tokens || []).map(t => `<span class="rec-match">${t}</span>`).join('');
      return `<div class="rec-result" onclick="openDetail('${r.uuid}')">
        <div style="display:flex;gap:16px;align-items:center">
          <div class="rec-score">${(r.relevance_score * 100).toFixed(0)}</div>
          <div style="flex:1">
            <div style="font-weight:700;font-size:15px;margin-bottom:4px">${r.name || r.trigger}</div>
            <span class="tag tag-type">${r.domain}</span>
            <span class="tag tag-scope">${r.process_type}</span>
            <span style="font-size:12px;color:var(--muted);margin-left:8px">🔧 ${r.tool_count} tools · ▶ ${r.execution_count}x</span>
            <span class="${cls}" style="font-size:12px;font-weight:600;margin-left:8px">${pct}%</span>
          </div>
        </div>
        <div style="margin-top:8px;font-size:12px">${tokens}</div>
      </div>`;
    }).join('');
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><p>Error: ${e.message}</p></div>`;
  }
}
window.searchRecommend = searchRecommend;
window.generateHarness = generateHarness;

async function generateHarness() {
  const input = document.getElementById('recommendInput');
  const query = input.value.trim();
  if (!query) {
    showToast('작업 설명을 입력해 주세요.', 'error');
    return;
  }
  
  const resultsDiv = document.getElementById('recommendResults');
  resultsDiv.innerHTML = '<div class="empty-state"><div class="icon">⏳</div><p>LLM을 통해 하네스 패턴을 생성하고 있습니다...</p><p style="font-size: 13px; color: var(--text-muted);">이 작업은 수십 초 정도 소요될 수 있습니다.</p></div>';

  try {
    const data = await window.moriesApi.post('analytics/harness/generate', { query: query, domain: 'general' });
    
    if (!data.generated_harness) {
      resultsDiv.innerHTML = '<div class="empty-state"><div class="icon">❌</div><p>결과를 생성하지 못했습니다.</p></div>';
      return;
    }
    
    const harness = data.generated_harness;
    const toolChain = harness.tool_chain || [];
    const conditionals = harness.conditionals || [];
    
    resultsDiv.innerHTML = `
      <div style="margin-bottom: 16px; font-size: 14px; display: flex; align-items: center; justify-content: space-between;">
        <span><strong>자동 생성 결과</strong> (도메인: general)</span>
      </div>
      <div class="harness-card" style="border: 1px solid var(--accent)">
        <div class="h-header">
          <span class="h-domain">Generated</span>
          <span class="h-type">Pipeline</span>
        </div>
        <div class="h-trigger">${query}</div>
        <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">${harness.description || ''}</p>
        
        <div class="mini-waterfall">
          ${toolChain.map((t, idx) => `
            <div class="wf-step">
              <span class="step-num">${idx+1}</span>
              <span class="step-tool">${typeof t === 'string' ? t : t.name || t.tool_name}</span>
            </div>
          `).join('')}
        </div>
        
        <div style="margin-top: 12px; display:flex; gap: 8px;">
          <span style="font-size: 12px; background: rgba(255,255,255,0.05); padding: 2px 8px; border-radius: 4px;">
            Conditionals: ${conditionals.length}
          </span>
        </div>
      </div>
    `;
    
  } catch(err) {
    showToast(err.message, 'error');
    resultsDiv.innerHTML = '<div class="empty-state"><div class="icon">❌</div><p>생성 중 오류가 발생했습니다.</p></div>';
  }
}

// Handle Enter key on recommend input
document.addEventListener('DOMContentLoaded', () => {
  const recInput = document.getElementById('recommendInput');
  if (recInput) recInput.addEventListener('keypress', e => { if (e.key === 'Enter') searchRecommend(); });
});

// ── Rollback (global scope) ──
async function doRollback(uuid) {
  const sel = document.getElementById('rollbackVersion');
  if (!sel || !sel.value) return;
  if (!confirm(`Version ${sel.value}로 롤백하시겠습니까?`)) return;

  try {
    const data = await window.moriesApi.post(`analytics/harness/${uuid}/rollback`, {to_version: parseInt(sel.value)});
    if (data.error) { alert(data.error); return; }
    alert(`✅ Rolled back: v${data.from_version} → v${data.to_version} (new: v${data.new_version})`);
    document.getElementById('detailModal').classList.remove('show');
    // Reload
    const loadDataFn = window._harness_loadData;
    if (loadDataFn) await loadDataFn();
  } catch (e) {
    alert('Rollback failed: ' + e.message);
  }
}
window.doRollback = doRollback;
// ── HITL Resolution ──
window.loadPendingHitl = async function() {
  const container = document.getElementById('hitlContainer');
  if (!container) return;
  container.innerHTML = '<div class="empty-state"><p>로딩 중...</p></div>';
  try {
    const data = await window.moriesApi.get('harness/hitl/pending');
    if (data.status !== 'success') throw new Error(data.error || 'Failed to fetch pending HITL');
    const pending = data.pending || [];
    if (pending.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="icon">✨</div><p>현재 피드백을 기다리는 항목이 없습니다.</p></div>';
      return;
    }
    
    container.innerHTML = pending.map(task => `
      <div style="border: 1px solid var(--orange); margin-bottom: 12px; padding: 16px; border-radius: 12px; background: var(--card);">
        <div style="display:flex; justify-content:space-between; margin-bottom: 8px;">
          <div>
            <span style="font-weight: 600; font-size: 14px;">Run ID: ${task.run_id}</span>
            <span style="font-size: 12px; margin-left: 8px; color: var(--muted);">Step: ${task.step_id}</span>
          </div>
          <span style="font-size: 12px; color: var(--muted);">${task.suspended_at}</span>
        </div>
        <div style="font-size: 13px; color: var(--text); background: var(--bg); padding: 8px; border-radius: 6px; margin-bottom: 12px; border-left: 3px solid var(--accent);">
          <strong>Trigger:</strong> ${task.context_preview || 'N/A'}
        </div>
        <div style="margin-bottom: 12px;">
          <input type="text" id="feedback_${task.run_id}" placeholder="피드백 입력 (선택사항)" style="padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font-size: 13px; width: 100%; max-width: 400px; outline: none;">
        </div>
        <div style="display:flex; gap: 8px;">
          <button class="btn btn-success btn-sm" onclick="resolveHitl('${task.run_id}', '${task.step_id}', true)">✅ 승인 (진행)</button>
          <button class="btn btn-danger btn-sm" onclick="resolveHitl('${task.run_id}', '${task.step_id}', false)">❌ 반려 (중단/우회)</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="icon">❌</div><p>오류 발생: ${e.message}</p></div>`;
  }
};

window.resolveHitl = async function(run_id, step_id, approved) {
  const fbInput = document.getElementById('feedback_' + run_id);
  const feedback = fbInput ? fbInput.value : '';
  
  if (!confirm(`${approved ? '✅ 승인' : '❌ 반려'} 처리하시겠습니까?`)) return;
  
  try {
    const data = await window.moriesApi.post('harness/hitl/resolve', { run_id, step_id, approved, feedback });
    if (data.error) throw new Error(data.error);
    
    // Use toast if available, else alert
    if (typeof toast === 'function') toast('✔️ HITL 피드백이 처리되었습니다.', 'success');
    else alert('✅ HITL 상태가 업데이트되었습니다.');
    
    loadPendingHitl();
  } catch (e) {
    if (typeof toast === 'function') toast('해결 실패: ' + e.message, 'error');
    else alert('해결 실패: ' + e.message);
  }
};

document.addEventListener('DOMContentLoaded', () => {
    const hitlTab = document.querySelector('.tab[data-tab="hitl"]');
    if (hitlTab) {
        hitlTab.addEventListener('click', () => {
            loadPendingHitl();
        });
    }
});