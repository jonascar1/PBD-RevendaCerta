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

const radiosAlcada = document.querySelectorAll(
    'input[name="tipo_alcada"]'
);

const labelAlcada = document.getElementById(
    "label-valor-alcada"
);

const sufixoAlcada = document.getElementById(
    "alcada-sufixo"
);

const ajudaAlcada = document.getElementById(
    "ajuda-alcada"
);

function atualizarAlcada(valor) {

        if (valor === "VALOR") {

            labelAlcada.textContent =
                "Limite de desconto (R$)";

            sufixoAlcada.textContent = "R$";

            ajudaAlcada.textContent =
                "Valor máximo de desconto sem aprovação.";

        } else {

            labelAlcada.textContent =
                "Limite de desconto (%)";

            sufixoAlcada.textContent = "%";

            ajudaAlcada.textContent =
                "Percentual máximo de desconto sem aprovação.";
        }

    }

radiosAlcada.forEach(function(radio) {
    radio.addEventListener("change", function() {
        atualizarAlcada(this.value);
    });
});

const marcado = document.querySelector('input[name="tipo_alcada"]:checked');
if (marcado) {
    atualizarAlcada(marcado.value);
}

document.querySelectorAll("[data-mostrar-senha]").forEach((botao) => {
    botao.addEventListener("click", () => mostrarSenha(botao.dataset.mostrarSenha, botao));
});
