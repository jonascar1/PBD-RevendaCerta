document.addEventListener("DOMContentLoaded", function () {
        const carrossel = document.getElementById("carrossel-veiculos");
        if (!carrossel) return;

        const janela = carrossel.querySelector(".janela-veiculos");
        const trilho = carrossel.querySelector(".trilho-veiculos");
        const anterior = carrossel.querySelector(".anterior");
        const proximo = carrossel.querySelector(".proximo");

        if (!janela || !trilho || !anterior || !proximo) return;

        const cards = Array.from(trilho.querySelectorAll(".card-veiculo"));
        let indice = 0;

        // Precisa bater com os breakpoints do CSS: 5 / 4 / 2 cards
        function quantidadeVisivel() {
            if (window.matchMedia("(max-width: 680px)").matches) return 2;
            if (window.matchMedia("(max-width: 1100px)").matches) return 4;
            return 5;
        }

        function maxIndice() {
            return Math.max(0, cards.length - quantidadeVisivel());
        }

        function atualizar() {
            indice = Math.min(indice, maxIndice());

            if (cards.length) {
                const gap = parseFloat(getComputedStyle(trilho).gap) || 0;
                const passo = cards[0].getBoundingClientRect().width + gap;
                trilho.style.transform = "translateX(" + (-indice * passo) + "px)";
            }

            anterior.disabled = indice === 0;
            proximo.disabled = indice >= maxIndice();
        }

        function ir(direcao) {
            const novo = Math.min(Math.max(indice + direcao, 0), maxIndice());
            if (novo !== indice) {
                indice = novo;
                atualizar();
            }
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
