// --- Avisos (toasts) ---
function dismissToast(toast) {
  toast.style.opacity = '0';
  setTimeout(() => toast.remove(), 200);
}

document.querySelectorAll('[data-toast]').forEach((toast) => {
  toast.querySelector('[data-toast-close]')?.addEventListener('click', () => dismissToast(toast));
  if (!('persist' in toast.dataset)) {
    setTimeout(() => dismissToast(toast), 5000);
  }
});

// --- Confirmaciones ---
const dialog = document.getElementById('confirm-dialog');

if (dialog) {
  const title = document.getElementById('confirm-title');
  const message = document.getElementById('confirm-message');
  const accept = document.getElementById('confirm-accept');
  let pendingForm = null;

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.confirm) return;

    if (form.dataset.confirmed === 'true') {
      delete form.dataset.confirmed;
      return;
    }

    event.preventDefault();
    pendingForm = form;
    title.textContent = form.dataset.confirmTitle || '¿Estás seguro?';
    message.textContent = form.dataset.confirm;
    accept.textContent = form.dataset.confirmButton || 'Confirmar';
    dialog.dataset.tone = form.dataset.confirmTone || 'default';
    dialog.returnValue = '';
    dialog.showModal();
    document.body.classList.add('overflow-hidden');
  });

  dialog.addEventListener('close', () => {
    document.body.classList.remove('overflow-hidden');
    const form = pendingForm;
    pendingForm = null;
    if (dialog.returnValue === 'confirm' && form) {
      form.dataset.confirmed = 'true';
      form.requestSubmit();
    }
  });

  // Clic en el fondo oscuro cierra el modal
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });
}