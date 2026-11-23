/**
 * Alterna a visibilidade do campo de senha na tela de autenticação.
 */
(function () {
    "use strict";

    const passwordInput = document.getElementById("password");
    const togglePassword = document.getElementById("togglePassword");

    if (!passwordInput || !togglePassword) return;

    togglePassword.addEventListener("click", function () {
        const oculto = passwordInput.type === "password";

        passwordInput.type = oculto ? "text" : "password";
        togglePassword.textContent = oculto ? "Ocultar" : "Mostrar";
        togglePassword.setAttribute("aria-pressed", String(oculto));
    });
})();