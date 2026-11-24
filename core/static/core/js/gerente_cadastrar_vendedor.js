function mostrarSenha(id, botao) {
    const campo = document.getElementById(id);

    if (campo.type === "password") {
        campo.type = "text";
        botao.textContent = "Ocultar";
    } else {
        campo.type = "password";
        botao.textContent = "Mostrar";
    }
}

document.querySelectorAll("[data-mostrar-senha]").forEach((botao) => {
    botao.addEventListener("click", () => mostrarSenha(botao.dataset.mostrarSenha, botao));
});
