document.addEventListener("DOMContentLoaded", function () {
    const inputFotos = document.getElementById("fotos");
    const previewFotos = document.getElementById("preview-fotos");
    const areaUpload = document.getElementById("area-upload");

    let arquivosSelecionados = [];
    let indiceArrastado = null;

    function atualizarInput() {
        const dataTransfer = new DataTransfer();

        arquivosSelecionados.forEach(function (arquivo) {
            dataTransfer.items.add(arquivo);
        });

        inputFotos.files = dataTransfer.files;
    }

    function removerFoto(index) {
        arquivosSelecionados.splice(index, 1);
        atualizarInput();
        atualizarPreview();
    }

    function atualizarPreview() {
        previewFotos.innerHTML = "";

        arquivosSelecionados.forEach(function (arquivo, index) {
            const reader = new FileReader();

            reader.onload = function (event) {
                const item = document.createElement("div");

                item.className = "foto-preview";
                item.draggable = true;
                item.dataset.index = index;

                const imagem = document.createElement("img");
                imagem.src = event.target.result;
                imagem.alt = "Pré-visualização da foto";

                item.appendChild(imagem);

                if (index === 0) {
                    const principal = document.createElement("span");
                    principal.className = "foto-principal";
                    principal.textContent = "Principal";
                    item.appendChild(principal);
                }

                const botaoRemover = document.createElement("button");
                botaoRemover.type = "button";
                botaoRemover.className = "remover-foto";
                botaoRemover.textContent = "×";

                botaoRemover.addEventListener("click", function () {
                    removerFoto(index);
                });

                item.appendChild(botaoRemover);

                item.addEventListener("dragstart", function () {
                    indiceArrastado = index;
                    item.classList.add("arrastando");
                });

                item.addEventListener("dragend", function () {
                    indiceArrastado = null;
                    item.classList.remove("arrastando");
                });

                item.addEventListener("dragover", function (event) {
                    event.preventDefault();
                });

                item.addEventListener("drop", function (event) {
                    event.preventDefault();
                    event.stopPropagation();

                    if (
                        indiceArrastado === null ||
                        indiceArrastado === index
                    ) {
                        return;
                    }

                    const arquivoMovido =
                        arquivosSelecionados.splice(indiceArrastado, 1)[0];

                    arquivosSelecionados.splice(index, 0, arquivoMovido);

                    indiceArrastado = null;
                    atualizarInput();
                    atualizarPreview();
                });

                previewFotos.appendChild(item);
            };

            reader.readAsDataURL(arquivo);
        });
    }

    function adicionarArquivos(arquivos) {
        const imagens = Array.from(arquivos).filter(function (arquivo) {
            return ["image/jpeg", "image/png", "image/webp"]
                .includes(arquivo.type);
        });

        arquivosSelecionados.push(...imagens);

        atualizarInput();
        atualizarPreview();
    }

    inputFotos.addEventListener("change", function () {
        adicionarArquivos(this.files);
    });

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

        adicionarArquivos(event.dataTransfer.files);
    });
});
