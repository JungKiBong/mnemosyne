/**
 * Mories — Unified Navigation Component
 *
 * Usage:
 *   1. Include nav-component.css in <head>
 *   2. Include this script before </body>
 *   3. Add <div id="mories-nav"></div> where the topbar should render
 *
 * Options (data-attributes on #mories-nav):
 *   data-active  — current page key (e.g. "dashboard", "graph", "memory", ...)
 *   data-status  — "true" to show status pills (default false)
 */
(function () {
  'use strict';

  /* ── Canonical navigation links ── */
  const NAV_ITEMS = [
    { key: 'dashboard',  label: 'Dashboard',       href: '/' },
    { key: 'graph',      label: 'Graph Explorer',  href: '/graph' },
    { key: 'memory',     label: 'Memory',          href: '/memory' },
    { key: 'terminology',label: 'Terminology',     href: '/terminology' },
    { key: 'synaptic',   label: 'Synaptic',        href: '/memory/synaptic' },
    { key: 'maturity',   label: 'Maturity',        href: '/maturity' },
    { key: 'history',    label: 'Audit Trail',     href: '/memory/history' },
    { key: 'api',        label: 'API Explorer',    href: '/api-docs' },
    { key: 'workflows',  label: 'Workflows',       href: '/workflows' },
    { key: 'guide',      label: 'Guide',           href: '/guide' },
  ];

  /* ── Auto-detect current page from URL ── */
  function detectActivePage() {
    const path = window.location.pathname.replace(/\/+$/, '') || '/';
    const map = {
      '/':                'dashboard',
      '/dashboard':       'dashboard',
      '/graph':           'graph',
      '/memory':          'memory',
      '/terminology':     'terminology',
      '/memory/synaptic': 'synaptic',
      '/synaptic':        'synaptic',
      '/maturity':        'maturity',
      '/memory/history':  'history',
      '/api-docs':        'api',
      '/workflows':       'workflows',
      '/guide':           'guide',
    };
    return map[path] || '';
  }

  /* ── Build the topbar HTML ── */
  function render(container) {
    const activeKey = container.dataset.active || detectActivePage();
    const showStatus = container.dataset.status === 'true';

    // Build nav links
    const navLinks = NAV_ITEMS.map(item => {
      const cls = item.key === activeKey
        ? 'mories-topbar__link mories-topbar__link--active'
        : 'mories-topbar__link';
      return `<a class="${cls}" href="${item.href}">${item.label}</a>`;
    }).join('');

    // Status pills (only on dashboard)
    const statusHTML = showStatus ? `
      <div class="mories-topbar__status">
        <div class="mories-status-pill">
          <div class="mories-status-dot mories-status-dot--green" id="neo4j-status"></div>
          Neo4j
        </div>
        <div class="mories-status-pill">
          <div class="mories-status-dot" id="sm-status"></div>
          Supermemory
        </div>
        <div class="mories-status-pill">
          <div class="mories-status-dot" id="observer-status"></div>
          Observers
        </div>
      </div>` : '';

    container.innerHTML = `
      <header class="mories-topbar" role="navigation" aria-label="Main navigation">
        <a class="mories-topbar__brand" href="/">
          <div class="mories-topbar__logo">M</div>
          <span class="mories-topbar__title">Mories</span>
          <span class="mories-topbar__version">v0.4.0</span>
        </a>

        <button class="mories-topbar__burger" aria-label="Toggle navigation" onclick="this.nextElementSibling.classList.toggle('open')">☰</button>

        <nav class="mories-topbar__nav">
          ${navLinks}
        </nav>

        ${statusHTML}
      </header>
    `;
  }

  /* ── Initialize ── */
  function init() {
    const container = document.getElementById('mories-nav');
    if (!container) return;
    render(container);
  }

  // Run on DOMContentLoaded or immediately if already loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
