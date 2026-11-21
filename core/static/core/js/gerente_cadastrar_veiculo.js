const origens = document.querySelectorAll('input[name="origem"]');

const campoCusto = document.getElementById("campo-custo");
const custoAquisicao = document.getElementById("custo_aquisicao");

const campoRepasse = document.getElementById("campo-repasse");
const valorRepasse = document.getElementById("valor_repasse");

function atualizarOrigem() {

    const origemSelecionada = document.querySelector(
        'input[name="origem"]:checked'
    );

    if (!origemSelecionada) {
        return;
    }

    const origem = origemSelecionada.value;

    if (origem === "CONSIGNADO") {

        // Consignado não possui custo de aquisição
        custoAquisicao.value = "0,00";
        custoAquisicao.disabled = true;

        campoCusto.classList.add("campo-desabilitado");

        // No consignado, o repasse é obrigatório
        valorRepasse.disabled = false;

        campoRepasse.classList.remove("campo-desabilitado");

    } else {

        // Comprado ou troca precisam de custo
        custoAquisicao.disabled = false;

        campoCusto.classList.remove("campo-desabilitado");

        // Repasse não é necessário nesses casos
        valorRepasse.value = "";
        valorRepasse.disabled = true;

        campoRepasse.classList.add("campo-desabilitado");
    }
}


origens.forEach(function (origem) {
    origem.addEventListener("change", atualizarOrigem);
});


atualizarOrigem();

const inputFotos = document.getElementById("fotos");
const previewFotos = document.getElementById("preview-fotos");

let arquivosSelecionados = [];
let indiceArrastado = null;

const areaUpload = document.getElementById("area-upload");

areaUpload.addEventListener("dragover", function (event) {
    event.preventDefault();
    areaUpload.classList.add("arrastando-arquivos");
});

areaUpload.addEventListener("dragleave", function () {
    areaUpload.classList.remove("arrastando-arquivos");
});

areaUpload.addEventListener("drop", function (event) {
    event.preventDefault();

    areaUpload.classList.remove("arrastando-arquivos");

    const arquivos = Array.from(event.dataTransfer.files);

    const imagens = arquivos.filter(function (arquivo) {
        return arquivo.type.startsWith("image/");
    });

    arquivosSelecionados = [
        ...arquivosSelecionados,
        ...imagens
    ];

    atualizarInput();
    atualizarPreview();
});


inputFotos.addEventListener("change", function () {

    const novosArquivos = Array.from(this.files);

    arquivosSelecionados = [
        ...arquivosSelecionados,
        ...novosArquivos
    ];

    atualizarInput();
    atualizarPreview();
});


function atualizarPreview() {

    previewFotos.innerHTML = "";

    arquivosSelecionados.forEach((arquivo, index) => {

        const reader = new FileReader();

        reader.onload = function (e) {

            const item = document.createElement("div");

            item.className = "foto-preview";
            item.draggable = true;

            item.innerHTML = `
                <img
                    src="${e.target.result}"
                    alt="Pré-visualização da foto"
                >

                ${index === 0
                    ? '<span class="foto-principal">Principal</span>'
                    : ''
                }

                <button
                    type="button"
                    class="remover-foto"
                >
                    ×
                </button>
            `;


            const botaoRemover =
                item.querySelector(".remover-foto");

            botaoRemover.addEventListener("click", function () {

                const indiceAtual =
                    Array.from(previewFotos.children)
                    .indexOf(item);

                removerFoto(indiceAtual);
            });


            item.addEventListener("dragstart", function () {

                indiceArrastado =
                    Array.from(previewFotos.children)
                    .indexOf(item);

                item.classList.add("arrastando");
            });


            item.addEventListener("dragend", function () {

                item.classList.remove("arrastando");

                indiceArrastado = null;
            });


            item.addEventListener("dragover", function (event) {

                event.preventDefault();
            });


            item.addEventListener("drop", function (event) {

                event.preventDefault();

                const indiceDestino =
                    Array.from(previewFotos.children)
                    .indexOf(item);

                if (
                    indiceArrastado === null ||
                    indiceArrastado === indiceDestino
                ) {
                    return;
                }


                const arquivoMovido =
                    arquivosSelecionados[indiceArrastado];


                arquivosSelecionados.splice(
                    indiceArrastado,
                    1
                );


                arquivosSelecionados.splice(
                    indiceDestino,
                    0,
                    arquivoMovido
                );


                atualizarInput();
                atualizarPreview();
            });


            previewFotos.appendChild(item);
        };


        reader.readAsDataURL(arquivo);
    });
}


function removerFoto(index) {

    arquivosSelecionados.splice(index, 1);

    atualizarInput();
    atualizarPreview();
}


function atualizarInput() {

    const dataTransfer = new DataTransfer();

    arquivosSelecionados.forEach(function (arquivo) {

        dataTransfer.items.add(arquivo);
    });

    inputFotos.files = dataTransfer.files;
}
