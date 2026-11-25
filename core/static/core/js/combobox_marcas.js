function inserirLogo(el, marca) {
    const img = document.createElement("img");
    img.className = "logo-fabricante";
    img.alt = "";
    img.src = "/static/core/img/marcas/" + marca.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-") + ".svg";
    img.addEventListener("error", () => img.remove());
    el.prepend(img);
}
document.addEventListener("DOMContentLoaded", () => document.querySelectorAll(".etiqueta-marca").forEach(el => inserirLogo(el, el.dataset.marca)));
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('select[data-combobox]').forEach(select => {
        const raiz = document.createElement("div");
        raiz.className = "combo-raiz";
        select.parentNode.insertBefore(raiz, select);
        raiz.appendChild(select);
        const gatilho = document.createElement("button");
        gatilho.type = "button";
        gatilho.className = "combo-gatilho";
        gatilho.setAttribute("aria-haspopup", "listbox");
        gatilho.setAttribute("aria-expanded", "false");
        const menu = document.createElement("div");
        menu.className = "combo-menu";
        menu.hidden = true;
        const pesquisa = document.createElement("input");
        pesquisa.type = "search";
        pesquisa.className = "combo-pesquisa";
        pesquisa.placeholder = "Pesquisar...";
        pesquisa.setAttribute("aria-label", "Pesquisar opção");
        const opcoes = document.createElement("div");
        opcoes.className = "combo-opcoes";
        opcoes.setAttribute("role", "listbox");
        opcoes.setAttribute("aria-label", "Opções disponíveis");
        menu.append(pesquisa, opcoes);
        raiz.append(gatilho, menu);
        select.tabIndex = -1;
        gatilho.setAttribute("aria-label", select.labels[0]?.textContent.trim() || "Selecionar opção");
        const valores = Array.from(select.options).map(o => ({ valor: o.value, texto: o.textContent.trim() }));
        const atualizar = () => { gatilho.textContent = select.selectedOptions[0]?.textContent.trim() || "Todas as marcas"; gatilho.insertAdjacentHTML("beforeend", '<span aria-hidden="true">⌄</span>'); };
        const fechar = () => { menu.hidden = true; gatilho.setAttribute("aria-expanded", "false"); };
        const abrir = () => { menu.hidden = false; gatilho.setAttribute("aria-expanded", "true"); pesquisa.value = ""; desenhar(); pesquisa.focus(); };
        const desenhar = () => {
            opcoes.replaceChildren();
            const termo = pesquisa.value.toLocaleLowerCase("pt-BR");
            const filtradas = valores.filter(o => o.texto.toLocaleLowerCase("pt-BR").includes(termo));
            filtradas.forEach(o => {
                const botao = document.createElement("button");
                botao.type = "button";
                botao.className = "combo-opcao";
                botao.setAttribute("role", "option");
                botao.setAttribute("aria-selected", String(select.value === o.valor));
                botao.textContent = o.texto;
                if (select.dataset.combobox === "marca" && o.valor)
                    inserirLogo(botao, o.valor);
                botao.addEventListener("click", () => { select.value = o.valor; select.dispatchEvent(new Event("change", { bubbles: true })); atualizar(); fechar(); gatilho.focus(); });
                opcoes.appendChild(botao);
            });
            if (!filtradas.length) {
                const vazio = document.createElement("p");
                vazio.className = "combo-vazio";
                vazio.textContent = "Nenhuma opção encontrada";
                opcoes.appendChild(vazio);
            }
        };
        gatilho.addEventListener("click", () => menu.hidden ? abrir() : fechar());
        pesquisa.addEventListener("input", desenhar);
        pesquisa.addEventListener("keydown", e => {
            if (e.key === "Escape") {
                fechar();
                gatilho.focus();
            }
            if (e.key === "ArrowDown") {
                e.preventDefault();
                opcoes.querySelector("button")?.focus();
            }
            if (e.key === "Enter") {
                e.preventDefault();
                opcoes.querySelector("button")?.click();
            }
        });
        opcoes.addEventListener("keydown", e => {
            const botoes = Array.from(opcoes.querySelectorAll("button"));
            const indice = botoes.indexOf(document.activeElement);
            if (e.key === "ArrowDown") {
                e.preventDefault();
                botoes[Math.min(indice + 1, botoes.length - 1)]?.focus();
            }
            if (e.key === "ArrowUp") {
                e.preventDefault();
                if (indice === 0)
                    pesquisa.focus();
                else
                    botoes[indice - 1]?.focus();
            }
            if (e.key === "Escape") {
                fechar();
                gatilho.focus();
            }
        });
        document.addEventListener("pointerdown", e => { if (!raiz.contains(e.target))
            fechar(); });
        raiz.addEventListener("focusout", e => { if (!raiz.contains(e.relatedTarget))
            fechar(); });
        atualizar();
    });
});
