
window.lucide?.createIcons();

document.addEventListener("DOMContentLoaded", function () {
    const abrir = document.getElementById("abrir-menu");
    const fechar = document.getElementById("fechar-menu");
    const drawer = document.getElementById("drawer-menu");
    const overlay = document.getElementById("drawer-overlay");

    if (!abrir || !fechar || !drawer || !overlay) return;

    function abrirDrawer() {
        document.body.classList.add("menu-aberto");
        drawer.inert = false;
        drawer.setAttribute("aria-hidden", "false");
        abrir.setAttribute("aria-expanded", "true");
        fechar.focus();
    }

    function fecharDrawer() {
        document.body.classList.remove("menu-aberto");
        drawer.inert = true;
        drawer.setAttribute("aria-hidden", "true");
        abrir.setAttribute("aria-expanded", "false");
        abrir.focus();
    }

    abrir.addEventListener("click", abrirDrawer);
    fechar.addEventListener("click", fecharDrawer);
    overlay.addEventListener("click", fecharDrawer);

    drawer.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", function () {
            document.body.classList.remove("menu-aberto");
            drawer.inert = true;
            drawer.setAttribute("aria-hidden", "true");
            abrir.setAttribute("aria-expanded", "false");
        });
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && document.body.classList.contains("menu-aberto")) {
            fecharDrawer();
        }
    });
});

document.addEventListener("DOMContentLoaded", () => { const numero = (document.body.dataset.whatsappNumero || "").replace(/\D/g, ""); if (!/^55\d{10,11}$/.test(numero)) return; document.querySelectorAll("[data-whatsapp]").forEach(a => { const texto = a.dataset.whatsapp === "vender" ? "Olá! Vim pelo site Revenda Certa e gostaria de vender ou trocar meu veículo." : "Olá! Vim pelo site Revenda Certa e gostaria de mais informações."; a.href = `https://wa.me/${numero}?text=${encodeURIComponent(texto)}`; a.target="_blank"; a.rel="noopener noreferrer"; }); });

// Entrada suave das seções, sem interferir nos carrosséis.
document.addEventListener("DOMContentLoaded", () => {
    if (!("IntersectionObserver" in window) || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver(entries => {
        entries.forEach(({target, isIntersecting}) => {
            if (!isIntersecting) return;
            target.classList.remove("reveal-pendente");
            observer.unobserve(target);
        });
    }, {threshold: 0.08});
    const elementos = document.querySelectorAll(".estoque-cabecalho, .filtros, .carrossel-veiculos, .titulo-centralizado, .etapas .etapa, .vender-painel, .contato-conteudo, .explorar-resultados, .explorar-grade .card-veiculo, .relacionados h2, .relacionados .card-veiculo");
    elementos.forEach((el, i) => {
        el.classList.add("reveal-elemento", "reveal-pendente");
        el.style.setProperty("--reveal-delay", `${(i % 4) * 65}ms`);
        observer.observe(el);
    });
});
