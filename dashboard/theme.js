/**
 * Mories — Theme Toggle Script
 * Include in every page: <script src="/theme.js"></script>
 * Injects the toggle button and handles localStorage persistence.
 */
(function() {
  const STORAGE_KEY = 'mories-theme';

  // Apply saved or system preference
  function getPreferred() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return saved;
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    const btn = document.getElementById('mories-theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
  }

  function toggle() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  }

  // Apply immediately (before DOMContentLoaded to prevent flash)
  applyTheme(getPreferred());

  // Inject button after DOM loaded
  document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('mories-theme-toggle')) return;
    const btn = document.createElement('button');
    btn.id = 'mories-theme-toggle';
    btn.className = 'theme-toggle';
    btn.title = '다크/라이트 모드 전환';
    btn.setAttribute('aria-label', 'Toggle theme');
    btn.textContent = getPreferred() === 'dark' ? '☀️' : '🌙';
    btn.addEventListener('click', toggle);
    document.body.appendChild(btn);
  });
})();
