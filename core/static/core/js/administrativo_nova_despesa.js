document.addEventListener('DOMContentLoaded', () => {
    const dialog = document.getElementById('dialog-nova-despesa');
    const open = document.getElementById('abrir-nova-despesa');
    const select = document.getElementById('veiculo-nova-despesa');
    const close = () => dialog?.close();
    open?.addEventListener('click', (event) => { event.preventDefault(); dialog?.showModal(); });
    document.getElementById('fechar-nova-despesa')?.addEventListener('click', close);
    document.getElementById('cancelar-nova-despesa')?.addEventListener('click', close);
    document.getElementById('continuar-nova-despesa')?.addEventListener('click', () => {
        if (!select?.value) {
            select?.focus();
            return;
        }
        window.location.assign(select.value);
    });
});
