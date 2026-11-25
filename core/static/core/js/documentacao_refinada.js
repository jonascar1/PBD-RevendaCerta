document.querySelectorAll('[data-doc-stage]').forEach(form => {
    const select = form.querySelector('[data-doc-status]');
    select.addEventListener('change', () => {
        form.requestSubmit();
    });
});
