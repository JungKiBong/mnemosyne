/**
 * Mories — Unified Navigation Component (Sidebar Layout)
 *
 * Usage:
 *   1. Include nav-component.css in <head>
 *   2. Include this script before </body>
 *   3. Add <div id="mories-nav"></div> where the sidebar should render
 *
 * Options (data-attributes on #mories-nav):
 *   data-active  — current page key (e.g. "dashboard", "graph", "memory", ...)
 *   data-status  — "true" to show status pills
 */
(function () {
  'use strict';

  /* ── I18n Translations ── */
  const I18N = {
    'ko': {
      'General': '일반', 'Dashboard': '대시보드',
      'Analytics & Memory': '분석 및 기억', 'Graph Explorer': '지식 그래프', 'Memory': '메모리 관리', 'Synaptic': '시냅틱 네트워크', 'Audit Trail': '감사 이력',
      'System & Rules': '시스템 및 규칙', 'Terminology': '용어 사전', 'Maturity': '성숙도', 'Workflows': '워크플로우', 'Harness': '하네스 (오케스트레이션)',
      'Developer': '개발자', 'API Explorer': 'API 탐색기', 'Guide': '운영 가이드'
    },
    'en': {
      'General': 'General', 'Dashboard': 'Dashboard',
      'Analytics & Memory': 'Analytics & Memory', 'Graph Explorer': 'Graph Explorer', 'Memory': 'Memory', 'Synaptic': 'Synaptic', 'Audit Trail': 'Audit Trail',
      'System & Rules': 'System & Rules', 'Terminology': 'Terminology', 'Maturity': 'Maturity', 'Workflows': 'Workflows', 'Harness': 'Harness (Orchestration)',
      'Developer': 'Developer', 'API Explorer': 'API Explorer', 'Guide': 'Guide'
    }
  };

  /* ── Categorized Navigation Links ── */
  const NAV_GROUPS = [
    {
      titleKey: 'General',
      items: [
        { key: 'dashboard',  labelKey: 'Dashboard',       href: '/', icon: '⊞' }
      ]
    },
    {
      titleKey: 'Analytics & Memory',
      items: [
        { key: 'graph',      labelKey: 'Graph Explorer',  href: '/graph',      icon: '❂' },
        { key: 'memory',     labelKey: 'Memory',          href: '/memory',     icon: '◉' },
        { key: 'synaptic',   labelKey: 'Synaptic',        href: '/synaptic',   icon: '⚯' },
        { key: 'history',    labelKey: 'Audit Trail',     href: '/memory_history', icon: '◴' }
      ]
    },
    {
      titleKey: 'System & Rules',
      items: [
        { key: 'terminology',labelKey: 'Terminology',     href: '/terminology', icon: '☰' },
        { key: 'maturity',   labelKey: 'Maturity',        href: '/maturity',    icon: '▤' },
        { key: 'workflows',  labelKey: 'Workflows',       href: '/workflows',   icon: '⧉' },
        { key: 'harness',    labelKey: 'Harness',         href: '/harness',     icon: '♞' }
      ]
    },
    {
      titleKey: 'Developer',
      items: [
        { key: 'api-docs',   labelKey: 'API Explorer',    href: '/api-docs',    icon: '⚡' },
        { key: 'guide',      labelKey: 'Guide',           href: '/guide',       icon: '📖' }
      ]
    }
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
      '/synaptic':        'synaptic',
      '/maturity':        'maturity',
      '/memory_history':  'history',
      '/api-docs':        'api-docs',
      '/workflows':       'workflows',
      '/harness':         'harness',
      '/harness.html':    'harness',
      '/guide':           'guide',
    };
    return map[path] || '';
  }

  /* ── Toggle Theme & Language ── */
  window.toggleMoriesTheme = function() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('moriesTheme', next);
  };

  /* ── Toggle Sidebar Collapse ── */
  window.toggleMoriesSidebar = function() {
    const sidebar = document.querySelector('.mories-sidebar');
    if (!sidebar) return;
    const isCollapsed = sidebar.classList.toggle('collapsed');
    document.body.classList.toggle('mories-sidebar-collapsed', isCollapsed);
    localStorage.setItem('moriesSidebarCollapsed', isCollapsed ? '1' : '0');
  };
  
  window.toggleMoriesLang = function(lang) {
    localStorage.setItem('moriesLang', lang);
    document.documentElement.setAttribute('lang', lang);
    window.dispatchEvent(new Event('moriesLangChanged'));
    const container = document.getElementById('mories-nav');
    if (container) render(container);
  };

  /* ── Restore Theme & Language ── */
  const savedTheme = localStorage.getItem('moriesTheme');
  if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
  }
  const currentLang = localStorage.getItem('moriesLang') || 'ko';
  document.documentElement.setAttribute('lang', currentLang);

  /* ── Build the sidebar HTML ── */
  function render(container) {
    document.body.classList.add('mories-has-sidebar');
    const activeKey = container.dataset.active || detectActivePage();
    const showStatus = container.dataset.status === 'true';
    const lang = localStorage.getItem('moriesLang') || 'ko';
    const t = I18N[lang];

    // Build grouped links
    const navHTML = NAV_GROUPS.map(group => {
      const linksHTML = group.items.map(item => {
        const isActive = item.key === activeKey;
        const cls = isActive
          ? 'mories-sidebar__link mories-sidebar__link--active'
          : 'mories-sidebar__link';
        return `
          <a class="${cls}" href="${item.href}" data-tooltip="${t[item.labelKey]}">
            <span class="mories-sidebar__icon">${item.icon}</span>
            <span class="mories-sidebar__label">${t[item.labelKey]}</span>
          </a>
        `;
      }).join('');
      return `
        <div class="mories-sidebar__group">
          <div class="mories-sidebar__group-title">${t[group.titleKey]}</div>
          ${linksHTML}
        </div>
      `;
    }).join('');

    // Status pills (only on dashboard)
    const statusHTML = showStatus ? `
      <div class="mories-sidebar__status-area">
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

    const isCollapsed = localStorage.getItem('moriesSidebarCollapsed') === '1';
    const collapsedClass = isCollapsed ? ' collapsed' : '';

    container.innerHTML = `
      <aside class="mories-sidebar${collapsedClass}" role="navigation" aria-label="Main navigation">
        <div class="mories-sidebar__header">
          <a class="mories-sidebar__brand" href="/">
            <div class="mories-sidebar__logo">M</div>
            <div class="mories-sidebar__brand-text">
              <span class="mories-sidebar__title">Mories</span>
              <span class="mories-sidebar__version">v0.4.0</span>
            </div>
          </a>
          <div class="mories-sidebar__header-actions" style="display: flex; gap: 8px;">
            <button class="mories-sidebar__theme-toggle" onclick="toggleMoriesLang(localStorage.getItem('moriesLang') === 'ko' ? 'en' : 'ko')" aria-label="Toggle Language" style="font-size: 13px; font-weight: bold; width: auto; padding: 0 6px;">
              ${lang === 'ko' ? '🇰🇷' : '🇺🇸'}
            </button>
            <button class="mories-sidebar__theme-toggle" onclick="toggleMoriesTheme()" aria-label="Toggle Theme">◐</button>
            <button class="mories-sidebar__collapse-btn" onclick="toggleMoriesSidebar()" aria-label="Toggle Sidebar" title="${isCollapsed ? 'Expand' : 'Collapse'}">«</button>
          </div>
        </div>

        <nav class="mories-sidebar__nav">
          ${navHTML}
        </nav>

        <div class="mories-sidebar__footer">
          ${statusHTML}
        </div>
      </aside>
      
      <!-- Mobile Toggle -->
      <button class="mories-sidebar-mobile-toggle" onclick="document.querySelector('.mories-sidebar').classList.toggle('open')" aria-label="Toggle Menu">
        ☰
      </button>
    `;
  }

  /* ── Initialize ── */
  function init() {
    const container = document.getElementById('mories-nav');
    if (!container) return;
    
    // Apply collapsed body class immediately to prevent layout flash
    if (localStorage.getItem('moriesSidebarCollapsed') === '1') {
      document.body.classList.add('mories-sidebar-collapsed');
    }
    
    render(container);
  }

  // Run on DOMContentLoaded or immediately if already loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
