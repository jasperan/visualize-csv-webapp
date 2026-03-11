/**
 * Main dashboard application logic
 */
(function () {
    // -----------------------------------------------------------------------
    // Tab switching
    // -----------------------------------------------------------------------
    const tabBtns = document.querySelectorAll('.tab-btn');
    const panels = document.querySelectorAll('.tab-panel');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => {
                b.classList.remove('active', 'border-brand-600', 'text-brand-600');
                b.classList.add('border-transparent', 'text-gray-500');
            });
            btn.classList.add('active', 'border-brand-600', 'text-brand-600');
            btn.classList.remove('border-transparent', 'text-gray-500');
            panels.forEach(p => p.classList.add('hidden'));
            document.getElementById('panel-' + btn.dataset.tab)?.classList.remove('hidden');
        });
    });

    // -----------------------------------------------------------------------
    // Sidebar toggle (mobile)
    // -----------------------------------------------------------------------
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('hidden'));
    }

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    let allColumns = [];
    let visibleColumns = new Set();
    let currentPage = 1;
    let sortCol = null;
    let sortAsc = true;

    // -----------------------------------------------------------------------
    // Column picker
    // -----------------------------------------------------------------------
    function renderColumnList(columns) {
        const list = document.getElementById('column-list');
        if (!list) return;
        list.innerHTML = '';
        columns.forEach(col => {
            const label = document.createElement('label');
            label.className = 'flex items-center gap-2 py-0.5 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 px-1 rounded';
            const typeColors = { numeric: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300', categorical: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300', temporal: 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300', text: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' };
            label.innerHTML = `
                <input type="checkbox" class="col-toggle rounded" data-col="${col.name}" ${visibleColumns.has(col.name) ? 'checked' : ''}>
                <span class="truncate flex-1" title="${col.name}">${col.name}</span>
                <span class="text-[10px] px-1 rounded ${typeColors[col.col_type] || typeColors.text}">${col.col_type[0].toUpperCase()}</span>
            `;
            label.querySelector('input').addEventListener('change', e => {
                if (e.target.checked) visibleColumns.add(col.name);
                else visibleColumns.delete(col.name);
                loadTable(currentPage);
            });
            list.appendChild(label);
        });

    }

    // -----------------------------------------------------------------------
    // Data table
    // -----------------------------------------------------------------------
    async function loadTable(page = 1) {
        currentPage = page;
        try {
            // Server-side sort
            let url = `/api/data?page=${page}&per_page=50`;
            if (sortCol) url += `&sort=${encodeURIComponent(sortCol)}&sort_asc=${sortAsc}`;
            const resp = await fetch(url);
            const data = await resp.json();
            if (data.error) return;

            const cols = data.columns.filter(c => visibleColumns.has(c));
            const colIndices = cols.map(c => data.columns.indexOf(c));

            const thead = document.getElementById('table-head');
            thead.innerHTML = '<tr>' + cols.map(c =>
                `<th class="px-3 py-2 font-medium whitespace-nowrap" data-col="${c}">
                    ${escapeHtml(c)}
                    <span class="text-[10px] ml-1">${sortCol === c ? (sortAsc ? '&#9650;' : '&#9660;') : ''}</span>
                </th>`
            ).join('') + '</tr>';

            thead.querySelectorAll('th').forEach(th => {
                th.addEventListener('click', () => {
                    const col = th.dataset.col;
                    if (sortCol === col) sortAsc = !sortAsc;
                    else { sortCol = col; sortAsc = true; }
                    loadTable(1); // Reset to page 1 on sort
                });
            });

            const rows = data.rows.map(r => colIndices.map(i => r[i]));

            const tbody = document.getElementById('table-body');
            tbody.innerHTML = rows.map(r =>
                '<tr class="hover:bg-gray-50 dark:hover:bg-gray-800/50">' +
                r.map(v => `<td class="px-3 py-2 whitespace-nowrap">${escapeHtml(v != null ? String(v) : '')}</td>`).join('') +
                '</tr>'
            ).join('');

            // Pagination
            const pag = document.getElementById('table-pagination');
            pag.innerHTML = `
                <span>Showing ${(page - 1) * data.per_page + 1}-${Math.min(page * data.per_page, data.total_rows)} of ${data.total_rows}</span>
                <div class="flex gap-2">
                    <button class="px-3 py-1 rounded border ${page > 1 ? 'hover:bg-gray-100 dark:hover:bg-gray-800' : 'opacity-40 cursor-not-allowed'}" ${page <= 1 ? 'disabled' : ''} id="prev-page">Prev</button>
                    <span class="px-2 py-1">Page ${page} of ${data.total_pages}</span>
                    <button class="px-3 py-1 rounded border ${page < data.total_pages ? 'hover:bg-gray-100 dark:hover:bg-gray-800' : 'opacity-40 cursor-not-allowed'}" ${page >= data.total_pages ? 'disabled' : ''} id="next-page">Next</button>
                </div>
            `;
            document.getElementById('prev-page')?.addEventListener('click', () => { if (page > 1) loadTable(page - 1); });
            document.getElementById('next-page')?.addEventListener('click', () => { if (page < data.total_pages) loadTable(page + 1); });
        } catch (err) {
            console.error('Table load error:', err);
        }
    }

    // -----------------------------------------------------------------------
    // Insights (renders from pre-fetched data)
    // -----------------------------------------------------------------------
    function renderInsights(insights) {
        const container = document.getElementById('insights-container');

        const iconMap = {
            'table': '<path d="M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18"/>',
            'alert-triangle': '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
            'zap': '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
            'trending-up': '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
            'trending-down': '<polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/>',
            'bar-chart-2': '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
            'hash': '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>',
            'copy': '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>',
        };

        const severityColors = {
            warning: 'border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950',
            success: 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-950',
            info: 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900',
        };

        container.innerHTML = '';

        insights.forEach(insight => {
            const card = document.createElement('div');
            card.className = `insight-card rounded-xl border p-4 ${severityColors[insight.severity] || severityColors.info}`;
            card.innerHTML = `
                <div class="flex items-start gap-3">
                    <svg class="w-5 h-5 shrink-0 mt-0.5 ${insight.severity === 'warning' ? 'text-amber-500' : insight.severity === 'success' ? 'text-green-500' : 'text-gray-400'}" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                        ${iconMap[insight.icon] || iconMap['table']}
                    </svg>
                    <div>
                        <p class="font-semibold text-sm">${escapeHtml(insight.title)}</p>
                        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">${escapeHtml(insight.detail)}</p>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });
    }

    // Legacy loader (fallback if async analysis not used)
    async function loadInsights() {
        try {
            const resp = await fetch('/api/insights');
            const data = await resp.json();
            if (data.error) return;
            renderInsights(data.insights || []);
            loadPII(document.getElementById('insights-container'));
        } catch (err) {
            document.getElementById('insights-container').innerHTML = `<p class="text-red-500">Failed to load insights: ${err.message}</p>`;
        }
    }

    // -----------------------------------------------------------------------
    // AI Narrative
    // -----------------------------------------------------------------------
    function initNarrative() {
        const section = document.getElementById('narrative-section');
        const btn = document.getElementById('generate-narrative');
        const content = document.getElementById('narrative-content');
        if (!section || !btn) return;

        section.classList.remove('hidden');

        btn.addEventListener('click', async () => {
            btn.disabled = true;
            btn.textContent = 'Generating...';
            content.innerHTML = '<span class="flex items-center gap-2"><svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/></svg> Analyzing your data with AI...</span>';
            try {
                const resp = await fetch('/api/narrative');
                const data = await resp.json();
                if (data.narrative) {
                    content.textContent = data.narrative;
                    btn.textContent = 'Regenerate';
                } else {
                    content.textContent = data.error || 'Could not generate narrative. Is Ollama running?';
                    btn.textContent = 'Retry';
                }
            } catch (err) {
                content.textContent = 'Error: ' + err.message;
                btn.textContent = 'Retry';
            }
            btn.disabled = false;
        });
    }

    // -----------------------------------------------------------------------
    // PII Detection
    // -----------------------------------------------------------------------
    async function loadPII(insightsContainer) {
        try {
            const resp = await fetch('/api/pii');
            const data = await resp.json();
            if (!data.has_pii) return;

            const cols = Object.entries(data.pii);
            const card = document.createElement('div');
            card.className = 'insight-card rounded-xl border p-4 border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950 col-span-full';
            let details = cols.map(([col, types]) =>
                `<strong>${escapeHtml(col)}</strong>: ${types.map(t => t.type + ' (' + t.match_pct + '%)').join(', ')}`
            ).join('<br>');
            card.innerHTML = `
                <div class="flex items-start gap-3">
                    <svg class="w-5 h-5 shrink-0 mt-0.5 text-red-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                        <path d="M12 15v2m0 0v2m0-2h2m-2 0H10m12-4a10 10 0 11-20 0 10 10 0 0120 0z"/>
                    </svg>
                    <div class="flex-1">
                        <p class="font-semibold text-sm text-red-700 dark:text-red-300">Potential PII Detected</p>
                        <p class="text-xs text-red-600 dark:text-red-400 mt-1">${details}</p>
                        <button class="mt-2 text-xs bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700 pii-redact-btn">View Redacted Data</button>
                    </div>
                </div>
            `;
            // Insert at the top of insights
            insightsContainer.insertBefore(card, insightsContainer.firstChild);

            card.querySelector('.pii-redact-btn').addEventListener('click', async () => {
                try {
                    const r = await fetch('/api/pii/redact', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({}),
                    });
                    const rd = await r.json();
                    // Switch to table tab and show redacted data
                    document.querySelector('[data-tab="table"]')?.click();
                    const tbody = document.getElementById('table-body');
                    const thead = document.getElementById('table-head');
                    thead.innerHTML = '<tr>' + rd.columns.map(c =>
                        `<th class="px-3 py-2 font-medium whitespace-nowrap ${rd.redacted_columns.includes(c) ? 'text-red-600' : ''}">${escapeHtml(c)}${rd.redacted_columns.includes(c) ? ' (redacted)' : ''}</th>`
                    ).join('') + '</tr>';
                    tbody.innerHTML = rd.rows.map(r =>
                        '<tr class="hover:bg-gray-50 dark:hover:bg-gray-800/50">' +
                        r.map(v => `<td class="px-3 py-2 whitespace-nowrap">${escapeHtml(v != null ? String(v) : '')}</td>`).join('') +
                        '</tr>'
                    ).join('');
                } catch (err) {
                    console.error('PII redact error:', err);
                }
            });
        } catch (err) {
            console.error('PII detection error:', err);
        }
    }

    // -----------------------------------------------------------------------
    // Charts (renders from pre-fetched data)
    // -----------------------------------------------------------------------
    function renderChartsData(charts) {
        const container = document.getElementById('charts-container');
        container.innerHTML = '';
        if (charts.length === 0) {
            container.innerHTML = '<p class="text-gray-400 text-center py-8">No charts could be auto-generated for this dataset. Try the AI chat to request specific visualizations.</p>';
            return;
        }
        charts.forEach(chart => Charts.render(container, chart));
    }

    async function loadCharts() {
        try {
            const resp = await fetch('/api/charts');
            const data = await resp.json();
            if (!data.error) renderChartsData(data.charts || []);
        } catch (err) {
            document.getElementById('charts-container').innerHTML = `<p class="text-red-500">Failed to load charts: ${err.message}</p>`;
        }
    }

    // -----------------------------------------------------------------------
    // Statistics (renders from pre-fetched data)
    // -----------------------------------------------------------------------
    function renderStatsData(stats) {
        const container = document.getElementById('stats-container');
        let html = '<table class="text-sm w-full"><thead><tr class="bg-gray-100 dark:bg-gray-800">';
        html += '<th class="px-3 py-2 text-left">Column</th><th class="px-3 py-2 text-left">Type</th>';
        html += '<th class="px-3 py-2 text-right">Count</th><th class="px-3 py-2 text-right">Mean</th>';
        html += '<th class="px-3 py-2 text-right">Std</th><th class="px-3 py-2 text-right">Min</th>';
        html += '<th class="px-3 py-2 text-right">Median</th><th class="px-3 py-2 text-right">Max</th>';
        html += '<th class="px-3 py-2 text-right">Unique</th>';
        html += '</tr></thead><tbody>';

        Object.values(stats).forEach(s => {
            html += `<tr class="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50">`;
            html += `<td class="px-3 py-2 font-medium">${escapeHtml(s.name)}</td>`;
            html += `<td class="px-3 py-2 text-gray-500">${escapeHtml(s.dtype)}</td>`;
            html += `<td class="px-3 py-2 text-right">${s.count}</td>`;
            html += `<td class="px-3 py-2 text-right">${s.mean != null ? s.mean : '-'}</td>`;
            html += `<td class="px-3 py-2 text-right">${s.std != null ? s.std : '-'}</td>`;
            html += `<td class="px-3 py-2 text-right">${s.min != null ? s.min : '-'}</td>`;
            html += `<td class="px-3 py-2 text-right">${s.median != null ? s.median : '-'}</td>`;
            html += `<td class="px-3 py-2 text-right">${s.max != null ? s.max : '-'}</td>`;
            html += `<td class="px-3 py-2 text-right">${s.unique != null ? s.unique : '-'}</td>`;
            html += '</tr>';
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    }

    async function loadStats() {
        try {
            const resp = await fetch('/api/stats');
            const data = await resp.json();
            if (!data.error) renderStatsData(data.stats || {});
        } catch (err) {
            document.getElementById('stats-container').innerHTML = `<p class="text-red-500">Failed to load statistics: ${err.message}</p>`;
        }
    }

    // -----------------------------------------------------------------------
    // Background analysis polling
    // -----------------------------------------------------------------------
    const renderedTasks = new Set();

    async function startBackgroundAnalysis() {
        try {
            await fetch('/api/analysis/start', { method: 'POST' });
            pollAnalysis();
        } catch (err) {
            // Fall back to synchronous loading
            console.warn('Background analysis unavailable, falling back:', err);
            await Promise.all([loadInsights(), loadCharts(), loadStats()]);
        }
    }

    async function pollAnalysis() {
        const maxPolls = 60; // 30s max
        for (let i = 0; i < maxPolls; i++) {
            try {
                const resp = await fetch('/api/analysis/status');
                const status = await resp.json();

                // Render completed tasks progressively
                if (status.insights?.status === 'done' && !renderedTasks.has('insights')) {
                    renderInsights(status.insights.result || []);
                    renderedTasks.add('insights');
                }
                if (status.charts?.status === 'done' && !renderedTasks.has('charts')) {
                    renderChartsData(status.charts.result || []);
                    renderedTasks.add('charts');
                }
                if (status.stats?.status === 'done' && !renderedTasks.has('stats')) {
                    renderStatsData(status.stats.result || {});
                    renderedTasks.add('stats');
                }
                if (status.pii?.status === 'done' && !renderedTasks.has('pii')) {
                    const piiData = status.pii.result || {};
                    if (piiData.has_pii) {
                        loadPII(document.getElementById('insights-container'));
                    }
                    renderedTasks.add('pii');
                }

                // Check if all done
                const allDone = Object.values(status).every(t => t.status === 'done' || t.status === 'error');
                if (allDone) break;
            } catch (err) {
                console.error('Poll error:', err);
                break;
            }
            await new Promise(r => setTimeout(r, 500));
        }
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    function escapeHtml(text) {
        const el = document.createElement('span');
        el.textContent = text;
        return el.innerHTML;
    }

    // -----------------------------------------------------------------------
    // Init
    // -----------------------------------------------------------------------
    async function init() {
        // Toggle-all columns — register once in init to avoid listener accumulation
        document.getElementById('toggle-all-cols')?.addEventListener('click', () => {
            const allChecked = visibleColumns.size === allColumns.length;
            allColumns.forEach(c => allChecked ? visibleColumns.delete(c.name) : visibleColumns.add(c.name));
            renderColumnList(allColumns);
            loadTable(currentPage);
        });

        // Load column info first
        try {
            const resp = await fetch('/api/column_info');
            const data = await resp.json();
            allColumns = data.columns || [];
            allColumns.forEach(c => visibleColumns.add(c.name));
            renderColumnList(allColumns);
        } catch (err) {
            console.error('Column info error:', err);
        }

        // Load table immediately, analysis in background
        loadTable(1);
        startBackgroundAnalysis();

        // Init modules
        Chat.init();
        initNarrative();
        Builder.init(allColumns);
        SQLPanel.init(allColumns);
        Dashboards.init(allColumns);
    }

    init();
})();
