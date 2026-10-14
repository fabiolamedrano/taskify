const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('sidebar-overlay');
const toggle = document.getElementById('sidebar-toggle');

function setSidebar(open) {
  sidebar.dataset.open = open;
  overlay.dataset.open = open;
  toggle.setAttribute('aria-expanded', open);
}

if (sidebar && overlay && toggle) {
  toggle.addEventListener('click', () => {
    setSidebar(sidebar.dataset.open !== 'true');
  });
  overlay.addEventListener('click', () => setSidebar(false));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setSidebar(false);
  });
}