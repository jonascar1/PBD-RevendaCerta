document.addEventListener('DOMContentLoaded', () => {
    // Sincronização secundária de aliases para garantir retrocompatibilidade
    const syncText = (srcId, targetId) => {
        const src = document.getElementById(srcId);
        const target = document.getElementById(targetId);
        if (src && target) {
            const observer = new MutationObserver(() => target.textContent = src.textContent);
            observer.observe(src, { childList: true, characterData: true, subtree: true });
        }
    };
    syncText('resumo-valor-oferecido', 'resumo-valor-oferecido-composicao');
});
