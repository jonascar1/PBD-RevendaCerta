document.addEventListener("DOMContentLoaded", function () {
    const carrossel = document.getElementById("carrossel-veiculos");
    if (!carrossel)
        return;
    const janela = carrossel.querySelector(".janela-veiculos");
    const trilho = carrossel.querySelector(".trilho-veiculos");
    const anterior = carrossel.querySelector(".anterior");
    const proximo = carrossel.querySelector(".proximo");
    if (!janela || !trilho || !anterior || !proximo)
        return;
    let cards = Array.from(trilho.querySelectorAll(".card-veiculo"));
    let indice = 0;
    let proximaPagina = carrossel.dataset.proximaPagina || "";
    let carregando = false;
    const status = document.getElementById("vitrine-carregamento");
    async function carregarMais() {
        if (!proximaPagina || carregando) return;
        carregando = true;
        if (status) status.textContent = "Carregando mais veículos…";
        try {
            const url = new URL(window.location.href);
            url.searchParams.set("pagina", proximaPagina);
            url.searchParams.set("fragmento", "1");
            const resposta = await fetch(url, {credentials: "same-origin"});
            if (!resposta.ok) throw new Error("Falha ao carregar veículos");
            const doc = new DOMParser().parseFromString(await resposta.text(), "text/html");
            const lote = doc.querySelector("[data-lote-veiculos]");
            if (!lote) throw new Error("Resposta inválida");
            const novosCards = Array.from(lote.querySelectorAll(".card-veiculo"));
            trilho.append(...novosCards);
            if (typeof inserirLogo === "function") {
                novosCards.forEach(card => {
                    card.querySelectorAll(".etiqueta-marca[data-marca]").forEach(el => {
                        if (!el.querySelector(".logo-fabricante")) inserirLogo(el, el.dataset.marca);
                    });
                });
            }
            cards = Array.from(trilho.querySelectorAll(".card-veiculo"));
            proximaPagina = lote.dataset.proximaPagina || "";
            if (window.lucide) window.lucide.createIcons();
            if (status) status.textContent = "";
        } catch (erro) {
            if (status) status.textContent = "Não foi possível carregar mais veículos. Avance para tentar novamente.";
        } finally {
            carregando = false;
            atualizar();
        }
    }
    // Precisa bater com os breakpoints do CSS: 5 / 4 / 2 cards
    function quantidadeVisivel() {
        if (window.matchMedia("(max-width: 680px)").matches)
            return 2;
        if (window.matchMedia("(max-width: 1100px)").matches)
            return 3;
        return 4;
    }
    function maxIndice() {
        return Math.max(0, cards.length - quantidadeVisivel());
    }
    function atualizar() {
        indice = Math.min(indice, maxIndice());
        if (cards.length) {
            const gap = parseFloat(getComputedStyle(trilho).gap) || 0;
            const passo = cards[0].offsetWidth + gap;
            trilho.style.transform = "translateX(" + (-indice * passo) + "px)";
        }
        anterior.disabled = indice === 0;
        proximo.disabled = indice >= maxIndice() && (!proximaPagina || carregando);
    }
    async function ir(direcao) {
        if (direcao > 0 && indice >= maxIndice() && proximaPagina) await carregarMais();
        const novo = Math.min(Math.max(indice + direcao, 0), maxIndice());
        if (novo !== indice) {
            indice = novo;
            atualizar();
        }
        if (direcao > 0 && indice >= maxIndice() - 2 && proximaPagina) carregarMais();
    }
    anterior.addEventListener("click", function () { ir(-1); });
    proximo.addEventListener("click", function () { ir(1); });
    /* ---------- Deslizar com o dedo ---------- */
    let inicioX = 0;
    let inicioY = 0;
    let deslizou = false;
    janela.addEventListener("touchstart", function (e) {
        inicioX = e.touches[0].clientX;
        inicioY = e.touches[0].clientY;
        deslizou = false;
    }, { passive: true });
    janela.addEventListener("touchend", function (e) {
        const dx = e.changedTouches[0].clientX - inicioX;
        const dy = e.changedTouches[0].clientY - inicioY;
        // só conta se foi mais horizontal que vertical e passou de 40px
        if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
            deslizou = true;
            ir(dx < 0 ? 1 : -1);
        }
    }, { passive: true });
    // evita abrir um link sem querer ao terminar de deslizar
    janela.addEventListener("click", function (e) {
        if (deslizou) {
            e.preventDefault();
            e.stopPropagation();
            deslizou = false;
        }
    }, true);
    window.addEventListener("resize", atualizar);
    atualizar();
});
