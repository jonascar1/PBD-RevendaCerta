lucide.createIcons();

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
