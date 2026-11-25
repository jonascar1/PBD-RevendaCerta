/* Preferências de aparência independentes da autenticação. */
(() => {
    const root = document.documentElement;
    const scope = root.dataset.rcThemeScope;
    const media = matchMedia('(prefers-color-scheme: dark)');
    const PANEL = 'rc-panel-theme';
    const SITE = 'rc-site-tema';
    const valid = v => ['light', 'dark', 'system'].includes(v);
    const get = key => { try {
        return localStorage.getItem(key);
    }
    catch {
        return null;
    } };
    const set = (key, value) => { try {
        localStorage.setItem(key, value);
        return true;
    }
    catch {
        return false;
    } };
    const old = id => { try {
        return JSON.parse(get('rc-preferences-v1:' + id) || '{}').theme;
    }
    catch {
        return null;
    } };
    // A cookie is a fallback independent of Django's session cookie.
    const cookiePanel = () => document.cookie.split(';').map(x => x.trim()).find(x => x.startsWith('rc_panel_theme='))?.split('=')[1];
    const readPanel = () => { const v = get(PANEL); return valid(v) ? v : cookiePanel(); };
    const writePanel = value => {
        const ok = set(PANEL, value);
        try {
            document.cookie = 'rc_panel_theme=' + value + '; Path=/; Max-Age=31536000; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
        }
        catch { }
        return ok || cookiePanel() === value;
    };
    let panel = readPanel();
    if (!valid(panel) && scope === 'panel') {
        const previous = old(root.dataset.rcThemeUser);
        if (valid(previous)) {
            panel = previous;
            writePanel(panel);
        }
    }
    let site = get(SITE) === 'escuro' ? 'dark' : 'light';
    const isDark = theme => theme === 'dark' || (theme === 'system' && media.matches);
    function apply() {
        const theme = scope === 'site' ? site : valid(panel) ? panel : 'light';
        root.dataset.rcTheme = isDark(theme) ? 'dark' : 'light';
        if (scope === 'panel')
            document.body?.classList.toggle('rc-dark', isDark(theme));
        document.querySelectorAll('[data-rc-site-toggle]').forEach(button => {
            const dark = site === 'dark';
            button.setAttribute('aria-pressed', String(dark));
            const label = dark ? 'Mudar para o modo claro' : 'Mudar para o modo escuro';
            button.setAttribute('aria-label', label);
            button.title = label;
        });
    }
    window.RCTheme = {
        panel: () => valid(panel) ? panel : 'light',
        hasPanel: () => valid(panel),
        setPanel: theme => { if (!valid(theme))
            return false; panel = theme; const ok = writePanel(theme); apply(); return ok; },
        apply
    };
    if (valid(panel))
        writePanel(panel);
    apply();
    document.addEventListener('DOMContentLoaded', apply);
    document.addEventListener('click', event => {
        if (!event.target.closest('[data-rc-site-toggle]') || scope !== 'site')
            return;
        site = site === 'dark' ? 'light' : 'dark';
        set(SITE, site === 'dark' ? 'escuro' : 'claro');
        apply();
    });
    media.addEventListener('change', apply);
    addEventListener('storage', event => {
        if (event.key === SITE || event.key === null)
            site = get(SITE) === 'escuro' ? 'dark' : 'light';
        if (event.key === PANEL || event.key === null) {
            panel = readPanel();
            if (scope === 'panel')
                dispatchEvent(new Event('rc-panel-theme-change'));
        }
        apply();
    });
    addEventListener('pageshow', event => {
        if (!event.persisted)
            return;
        panel = readPanel();
        site = get(SITE) === 'escuro' ? 'dark' : 'light';
        if (scope === 'panel')
            dispatchEvent(new Event('rc-panel-theme-change'));
        apply();
    });
})();
