const board = document.getElementById('board');
const errorBox = document.getElementById('board-error');

if (board) {
  const csrf = board.dataset.csrf;
  const canMove = board.dataset.canMove === 'true';
  let errorTimer;

  function updateCounts() {
    board.querySelectorAll('[data-count-for]').forEach((badge) => {
      const list = board.querySelector(`[data-column="${badge.dataset.countFor}"]`);
      badge.textContent = list.children.length;
    });
  }

  function syncSelect(card) {
    const select = card.querySelector('[data-move-select]');
    if (select) select.value = card.parentElement.dataset.column;
  }

  function showError() {
    errorBox.classList.remove('hidden');
    clearTimeout(errorTimer);
    errorTimer = setTimeout(() => errorBox.classList.add('hidden'), 4000);
  }

  // Guarda el nuevo estado; si falla, deshace el movimiento con rollback()
  async function persist(card, rollback) {
    const status = card.parentElement.dataset.column;
    syncSelect(card);
    updateCounts();
    try {
      const response = await fetch(card.dataset.moveUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    } catch (error) {
      rollback();
      syncSelect(card);
      updateCounts();
      showError();
    }
  }

  // Arrastrar y soltar
  board.querySelectorAll('[data-column]').forEach((list) => {
    new Sortable(list, {
      group: 'tasks',
      animation: 150,
      ghostClass: 'opacity-40',
      disabled: !canMove,
      delay: 150,
      delayOnTouchOnly: true, // en pantallas táctiles, mantener pulsado para arrastrar
      onEnd: (event) => {
        if (event.from === event.to) return;
        persist(event.item, () => {
          event.from.insertBefore(event.item, event.from.children[event.oldIndex] ?? null);
        });
      },
    });
  });

  // Alternativa sin arrastre: el selector de cada tarjeta
  board.querySelectorAll('[data-move-select]').forEach((select) => {
    select.addEventListener('change', () => {
      const card = select.closest('[data-task]');
      const from = card.parentElement;
      const next = card.nextElementSibling;
      board.querySelector(`[data-column="${select.value}"]`).appendChild(card);
      persist(card, () => from.insertBefore(card, next));
    });
  });
}