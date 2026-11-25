(() => {
    const b = document.body, q = s => document.querySelector(s);
    const toggle = q('.rc-mobile-toggle'), back = q('.rc-mobile-backdrop'), side = q('#rc-sidebar');
    function menu(open) { b.classList.toggle('rc-menu-open', open); toggle?.setAttribute('aria-expanded', String(open)); if (back)
        back.hidden = !open; if (open)
        side?.querySelector('a')?.focus();
    else
        toggle?.focus(); }
    toggle?.addEventListener('click', () => menu(!b.classList.contains('rc-menu-open')));
    back?.addEventListener('click', () => menu(false));
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && b.classList.contains('rc-menu-open'))
        menu(false); });
    matchMedia('(max-width:900px)').addEventListener('change', e => { if (!e.matches && b.classList.contains('rc-menu-open'))
        menu(false); });
})();
