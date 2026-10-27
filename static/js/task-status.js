const switcher = document.getElementById('status-switch');

if (switcher) {
  const error = document.getElementById('status-error');
  const buttons = switcher.querySelectorAll('button');

  switcher.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-status]');
    if (!button || button.disabled || button.getAttribute('aria-pressed') === 'true') return;

    buttons.forEach((item) => { item.disabled = true; });
    error.classList.add('hidden');
    try {
      const response = await fetch(switcher.dataset.url, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': switcher.dataset.csrf },
        body: JSON.stringify({ status: button.dataset.status }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      window.location.reload();
    } catch (failure) {
      buttons.forEach((item) => { item.disabled = false; });
      error.classList.remove('hidden');
    }
  });
}