(() => {
    const b = document.body;
    if (!b.dataset.prefUser)
        return;
    const key = 'rc-preferences-v1:' + b.dataset.prefUser;
    let p = { theme: 'light', size: 'normal', name: '', photo: '' };
    try {
        Object.assign(p, JSON.parse(localStorage.getItem(key) || '{}'));
    }
    catch { }
    if (window.RCTheme) {
        if (!window.RCTheme.hasPanel() && ['light', 'dark', 'system'].includes(p.theme))
            window.RCTheme.setPanel(p.theme);
        p.theme = window.RCTheme.panel();
    }
    const q = s => document.querySelector(s), qa = s => document.querySelectorAll(s), media = matchMedia('(prefers-color-scheme: dark)'), status = q('#rc-pref-status');
    const name = q('.sidebar .perfil strong'), original = name?.textContent.trim(), avatar = q('.sidebar .perfil :is(.avatar,.perfil-icon,.perfil-avatar)'), initial = avatar?.textContent.trim();
    function drawAvatar(el, fallback) { if (!el)
        return; el.replaceChildren(); if (/^data:image\/jpeg;base64,/.test(p.photo)) {
        const im = document.createElement('img');
        im.src = p.photo;
        im.alt = '';
        el.append(im);
    }
    else
        el.textContent = (p.name || fallback || '?').charAt(0).toUpperCase(); }
    function themeCharts() {
        const ChartLib = window.Chart;
        if (!ChartLib || !ChartLib.instances)
            return;
        const dark = b.classList.contains('rc-dark'), text = dark ? '#a0b1c8' : '#64748b', grid = dark ? '#26384d' : '#e2e8f0';
        ChartLib.defaults.color = text;
        Object.values(ChartLib.instances).forEach(chart => {
            if (!chart.canvas?.closest('.rc-dashboard'))
                return;
            const o = chart.options;
            o.color = text;
            Object.keys(chart.scales || {}).forEach(id => {
                const scale = o.scales[id];
                if (!scale)
                    return;
                if (scale.ticks)
                    scale.ticks.color = text;
                if (scale.grid)
                    scale.grid.color = grid;
                if (scale.border)
                    scale.border.color = grid;
                if (scale.title)
                    scale.title.color = text;
            });
            if (o.plugins?.legend?.labels)
                o.plugins.legend.labels.color = text;
            if (o.plugins?.tooltip) {
                Object.assign(o.plugins.tooltip, { backgroundColor: dark ? '#19263a' : '#fff', titleColor: dark ? '#eef4fc' : '#172033', bodyColor: dark ? '#d3e0f2' : '#334155', borderColor: grid });
            }
            if (chart.config.type === 'doughnut')
                chart.data.datasets.forEach(ds => { if (ds.backgroundColor === '#e2e8f0' || ds.backgroundColor === '#26384d')
                    ds.backgroundColor = grid; });
            chart.update('none');
        });
    }
    function apply() { b.classList.toggle('rc-dark', p.theme === 'dark' || p.theme === 'system' && media.matches); b.classList.toggle('rc-large', p.size === 'large'); themeCharts(); if (name)
        name.textContent = p.name || original; drawAvatar(avatar, initial); drawAvatar(q('[data-pref-avatar]'), initial); qa('[data-theme-choice]').forEach(e => e.setAttribute('aria-pressed', String(e.dataset.themeChoice === p.theme))); qa('[data-size-choice]').forEach(e => e.setAttribute('aria-pressed', String(e.dataset.sizeChoice === p.size))); }
    function save() { try {
        const { theme, ...profile } = p;
        localStorage.setItem(key, JSON.stringify(profile));
        if (status)
            status.textContent = 'Preferências salvas.';
    }
    catch {
        if (status)
            status.textContent = 'Não foi possível salvar neste navegador.';
    } apply(); }
    apply();
    media.addEventListener('change', apply);
    window.addEventListener('rc-panel-theme-change', () => { if (window.RCTheme) {
        p.theme = window.RCTheme.panel();
        apply();
    } });
    qa('[data-theme-choice]').forEach(e => e.onclick = () => { p.theme = e.dataset.themeChoice; const ok = window.RCTheme?.setPanel(p.theme); save(); if (ok === false && status)
        status.textContent = 'Não foi possível salvar o tema neste navegador.'; });
    qa('[data-size-choice]').forEach(e => e.onclick = () => { p.size = e.dataset.sizeChoice; save(); });
    const input = q('#rc-display-name');
    if (input) {
        input.value = p.name;
        input.oninput = () => { p.name = input.value.slice(0, 60).trim(); save(); };
    }
    const file = q('#rc-photo');
    if (file)
        file.onchange = async () => { const f = file.files[0]; file.value = ''; if (!f)
            return; if (!['image/jpeg', 'image/png'].includes(f.type) || f.size > 5 * 1024 * 1024) {
            status.textContent = 'Escolha JPG ou PNG de até 5 MB.';
            return;
        } const url = URL.createObjectURL(f); try {
            const im = new Image();
            im.src = url;
            await im.decode();
            const side = Math.min(im.width, im.height), canvas = document.createElement('canvas');
            canvas.width = canvas.height = 256;
            canvas.getContext('2d').drawImage(im, (im.width - side) / 2, (im.height - side) / 2, side, side, 0, 0, 256, 256);
            p.photo = canvas.toDataURL('image/jpeg', .85);
            save();
        }
        catch {
            status.textContent = 'Não foi possível abrir a imagem.';
        }
        finally {
            URL.revokeObjectURL(url);
        } };
    q('#rc-remove-photo')?.addEventListener('click', () => { p.photo = ''; save(); });
    q('#rc-reset')?.addEventListener('click', () => { p = { theme: 'light', size: 'normal', name: '', photo: '' }; window.RCTheme?.setPanel('light'); if (input)
        input.value = ''; save(); });
    qa('main table').forEach(table => { if (table.parentElement.matches('.rc-table-scroll,.al-scroll,.table-container'))
        return; const wrap = document.createElement('div'); wrap.className = 'rc-table-scroll'; table.before(wrap); wrap.append(table); });
})();
