/**
 * Dashboard Builder — save, load, and share chart collections.
 */
const Dashboards = {
    columns: [],
    currentId: null,
    widgets: [],

    init(columns) {
        this.columns = columns;
        this.bindEvents();
        this.loadList();
        this.checkUrlDashboard();
    },

    bindEvents() {
        document.getElementById('dash-save')?.addEventListener('click', () => this.save());
        document.getElementById('dash-add-widget')?.addEventListener('click', () => this.addWidgetFromBuilder());
        document.getElementById('dash-new')?.addEventListener('click', () => this.newDashboard());
    },

    checkUrlDashboard() {
        const params = new URLSearchParams(window.location.search);
        const dashId = params.get('dashboard');
        if (dashId) this.load(dashId);
    },

    async loadList() {
        const listEl = document.getElementById('dash-list');
        if (!listEl) return;

        try {
            const resp = await fetch('/api/dashboards');
            const data = await resp.json();

            if (!data.dashboards || data.dashboards.length === 0) {
                listEl.innerHTML = '<p class="text-xs text-gray-400 text-center py-2">No saved dashboards yet.</p>';
                return;
            }

            listEl.innerHTML = data.dashboards.map(d => `
                <div class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 group">
                    <button class="dash-load text-sm text-left flex-1 truncate hover:text-brand-600" data-id="${this.escapeAttr(d.id)}">
                        ${this.escapeHtml(d.name)} <span class="text-xs text-gray-400">(${d.widget_count} widget${d.widget_count !== 1 ? 's' : ''})</span>
                    </button>
                    <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button class="dash-share text-xs text-brand-600 hover:underline" data-id="${this.escapeAttr(d.id)}">Share</button>
                        <button class="dash-delete text-xs text-red-500 hover:underline" data-id="${this.escapeAttr(d.id)}">Delete</button>
                    </div>
                </div>
            `).join('');

            listEl.querySelectorAll('.dash-load').forEach(btn => {
                btn.addEventListener('click', () => this.load(btn.dataset.id));
            });
            listEl.querySelectorAll('.dash-share').forEach(btn => {
                btn.addEventListener('click', () => this.share(btn.dataset.id));
            });
            listEl.querySelectorAll('.dash-delete').forEach(btn => {
                btn.addEventListener('click', () => this.deleteDashboard(btn.dataset.id));
            });
        } catch (err) {
            listEl.innerHTML = `<p class="text-xs text-red-500">${err.message}</p>`;
        }
    },

    newDashboard() {
        this.currentId = null;
        this.widgets = [];
        document.getElementById('dash-name').value = '';
        this.renderWidgets();
    },

    addWidgetFromBuilder() {
        const chartType = document.getElementById('builder-type')?.value;
        const xCol = document.getElementById('builder-x')?.value;
        const yCol = document.getElementById('builder-y')?.value;
        const colorCol = document.getElementById('builder-color')?.value;
        const agg = document.getElementById('builder-agg')?.value;
        const title = document.getElementById('builder-title')?.value;

        if (!xCol) {
            this.showNotification('Configure a chart in the Builder tab first, then add it here.', 'warning');
            return;
        }

        this.widgets.push({
            id: Date.now().toString(36),
            chartType: chartType || 'bar',
            x: xCol,
            y: yCol || '',
            color: colorCol || '',
            agg: agg || 'none',
            title: title || '',
        });

        this.renderWidgets();
        this.showNotification('Widget added to dashboard.', 'success');
    },

    renderWidgets() {
        const grid = document.getElementById('dash-widgets');
        if (!grid) return;

        if (this.widgets.length === 0) {
            grid.innerHTML = '<p class="text-gray-400 text-sm text-center py-8 col-span-full">No widgets yet. Use the Chart Builder tab to configure a chart, then click "Add to Dashboard".</p>';
            return;
        }

        grid.innerHTML = this.widgets.map((w, i) => `
            <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
                <div class="flex items-center justify-between px-3 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
                    <span class="text-xs font-medium truncate">${this.escapeHtml(w.title || this.autoTitle(w))}</span>
                    <button class="dash-remove-widget text-xs text-red-500 hover:underline" data-idx="${i}">Remove</button>
                </div>
                <div class="p-2 min-h-[300px]" id="dash-widget-${w.id}"></div>
            </div>
        `).join('');

        grid.querySelectorAll('.dash-remove-widget').forEach(btn => {
            btn.addEventListener('click', () => {
                this.widgets.splice(parseInt(btn.dataset.idx), 1);
                this.renderWidgets();
            });
        });

        // Render each widget chart
        this.widgets.forEach(w => this.renderWidgetChart(w));
    },

    async renderWidgetChart(widget) {
        const container = document.getElementById(`dash-widget-${widget.id}`);
        if (!container) return;

        container.innerHTML = '<div class="flex items-center justify-center h-full text-gray-400 text-sm"><svg class="animate-spin w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/></svg>Loading...</div>';

        try {
            const resp = await fetch('/api/builder/data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ x: widget.x, y: widget.y, color: widget.color, agg: widget.agg }),
            });
            const data = await resp.json();
            if (data.error) {
                container.innerHTML = `<p class="text-red-500 text-sm p-4">${data.error}</p>`;
                return;
            }

            container.innerHTML = '';
            const title = widget.title || this.autoTitle(widget);
            Builder.renderChart(container, widget.chartType, data, title, widget.x, widget.y, widget.color);
        } catch (err) {
            container.innerHTML = `<p class="text-red-500 text-sm p-4">${err.message}</p>`;
        }
    },

    autoTitle(w) {
        if (w.chartType === 'histogram') return `Distribution of ${w.x}`;
        if (w.chartType === 'pie') return `${w.x} Breakdown`;
        if (w.agg !== 'none' && w.y) return `${w.agg} of ${w.y} by ${w.x}`;
        if (w.y) return `${w.y} vs ${w.x}`;
        return w.x;
    },

    async save() {
        const nameInput = document.getElementById('dash-name');
        const name = nameInput?.value.trim();
        if (!name) {
            this.showNotification('Enter a dashboard name.', 'warning');
            nameInput?.focus();
            return;
        }
        if (this.widgets.length === 0) {
            this.showNotification('Add at least one widget before saving.', 'warning');
            return;
        }

        try {
            const resp = await fetch('/api/dashboards', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: this.currentId,
                    name,
                    widgets: this.widgets,
                }),
            });
            const data = await resp.json();
            if (data.error) {
                this.showNotification(data.error, 'error');
                return;
            }
            this.currentId = data.id;
            this.showNotification('Dashboard saved!', 'success');
            this.loadList();
        } catch (err) {
            this.showNotification('Save failed: ' + err.message, 'error');
        }
    },

    async load(dashId) {
        try {
            const resp = await fetch(`/api/dashboards/${encodeURIComponent(dashId)}`);
            const data = await resp.json();
            if (data.error) {
                this.showNotification(data.error, 'error');
                return;
            }
            this.currentId = data.id;
            this.widgets = data.widgets || [];
            document.getElementById('dash-name').value = data.name || '';
            this.renderWidgets();

            // Switch to dashboards tab
            document.querySelector('[data-tab="dashboards"]')?.click();
        } catch (err) {
            this.showNotification('Load failed: ' + err.message, 'error');
        }
    },

    share(dashId) {
        const url = `${window.location.origin}${window.location.pathname}?dashboard=${encodeURIComponent(dashId)}`;
        navigator.clipboard.writeText(url).then(() => {
            this.showNotification('Share link copied to clipboard!', 'success');
        }).catch(() => {
            // Fallback
            prompt('Copy this link:', url);
        });
    },

    async deleteDashboard(dashId) {
        if (!confirm('Delete this dashboard?')) return;
        try {
            await fetch(`/api/dashboards/${encodeURIComponent(dashId)}`, { method: 'DELETE' });
            if (this.currentId === dashId) this.newDashboard();
            this.loadList();
        } catch (err) {
            this.showNotification('Delete failed: ' + err.message, 'error');
        }
    },

    showNotification(msg, type) {
        const area = document.getElementById('dash-notifications');
        if (!area) return;
        const colors = { success: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300', warning: 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300', error: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300' };
        const el = document.createElement('div');
        el.className = `text-xs px-3 py-2 rounded-lg ${colors[type] || colors.success} transition-opacity`;
        el.textContent = msg;
        area.innerHTML = '';
        area.appendChild(el);
        setTimeout(() => el.remove(), 3000);
    },

    escapeHtml(text) {
        const el = document.createElement('span');
        el.textContent = text;
        return el.innerHTML;
    },

    escapeAttr(text) {
        return String(text).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },
};
