// dashboard/assets/js/app.js

// ========== TAB SWITCHING ==========
const tabs = document.querySelectorAll('.tab');
const tabContents = document.querySelectorAll('.tab-content');
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    tabs.forEach(t => t.classList.remove('active'));
    tabContents.forEach(tc => tc.classList.remove('active'));
    tab.classList.add('active');
    const target = document.getElementById(`tab-${tab.dataset.tab}`);
    if (target) {
        target.classList.add('active');
    }
  });
});

// ========== DEMO DATA ==========
const AGENTS_DEMO = [
  { name: 'Alice Chen', id: 'agent_001', color: '#4a7dff',
    traits: ['tech-savvy', 'analytical', 'detail-oriented'],
    dynamic: 'Currently frustrated with Bob\'s stance on climate policy. Leaning towards posting a rebuttal.',
    memories: 47, interactions: 128 },
  { name: 'Bob Park', id: 'agent_002', color: '#8b5cf6',
    traits: ['outgoing', 'conservative', 'sports fan'],
    dynamic: 'Enjoying a streak of popular posts. Considering following more tech influencers.',
    memories: 35, interactions: 96 },
  { name: 'Carol Kim', id: 'agent_003', color: '#ec4899',
    traits: ['creative', 'empathetic', 'bookworm'],
    dynamic: 'Mediating between Alice and Bob. Feeling exhausted from social conflicts.',
    memories: 52, interactions: 142 },
  { name: 'David Lee', id: 'agent_004', color: '#f97316',
    traits: ['pragmatic', 'quiet', 'data-driven'],
    dynamic: 'Observing the Alice-Bob debate from the sidelines. Collecting data for analysis.',
    memories: 23, interactions: 58 },
  { name: 'Eve Tanaka', id: 'agent_005', color: '#22c55e',
    traits: ['extroverted', 'progressive', 'foodie'],
    dynamic: 'Actively engaging with multiple threads. Planning a collaborative post with Carol.',
    memories: 41, interactions: 115 },
  { name: 'Frank Wu', id: 'agent_006', color: '#06b6d4',
    traits: ['skeptical', 'methodical', 'gamer'],
    dynamic: 'Recently muted two noisy accounts. Searching for niche interest communities.',
    memories: 29, interactions: 72 },
];

const TIMELINE_DEMO = [
  { time: 'R12', type: 'social', agent: 'Carol Kim', text: 'Expressed concern about escalating tension between Alice and Bob. Sent private message to both.' },
  { time: 'R12', type: 'event', agent: 'Alice Chen', text: 'Quote-posted Bob\'s climate article with a detailed 3-point rebuttal. Post received 24 likes.' },
  { time: 'R11', type: 'personal', agent: 'Eve Tanaka', text: 'Shows consistent preference for food-related content. 73% of liked posts are food/recipe topics.' },
  { time: 'R11', type: 'social', agent: 'Bob Park', text: 'Followed 3 new tech influencers after Alice\'s recommendation. Sentiment towards Alice shifted +0.2.' },
  { time: 'R10', type: 'event', agent: 'David Lee', text: 'Performed 8 search queries in a single round — unusual spike. Topics: AI regulation, market data.' },
  { time: 'R10', type: 'personal', agent: 'Frank Wu', text: 'Mute behavior pattern detected: mutes users after 3+ negative interactions. Threshold identified.' },
  { time: 'R09', type: 'social', agent: 'Alice Chen', text: 'Strong alliance forming with Carol. 85% positive interaction rate over last 5 rounds.' },
  { time: 'R09', type: 'event', agent: 'Eve Tanaka', text: 'Created a collaborative thread with Carol about weekend cooking. First cross-agent content creation.' },
];

// ========== RENDER FUNCTIONS ==========
function renderTimeline() {
  const container = document.getElementById('timeline-list');
  if(!container) return;
  container.innerHTML = TIMELINE_DEMO.map(item => `
    <div class="timeline-item">
      <div class="timeline-time">${item.time}</div>
      <div class="timeline-dot-col">
        <div class="timeline-dot ${item.type}"></div>
      </div>
      <div class="timeline-content">
        <div class="timeline-agent">${item.agent}</div>
        <div class="timeline-text">${item.text}</div>
        <span class="timeline-tag ${item.type}">${item.type}</span>
      </div>
    </div>
  `).join('');
}

function renderAgents() {
  const grid = document.getElementById('agents-grid');
  if(!grid) return;
  grid.innerHTML = AGENTS_DEMO.map(agent => `
    <div class="agent-card">
      <div class="agent-card-header">
        <div class="agent-avatar" style="background:${agent.color}">
          ${agent.name.charAt(0)}
        </div>
        <div>
          <div class="agent-name">${agent.name}</div>
          <div class="agent-id">${agent.id}</div>
        </div>
      </div>
      <div class="agent-traits">
        ${agent.traits.map(t => `<span class="trait-tag">${t}</span>`).join('')}
      </div>
      <div class="agent-dynamic">${agent.dynamic}</div>
      <div class="agent-stats">
        <div class="agent-stat"><strong>${agent.memories}</strong>memories</div>
        <div class="agent-stat"><strong>${agent.interactions}</strong>interactions</div>
      </div>
    </div>
  `).join('');
}

function updateStats() {
  const statAgents = document.getElementById('stat-agents');
  if(statAgents) statAgents.textContent = AGENTS_DEMO.length;
  
  const totalMem = AGENTS_DEMO.reduce((s, a) => s + a.memories, 0);
  const memEl = document.getElementById('stat-memories');
  if(memEl) memEl.textContent = totalMem;
  
  const memRateEl = document.getElementById('stat-memories-rate');
  if(memRateEl) memRateEl.textContent = `+${Math.floor(totalMem / 12)}/round avg`;
  
  const nodeEl = document.getElementById('stat-nodes');
  if(nodeEl) nodeEl.textContent = '1,247'; // Default value, will be overridden by status.js polling
  
  const latencyEl = document.getElementById('stat-latency');
  if(latencyEl) latencyEl.textContent = '48ms';
}

// ========== INIT ==========
window.addEventListener('DOMContentLoaded', () => {
    renderTimeline();
    renderAgents();
    updateStats();
});