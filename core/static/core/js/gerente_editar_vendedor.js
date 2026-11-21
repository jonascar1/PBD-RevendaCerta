const radiosAlcada = document.querySelectorAll(
        'input[name="tipo_alcada"]'
    );

    const sufixoAlcada = document.getElementById(
        "sufixo-alcada"
    );

    const descricaoAlcada = document.getElementById(
        "descricao-alcada"
    );

    function atualizarAlcada() {

        const tipo = document.querySelector(
            'input[name="tipo_alcada"]:checked'
        ).value;

        if (tipo === "VALOR") {

            sufixoAlcada.textContent = "R$";

            descricaoAlcada.textContent =
                "Valor máximo de desconto que o vendedor pode oferecer sem aprovação.";

        } else {

            sufixoAlcada.textContent = "%";

            descricaoAlcada.textContent =
                "Percentual máximo de desconto que o vendedor pode oferecer sem aprovação.";
        }
    }

    radiosAlcada.forEach(radio => {
        radio.addEventListener("change", atualizarAlcada);
    });

    atualizarAlcada();
