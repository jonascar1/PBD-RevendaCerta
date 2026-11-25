const form = document.getElementById('al-form');
const all = document.getElementById('al-all');
const boxes = [...form.querySelectorAll('[name="veiculos"]')];
function update() { const n = boxes.filter(b => b.checked).length; document.getElementById('al-count').textContent = `${n} de ${boxes.length} selecionados`; all.checked = n > 0 && n === boxes.length; all.indeterminate = n > 0 && n < boxes.length; }
all.addEventListener('change', () => { boxes.forEach(b => b.checked = all.checked); update(); });
boxes.forEach(b => b.addEventListener('change', update));
form.addEventListener('submit', e => { const n = boxes.filter(b => b.checked).length; if (!n || !confirm(`Aplicar a nova alçada a ${n} veículo(s)?`))
    e.preventDefault(); });
update();
