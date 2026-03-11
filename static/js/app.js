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
    // Insights
    // -----------------------------------------------------------------------
    async function loadInsights() {
        const container = document.getElementById('insights-container');
        try {
            const resp = await fetch('/api/insights');
            const data = await resp.json();
            if (data.error) { container.innerHTML = `<p class="text-red-500">${data.error}</p>`; return; }

            container.innerHTML = '';
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

            data.insights.forEach(insight => {
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
        } catch (err) {
            container.innerHTML = `<p class="text-red-500">Failed to load insights: ${err.message}</p>`;
        }
    }

    // -----------------------------------------------------------------------
    // Charts
    // -----------------------------------------------------------------------
    async function loadCharts() {
        const container = document.getElementById('charts-container');
        try {
            const resp = await fetch('/api/charts');
            const data = await resp.json();
            if (data.error) { container.innerHTML = `<p class="text-red-500">${data.error}</p>`; return; }

            container.innerHTML = '';
            data.charts.forEach(chart => Charts.render(container, chart));

            if (data.charts.length === 0) {
                container.innerHTML = '<p class="text-gray-400 text-center py-8">No charts could be auto-generated for this dataset. Try the AI chat to request specific visualizations.</p>';
            }
        } catch (err) {
            container.innerHTML = `<p class="text-red-500">Failed to load charts: ${err.message}</p>`;
        }
    }

    // -----------------------------------------------------------------------
    // Statistics
    // -----------------------------------------------------------------------
    async function loadStats() {
        const container = document.getElementById('stats-container');
        try {
            const resp = await fetch('/api/stats');
            const data = await resp.json();
            if (data.error) { container.innerHTML = `<p class="text-red-500">${data.error}</p>`; return; }

            let html = '<table class="text-sm w-full"><thead><tr class="bg-gray-100 dark:bg-gray-800">';
            html += '<th class="px-3 py-2 text-left">Column</th><th class="px-3 py-2 text-left">Type</th>';
            html += '<th class="px-3 py-2 text-right">Count</th><th class="px-3 py-2 text-right">Mean</th>';
            html += '<th class="px-3 py-2 text-right">Std</th><th class="px-3 py-2 text-right">Min</th>';
            html += '<th class="px-3 py-2 text-right">Median</th><th class="px-3 py-2 text-right">Max</th>';
            html += '<th class="px-3 py-2 text-right">Unique</th>';
            html += '</tr></thead><tbody>';

            Object.values(data.stats).forEach(s => {
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
        } catch (err) {
            container.innerHTML = `<p class="text-red-500">Failed to load statistics: ${err.message}</p>`;
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

        // Load everything in parallel
        await Promise.all([
            loadInsights(),
            loadTable(1),
            loadCharts(),
            loadStats(),
        ]);

        // Init chat
        Chat.init();
    }

    init();
})();
