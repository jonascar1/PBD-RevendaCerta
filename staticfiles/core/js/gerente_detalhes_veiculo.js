function trocarFoto(url, elemento) {

    const fotoPrincipal = document.getElementById("foto-principal");

    if (fotoPrincipal) {
        fotoPrincipal.src = url;
    }

    document.querySelectorAll(".miniatura").forEach(function(miniatura) {
        miniatura.classList.remove("ativa");
    });

    elemento.classList.add("ativa");
}

// Galeria: substitui o antigo onclick inline.
document.querySelectorAll("[data-foto-url]").forEach((elemento) => {
    elemento.addEventListener("click", () => trocarFoto(elemento.dataset.fotoUrl, elemento));
});
