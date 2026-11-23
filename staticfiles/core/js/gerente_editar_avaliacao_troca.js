document.addEventListener("DOMContentLoaded", function () {
        const inputFotos = document.getElementById("fotos");
        const previewFotos = document.getElementById("preview-fotos");
        const areaUpload = document.getElementById("area-upload");
        const fotosRemovidasInput = document.getElementById("fotos-removidas");
        const fotosRemovidas = [];

        document.querySelectorAll(".remover-foto-existente").forEach(function (botao) {
            botao.addEventListener("click", function () {
                const foto = botao.closest(".foto-existente");
                const fotoId = foto.dataset.fotoId;

                if (!fotosRemovidas.includes(fotoId)) {
                    fotosRemovidas.push(fotoId);
                }

                fotosRemovidasInput.value = JSON.stringify(fotosRemovidas);

                foto.remove();
                atualizarOrdemFotosExistentes();
            });
        });

        // Reordenação das fotos já cadastradas
        const ordemFotosInput = document.getElementById("ordem-fotos-existentes");

        const listaFotosExistentes = document.querySelector(
            ".fotos-existentes .preview-fotos"
        );

        let fotoExistenteArrastada = null;

        function atualizarOrdemFotosExistentes() {
            if (!listaFotosExistentes || !ordemFotosInput) {
                return;
            }

            const fotos = Array.from(
                listaFotosExistentes.querySelectorAll(".foto-existente")
            );

            const ids = fotos.map(function (foto) {
                return foto.dataset.fotoId;
            });

            ordemFotosInput.value = JSON.stringify(ids);

            // Atualiza a indicação da foto principal
            fotos.forEach(function (foto, index) {
                const etiqueta = foto.querySelector(".foto-principal");

                if (etiqueta) {
                    etiqueta.remove();
                }

                if (index === 0) {
                    const principal = document.createElement("span");
                    principal.className = "foto-principal";
                    principal.textContent = "Principal";
                    foto.appendChild(principal);
                }
            });
        }

        if (listaFotosExistentes) {
            listaFotosExistentes.querySelectorAll(".foto-existente").forEach(
                function (foto) {

                    foto.addEventListener("dragstart", function () {
                        fotoExistenteArrastada = foto;
                        foto.classList.add("arrastando");
                    });

                    foto.addEventListener("dragend", function () {
                        foto.classList.remove("arrastando");
                        fotoExistenteArrastada = null;
                    });

                    foto.addEventListener("dragover", function (event) {
                        event.preventDefault();
                    });

                    foto.addEventListener("drop", function (event) {
                        event.preventDefault();
                        event.stopPropagation();

                        if (
                            !fotoExistenteArrastada ||
                            fotoExistenteArrastada === foto
                        ) {
                            return;
                        }

                        const elementos = Array.from(
                            listaFotosExistentes.querySelectorAll(".foto-existente")
                        );

                        const origem = elementos.indexOf(fotoExistenteArrastada);
                        const destino = elementos.indexOf(foto);

                        if (origem < destino) {
                            foto.after(fotoExistenteArrastada);
                        } else {
                            foto.before(fotoExistenteArrastada);
                        }

                        atualizarOrdemFotosExistentes();
                    });
                }
            );
        }

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
                const item = document.createElement("div");
                item.className = "foto-preview";
                item.draggable = true;

                const imagem = document.createElement("img");
                imagem.alt = "Pré-visualização da foto";
                item.appendChild(imagem);

                const reader = new FileReader();

                reader.onload = function (event) {
                    imagem.src = event.target.result;
                };

                reader.readAsDataURL(arquivo);

                if (index === 0) {
                    const principal = document.createElement("span");
                    principal.className = "foto-principal";
                    principal.textContent = "Primeira nova foto";
                    item.appendChild(principal);
                }

                const botaoRemover = document.createElement("button");
                botaoRemover.type = "button";
                botaoRemover.className = "remover-foto";
                botaoRemover.textContent = "×";
                botaoRemover.setAttribute("aria-label", "Remover foto");

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
