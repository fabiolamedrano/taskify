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

document.querySelectorAll('select[data-autosubmit]').forEach((select) => {
  select.addEventListener('change', () => select.form.requestSubmit());
});

// Menú de usuario (<details data-menu>): se cierra al pulsar fuera o con Esc
document.addEventListener('click', (event) => {
  document.querySelectorAll('details[data-menu][open]').forEach((menu) => {
    if (!menu.contains(event.target)) menu.removeAttribute('open');
  });
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  document.querySelectorAll('details[data-menu][open]').forEach((menu) => menu.removeAttribute('open'));
});