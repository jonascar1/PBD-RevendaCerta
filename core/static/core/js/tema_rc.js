/* Tema único para vitrine, login e painéis. */
(() => {
    const root = document.documentElement;
    const media = matchMedia('(prefers-color-scheme: dark)');
    const key = 'rc-panel-theme';
    const valid = v => ['light', 'dark', 'system'].includes(v);
    const get = k => { try { return localStorage.getItem(k); } catch { return null; } };
    const cookie = () => document.cookie.split(';').map(x => x.trim()).find(x => x.startsWith('rc_panel_theme='))?.split('=')[1];
    const read = () => [cookie(), get(key), get('rc-site-tema') === 'escuro' ? 'dark' : get('rc-site-tema') === 'claro' ? 'light' : null].find(valid);
    let theme = read();
    function write(v) {
        theme = v;
        let ok = false;
        try { localStorage.setItem(key, v); ok = true; } catch {}
        try { document.cookie = 'rc_panel_theme=' + v + '; Path=/; Max-Age=31536000; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : ''); } catch {}
        return ok || cookie() === v;
    }
    const url = new URL(location.href);
    const incoming = url.searchParams.get('rc_theme');
    if (valid(incoming)) {
        write(incoming);
        url.searchParams.delete('rc_theme');
        history.replaceState(history.state, '', url);
    }
    const dark = () => theme === 'dark' || (theme === 'system' && media.matches);
    function apply() {
        root.dataset.rcTheme = dark() ? 'dark' : 'light';
        if (root.dataset.rcThemeScope === 'panel') document.body?.classList.toggle('rc-dark', dark());
        document.querySelectorAll('[data-rc-site-toggle]').forEach(b => {
            const label = dark() ? 'Mudar para o modo claro' : 'Mudar para o modo escuro';
            b.setAttribute('aria-pressed', String(dark())); b.setAttribute('aria-label', label); b.title = label;
        });
        document.querySelectorAll('a[data-rc-theme-transfer]').forEach(a => {
            const target = new URL(a.href, location.href);
            target.searchParams.set('rc_theme', theme || 'light'); a.href = target.href;
        });
    }
    function refresh() { theme = read(); apply(); dispatchEvent(new Event('rc-panel-theme-change')); }
    window.RCTheme = {panel: () => theme || 'light', hasPanel: () => valid(theme), setPanel: v => { if (!valid(v)) return false; const ok = write(v); apply(); return ok; }, apply};
    apply();
    document.addEventListener('DOMContentLoaded', apply);
    document.addEventListener('click', e => { if (e.target.closest('[data-rc-site-toggle]')) { write(dark() ? 'light' : 'dark'); apply(); } });
    media.addEventListener('change', apply);
    addEventListener('storage', e => { if (e.key === key || e.key === null) refresh(); });
    addEventListener('pageshow', refresh);
    addEventListener('focus', refresh);
})();
