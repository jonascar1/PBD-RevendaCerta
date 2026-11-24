document.addEventListener("DOMContentLoaded", function () {
    const banner = document.querySelector(".banner, .banner-carrossel, #banner-carrossel");
    if (!banner) return;

    const slides = Array.from(
        banner.querySelectorAll(".banner-slide, .slide-banner, .carrossel-banner-item")
    );
    if (slides.length <= 1) return;

    const btnAnterior = banner.querySelector(".banner-anterior, .seta-banner.anterior, [data-banner-prev]");
    const btnProximo = banner.querySelector(".banner-proximo, .seta-banner.proximo, [data-banner-next]");
    const indicadores = Array.from(
        banner.querySelectorAll(".banner-indicador, .banner-dot, [data-banner-slide]")
    );

    let indiceAtual = slides.findIndex((slide) => slide.classList.contains("ativo"));
    if (indiceAtual < 0) indiceAtual = 0;

    const INTERVALO_MS = 5000;
    let timer = null;

    function mostrarSlide(novoIndice) {
        indiceAtual = (novoIndice + slides.length) % slides.length;

        slides.forEach((slide, i) => {
            const ativo = i === indiceAtual;
            slide.classList.toggle("ativo", ativo);
            slide.setAttribute("aria-hidden", ativo ? "false" : "true");
        });

        indicadores.forEach((dot, i) => {
            const ativo = i === indiceAtual;
            dot.classList.toggle("ativo", ativo);
            dot.setAttribute("aria-current", ativo ? "true" : "false");
        });
    }

    function iniciarAutoPlay() {
        pararAutoPlay();
        timer = setInterval(() => {
            mostrarSlide(indiceAtual + 1);
        }, INTERVALO_MS);
    }

    function pararAutoPlay() {
        if (timer) {
            clearInterval(timer);
            timer = null;
        }
    }

    if (btnAnterior) {
        btnAnterior.addEventListener("click", () => {
            mostrarSlide(indiceAtual - 1);
            iniciarAutoPlay();
        });
    }

    if (btnProximo) {
        btnProximo.addEventListener("click", () => {
            mostrarSlide(indiceAtual + 1);
            iniciarAutoPlay();
        });
    }

    indicadores.forEach((dot, i) => {
        dot.addEventListener("click", () => {
            const alvo = dot.dataset.bannerSlide !== undefined
                ? Number(dot.dataset.bannerSlide)
                : i;
            mostrarSlide(alvo);
            iniciarAutoPlay();
        });
    });

    // Pausa quando o usuário passa o mouse ou foca dentro do banner
    banner.addEventListener("mouseenter", pararAutoPlay);
    banner.addEventListener("mouseleave", iniciarAutoPlay);
    banner.addEventListener("focusin", pararAutoPlay);
    banner.addEventListener("focusout", iniciarAutoPlay);

    // Suporte a deslizar (swipe) no celular
    let toqueInicioX = 0;
    banner.addEventListener("touchstart", (e) => {
        toqueInicioX = e.changedTouches[0].clientX;
        pararAutoPlay();
    }, { passive: true });

    banner.addEventListener("touchend", (e) => {
        const deltaX = e.changedTouches[0].clientX - toqueInicioX;
        if (Math.abs(deltaX) > 40) {
            mostrarSlide(deltaX < 0 ? indiceAtual + 1 : indiceAtual - 1);
        }
        iniciarAutoPlay();
    }, { passive: true });

    mostrarSlide(indiceAtual);
    iniciarAutoPlay();
});