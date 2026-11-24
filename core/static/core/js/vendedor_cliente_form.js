/* ---------- Alternar PF / PJ ---------- */
const selectTipo = document.getElementById(document.querySelector("[data-carteira-tipo-id]").dataset.carteiraTipoId);
const secoesTipo = document.querySelectorAll("[data-tipo]");

function atualizarTipo() {
    secoesTipo.forEach(function (secao) {
        secao.hidden = secao.dataset.tipo !== selectTipo.value;
    });
}
selectTipo.addEventListener("change", atualizarTipo);
atualizarTipo();

/* ---------- Telefones dinâmicos ---------- */
const container = document.getElementById("telefones-container");
const molde = document.getElementById("telefone-empty-form");
const totalForms = document.querySelector('input[name$="-TOTAL_FORMS"]');

function ligarRemocao(linha) {
    linha.querySelector("[data-remove-row]").addEventListener("click", function () {
        const checkbox = linha.querySelector('input[type="checkbox"][name$="-DELETE"]');
        if (checkbox) checkbox.checked = true;
        linha.hidden = true;
    });
}

container.querySelectorAll("[data-form-row]").forEach(ligarRemocao);

document.getElementById("btn-add-telefone").addEventListener("click", function () {
    const indice = parseInt(totalForms.value, 10);
    const html = molde.innerHTML.replace(/__prefix__/g, indice);

    const wrapper = document.createElement("div");
    wrapper.innerHTML = html.trim();
    const linha = wrapper.firstElementChild;

    container.appendChild(linha);
    ligarRemocao(linha);
    totalForms.value = indice + 1;
    lucide.createIcons();
});
