(() => { const p = document.querySelector('#loginForm input[type=password]'), b = document.getElementById('togglePassword'); function icons() { window.lucide?.createIcons(); } if (p && b) {
    b.addEventListener('click', () => { const show = p.type === 'password'; p.type = show ? 'text' : 'password'; b.setAttribute('aria-pressed', String(show)); b.setAttribute('aria-label', show ? 'Ocultar senha' : 'Mostrar senha'); b.innerHTML = window.lucide ? `<i data-lucide="${show ? 'eye-off' : 'eye'}"></i>` : (show ? 'Ocultar' : 'Mostrar'); icons(); });
    if (!window.lucide)
        b.textContent = 'Mostrar';
} icons(); })();

// Revalida o formulário restaurado pelo histórico do navegador.
window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
        window.location.reload();
    }
});
