(function () {
  const search = document.getElementById('search');
  const chips = document.querySelectorAll('#chips .chip');
  const rows = document.querySelectorAll('.roster .row');

  let activeFilter = 'all';

  function applyFilters() {
    const q = (search.value || '').trim().toLowerCase();
    rows.forEach((row) => {
      const matchesStatus = activeFilter === 'all' || row.dataset.status === activeFilter;
      const matchesQuery =
        !q || row.dataset.name.includes(q) || row.dataset.domain.includes(q);
      row.hidden = !(matchesStatus && matchesQuery);
    });
  }

  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      chips.forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.filter;
      applyFilters();
    });
  });

  if (search) {
    search.addEventListener('input', applyFilters);
  }
})();
