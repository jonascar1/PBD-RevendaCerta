document.addEventListener('DOMContentLoaded', () => { const search = document.querySelector('[data-vehicle-search]'); if (search) {
    const norm = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const list = document.querySelector('[data-vehicles]');
    const cars = [...list.querySelectorAll('.ao-choice')];
    const filters = [...document.querySelectorAll('[data-filter]')];
    const order = document.querySelector('[data-order]');
    const panel = document.getElementById('ao-filters');
    const toggle = document.querySelector('.ao-filter-toggle');
    filters.forEach(f => { const values = [...new Set(cars.map(a => a.dataset[f.dataset.filter]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR')); values.forEach(v => f.add(new Option(v, v))); });
    function update() { let count = 0; cars.slice().sort((a, b) => (order.value === 'desc' ? -1 : 1) * a.textContent.trim().localeCompare(b.textContent.trim(), 'pt-BR')).forEach(a => { a.hidden = !(norm(a.textContent).includes(norm(search.value.trim())) && filters.every(f => !f.value || a.dataset[f.dataset.filter] === f.value)); if (!a.hidden)
        count++; list.append(a); }); document.querySelector('[data-results]').textContent = count ? `${count} veículo(s) encontrado(s)` : 'Nenhum veículo encontrado.'; const n = filters.filter(f => f.value).length; toggle.textContent = n ? `Filtros (${n})` : 'Filtros'; }
    toggle.addEventListener('click', () => { panel.hidden = !panel.hidden; toggle.setAttribute('aria-expanded', String(!panel.hidden)); });
    search.addEventListener('input', update);
    [...filters, order].forEach(f => f.addEventListener('change', update));
    document.querySelector('[data-clear-filters]').addEventListener('click', () => { filters.forEach(f => f.value = ''); order.value = 'asc'; search.value = ''; update(); });
    update();
} document.querySelectorAll('[data-checklist]').forEach(form => { const boxes = [...form.querySelectorAll('input[type=checkbox]')]; const update = () => { const n = boxes.filter(b => b.checked).length; form.querySelector('[data-count]').textContent = `${n}/${boxes.length} itens conferidos`; form.querySelector('button[type=submit]').disabled = n !== boxes.length; }; form.addEventListener('change', update); update(); }); });
