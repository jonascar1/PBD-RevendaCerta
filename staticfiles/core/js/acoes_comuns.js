// Ações reutilizadas nos templates, sem JavaScript inline.
document.querySelectorAll("[data-auto-submit]").forEach((campo) => {
    campo.addEventListener("change", () => campo.form?.submit());
});
document.querySelectorAll("form[data-confirmacao]").forEach((formulario) => {
    formulario.addEventListener("submit", (evento) => {
        if (!window.confirm(formulario.dataset.confirmacao)) evento.preventDefault();
    });
});
document.querySelectorAll("[data-confirmacao-clique]").forEach((elemento) => {
    elemento.addEventListener("click", (evento) => {
        if (!window.confirm(elemento.dataset.confirmacaoClique)) evento.preventDefault();
    });
});
document.querySelectorAll("[data-imprimir]").forEach((botao) => {
    botao.addEventListener("click", () => window.print());
});
