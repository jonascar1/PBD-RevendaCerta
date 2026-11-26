(() => {
    let timer;
    function notify() {
        let toast = document.getElementById('rc-demo-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'rc-demo-toast';
            toast.setAttribute('role', 'status');
            toast.innerHTML = '<strong>Modo demonstração</strong><span>Alterações nos registros estão desativadas neste ambiente.</span>';
            document.body.append(toast);
        }
        toast.hidden = false;
        clearTimeout(timer);
        timer = setTimeout(() => { toast.hidden = true; }, 4500);
    }
    document.addEventListener('submit', event => {
        const form = event.target;
        const method = (event.submitter?.getAttribute('formmethod') || form.method || 'get').toLowerCase();
        const url = new URL(event.submitter?.getAttribute('formaction') || form.action || location.href, location.href);
        if (method === 'get' || (url.origin === location.origin && ['/demo/perfil/', '/accounts/logout/'].includes(url.pathname))) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        notify();
    }, true);
    const originalFetch = window.fetch;
    window.fetch = async function (...args) {
        const response = await originalFetch.apply(this, args);
        if (response.headers.get('X-RC-Demo-Blocked') === '1') notify();
        return response;
    };
})();
