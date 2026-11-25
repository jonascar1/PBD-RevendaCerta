const origens = document.querySelectorAll('input[name="origem"]');
const campoCusto = document.getElementById("campo-custo");
const custoAquisicao = document.getElementById("custo_aquisicao");
const campoRepasse = document.getElementById("campo-repasse");
const valorRepasse = document.getElementById("valor_repasse");
function atualizarOrigem() {
    const origemSelecionada = document.querySelector('input[name="origem"]:checked');
    if (!origemSelecionada) {
        return;
    }
    const origem = origemSelecionada.value;
    if (origem === "CONSIGNADO") {
        // Consignado não possui custo de aquisição
        custoAquisicao.disabled = false;
        campoCusto.classList.add("campo-desabilitado");
        // No consignado, o repasse é obrigatório
        valorRepasse.disabled = false;
        campoRepasse.classList.remove("campo-desabilitado");
    }
    else {
        // Comprado ou troca precisam de custo
        custoAquisicao.disabled = false;
        campoCusto.classList.remove("campo-desabilitado");
        // Repasse não é necessário nesses casos
        valorRepasse.disabled = false;
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

                ${index === 0 &&
                document.querySelectorAll(".foto-existente:not([style*='display: none'])").length === 0
                ? '<span class="foto-principal">Principal</span>'
                : ''}

                <button
                    type="button"
                    class="remover-foto"
                >
                    ×
                </button>
            `;
            const botaoRemover = item.querySelector(".remover-foto");
            botaoRemover.addEventListener("click", function () {
                const indiceAtual = Array.from(previewFotos.children)
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
                const indiceDestino = Array.from(previewFotos.children)
                    .indexOf(item);
                if (indiceArrastado === null ||
                    indiceArrastado === indiceDestino) {
                    return;
                }
                const arquivoMovido = arquivosSelecionados[indiceArrastado];
                arquivosSelecionados.splice(indiceArrastado, 1);
                arquivosSelecionados.splice(indiceDestino, 0, arquivoMovido);
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
// As exclusões só são aplicadas quando o formulário é salvo.
const galeriaExistente = document.getElementById("fotos-existentes-container");
const fotosExcluir = document.getElementById("fotos-excluir");
const ordemFotos = document.getElementById("ordem-fotos");
const fotoPrincipalInput = document.getElementById("foto-principal");
function fotosAtivas() {
    return galeriaExistente
        ? [...galeriaExistente.querySelectorAll(".foto-existente:not(.pendente-exclusao)")]
        : [];
}
function fixarPrincipalNoInicio() {
    if (!galeriaExistente || !fotoPrincipalInput)
        return;
    const principal = fotosAtivas().find(foto => foto.dataset.fotoId === fotoPrincipalInput.value);
    if (principal && galeriaExistente.firstElementChild !== principal) {
        galeriaExistente.insertBefore(principal, galeriaExistente.firstElementChild);
    }
}
function atualizarGaleriaExistente() {
    const ativas = fotosAtivas();
    if (!ativas.some(foto => foto.dataset.fotoId === fotoPrincipalInput.value)) {
        fotoPrincipalInput.value = ativas[0]?.dataset.fotoId || "";
    }
    fixarPrincipalNoInicio();
    const fotos = fotosAtivas();
    const ids = fotos.map(foto => foto.dataset.fotoId);
    ordemFotos.value = ids.join(",");
    fotosExcluir.value = galeriaExistente
        ? [...galeriaExistente.querySelectorAll(".foto-existente.pendente-exclusao")]
            .map(foto => foto.dataset.fotoId).join(",")
        : "";
    if (!ids.includes(fotoPrincipalInput.value)) {
        fotoPrincipalInput.value = ids[0] || "";
    }
    if (galeriaExistente) {
        galeriaExistente.querySelectorAll(".foto-existente").forEach(foto => {
            const principal = !foto.classList.contains("pendente-exclusao") &&
                foto.dataset.fotoId === fotoPrincipalInput.value;
            foto.classList.toggle("is-principal", principal);
            foto.draggable = !principal && !foto.classList.contains("pendente-exclusao");
            const estrela = foto.querySelector(".selecionar-principal");
            if (estrela) {
                estrela.setAttribute("aria-pressed", String(principal));
                estrela.title = principal ? "Imagem principal" : "Definir como imagem principal";
                estrela.setAttribute("aria-label", estrela.title);
                estrela.disabled = foto.classList.contains("pendente-exclusao");
            }
            const botao = foto.querySelector(".remover-foto-existente");
            if (botao) {
                const restaurar = foto.classList.contains("pendente-exclusao");
                botao.textContent = restaurar ? "✓" : "×";
                botao.title = restaurar ? "Restaurar imagem" : "Marcar para excluir";
                botao.setAttribute("aria-label", botao.title);
            }
        });
    }
}
if (galeriaExistente) {
    galeriaExistente.addEventListener("dragstart", function (event) {
        const foto = event.target.closest(".foto-existente");
        if (foto && foto.dataset.fotoId === fotoPrincipalInput.value) {
            event.preventDefault();
            event.stopImmediatePropagation();
        }
    }, true);
}
if (galeriaExistente) {
    const inicial = galeriaExistente.querySelector('.selecionar-principal[aria-pressed="true"]');
    if (inicial)
        fotoPrincipalInput.value = inicial.closest(".foto-existente").dataset.fotoId;
    galeriaExistente.addEventListener("click", event => {
        const estrela = event.target.closest(".selecionar-principal");
        if (estrela && galeriaExistente.contains(estrela)) {
            event.preventDefault();
            const foto = estrela.closest(".foto-existente");
            if (!foto.classList.contains("pendente-exclusao")) {
                fotoPrincipalInput.value = foto.dataset.fotoId;
                galeriaExistente.prepend(foto);
                atualizarGaleriaExistente();
            }
            return;
        }
        const botao = event.target.closest(".remover-foto-existente");
        if (botao && galeriaExistente.contains(botao)) {
            event.preventDefault();
            botao.closest(".foto-existente").classList.toggle("pendente-exclusao");
            atualizarGaleriaExistente();
        }
    });
    atualizarGaleriaExistente();
}
// Reordenação das fotos já cadastradas (não interfere nos controles de estrela/exclusão).
if (galeriaExistente) {
    let fotoArrastada = null;
    galeriaExistente.addEventListener("dragstart", event => {
        if (event.target.closest("button")) {
            event.preventDefault();
            return;
        }
        const foto = event.target.closest(".foto-existente");
        if (!foto || foto.classList.contains("pendente-exclusao") || foto.dataset.fotoId === fotoPrincipalInput.value) {
            event.preventDefault();
            return;
        }
        fotoArrastada = foto;
        foto.classList.add("foto-arrastando");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", foto.dataset.fotoId);
    });
    galeriaExistente.addEventListener("dragover", event => {
        const destino = event.target.closest(".foto-existente");
        if (!fotoArrastada || !destino || destino.classList.contains("pendente-exclusao") || destino.dataset.fotoId === fotoPrincipalInput.value)
            return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
    });
    galeriaExistente.addEventListener("drop", event => {
        const destino = event.target.closest(".foto-existente");
        if (!fotoArrastada || !destino || destino === fotoArrastada || destino.classList.contains("pendente-exclusao") || destino.dataset.fotoId === fotoPrincipalInput.value)
            return;
        event.preventDefault();
        const elementos = [...galeriaExistente.children];
        const origem = elementos.indexOf(fotoArrastada);
        const alvo = elementos.indexOf(destino);
        if (origem < alvo)
            destino.after(fotoArrastada);
        else
            destino.before(fotoArrastada);
        atualizarGaleriaExistente();
    });
    galeriaExistente.addEventListener("dragend", () => {
        if (fotoArrastada)
            fotoArrastada.classList.remove("foto-arrastando");
        fotoArrastada = null;
    });
}
