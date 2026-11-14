(() => {
  const room = document.getElementById('room-select');
  const cabinet = document.getElementById('cabinet-select');
  const shelf = document.getElementById('shelf-select');

  function filterOptions(select, dataAttribute, selectedParent) {
    if (!select) return;
    const selected = select.value;
    for (const option of select.options) {
      if (!option.value || !option.dataset[dataAttribute]) {
        option.hidden = false;
        continue;
      }
      option.hidden = !selectedParent || option.dataset[dataAttribute] !== selectedParent;
    }
    const chosen = select.selectedOptions[0];
    if (chosen && chosen.hidden) select.value = '0';
    select.disabled = !selectedParent;
  }

  function syncLocation() {
    if (cabinet) filterOptions(cabinet, 'roomId', room?.value && room.value !== '0' ? room.value : '');
    if (shelf) filterOptions(shelf, 'cabinetId', cabinet?.value && cabinet.value !== '0' ? cabinet.value : '');
  }
  room?.addEventListener('change', syncLocation);
  cabinet?.addEventListener('change', syncLocation);
  if (room || cabinet || shelf) syncLocation();

  const kind = document.getElementById('location-kind');
  const roomParent = document.getElementById('room-parent');
  const cabinetParent = document.getElementById('cabinet-parent');
  function syncSettingsParents() {
    if (!kind) return;
    const isShelf = kind.value === 'shelf';
    if (roomParent) roomParent.hidden = isShelf;
    if (cabinetParent) cabinetParent.hidden = !isShelf;
  }
  kind?.addEventListener('change', syncSettingsParents);
  syncSettingsParents();

  // Keep unsaved book-form fields while visiting the online metadata lookup.
  const bookForm = document.getElementById('book-entry-form');
  if (bookForm) {
    const draftKey = bookForm.dataset.draftKey;
    const saveDraft = () => {
      const draft = {};
      for (const field of bookForm.elements) {
        if (!field.name || field.type === 'file' || field.type === 'submit' || field.type === 'button') continue;
        if (field.type === 'checkbox' || field.type === 'radio') draft[field.name] = field.checked;
        else draft[field.name] = field.value;
      }
      try { sessionStorage.setItem(draftKey, JSON.stringify(draft)); } catch (_) { /* storage may be disabled */ }
    };
    try {
      const draft = JSON.parse(sessionStorage.getItem(draftKey) || 'null');
      if (draft) {
        for (const field of bookForm.elements) {
          if (!field.name || field.type === 'file' || !(field.name in draft)) continue;
          if (field.type === 'checkbox' || field.type === 'radio') field.checked = !!draft[field.name];
          else if (field.name !== 'allow_duplicate') field.value = draft[field.name];
        }
        syncLocation();
      }
    } catch (_) { /* ignore malformed session data */ }

    const lookupLink = document.getElementById('lookup-from-form');
    lookupLink?.addEventListener('click', (event) => {
      event.preventDefault();
      saveDraft();
      const isbn = bookForm.querySelector('[name="isbns"]')?.value.trim();
      const title = bookForm.querySelector('[name="title"]')?.value.trim();
      const query = isbn || title || '';
      const params = new URLSearchParams({ q: query, return_to: location.pathname });
      const targetId = Number(lookupLink.dataset.targetBookId || 0);
      if (targetId) params.set('target_book_id', String(targetId));
      location.href = `/lookup?${params.toString()}`;
    });

    bookForm.addEventListener('submit', async (event) => {
      saveDraft();
      if (bookForm.dataset.duplicateChecked === 'yes') return;
      const id = Number(bookForm.querySelector('[name="id"]')?.value || 0);
      if (id) return;
      const isbnValue = bookForm.querySelector('[name="isbns"]')?.value || '';
      if (!isbnValue.trim()) return;
      event.preventDefault();
      try {
        const response = await fetch(`/api/isbn-check?isbns=${encodeURIComponent(isbnValue)}`);
        const payload = await response.json();
        const duplicates = payload.duplicates || [];
        if (duplicates.length) {
          const details = duplicates.map(item => `${item.title} (${item.inventory_no})`).join('\n');
          const proceed = window.confirm(`OPOZORILO: ISBN že obstaja v domači knjižnici:\n\n${details}\n\nAli želiš vseeno dodati nov fizični izvod?`);
          if (!proceed) return;
          const allow = bookForm.querySelector('[name="allow_duplicate"]');
          if (allow) allow.value = '1';
        }
        bookForm.dataset.duplicateChecked = 'yes';
        bookForm.requestSubmit();
      } catch (error) {
        // Do not silently allow a possible duplicate when the check endpoint fails.
        window.alert('Preverjanje dvojnikov trenutno ni uspelo. Podatki so ohranjeni; poskusi ponovno, preden shraniš knjigo.');
      }
    });
  }

  // Clear a saved draft only after the server has successfully opened the book detail page.
  const draftClear = document.getElementById('clear-book-draft');
  if (draftClear?.dataset.key) {
    try {
      sessionStorage.removeItem(draftClear.dataset.key);
      if (draftClear.dataset.newKey) sessionStorage.removeItem(draftClear.dataset.newKey);
    } catch (_) { /* ignore */ }
  }

  // Autocomplete for reading titles: matching local books are suggestions, but any title is allowed.
  document.querySelectorAll('.book-autocomplete').forEach((input) => {
    const form = input.closest('form');
    const listId = input.getAttribute('list');
    const list = listId ? document.getElementById(listId) : null;
    const hidden = form?.querySelector('input[name="book_id"]');
    let timer = null;
    let lastOptions = [];
    input.addEventListener('input', () => {
      if (hidden) hidden.value = '0';
      clearTimeout(timer);
      const query = input.value.trim();
      if (query.length < 2 || !list) { if (list) list.replaceChildren(); return; }
      timer = setTimeout(async () => {
        try {
          const response = await fetch(`/api/books/suggest?q=${encodeURIComponent(query)}`);
          if (!response.ok) return;
          lastOptions = await response.json();
          list.replaceChildren();
          for (const item of lastOptions) {
            const option = document.createElement('option');
            option.value = item.label;
            option.dataset.bookId = item.id;
            list.appendChild(option);
          }
        } catch (_) { /* free-text entry remains available */ }
      }, 180);
    });
    input.addEventListener('change', () => {
      if (!hidden) return;
      const match = lastOptions.find(item => item.label === input.value);
      hidden.value = match ? String(match.id) : '0';
    });
  });
})();
