/**
 * Interactive Chart Builder
 */
const Builder = {
    columns: [],

    init(columns) {
        this.columns = columns;
        this.populateSelects();
        this.bindEvents();
    },

    populateSelects() {
        const selects = ['builder-x', 'builder-y', 'builder-color'];
        selects.forEach(id => {
            const sel = document.getElementById(id);
            if (!sel) return;
            const first = sel.options[0];
            sel.innerHTML = '';
            sel.appendChild(first);
            this.columns.forEach(col => {
                const opt = document.createElement('option');
                opt.value = col.name;
                opt.textContent = `${col.name} (${col.col_type})`;
                sel.appendChild(opt);
            });
        });
    },

    bindEvents() {
        const renderBtn = document.getElementById('builder-render');
        if (!renderBtn) return;

        renderBtn.addEventListener('click', () => this.render());

        // Auto-hide Y axis for histogram
        document.getElementById('builder-type')?.addEventListener('change', e => {
            const yGroup = document.getElementById('builder-y-group');
            const colorGroup = document.getElementById('builder-color-group');
            if (e.target.value === 'histogram') {
                yGroup.style.display = 'none';
            } else {
                yGroup.style.display = '';
            }
        });
    },

    async render() {
        const chartType = document.getElementById('builder-type').value;
        const xCol = document.getElementById('builder-x').value;
        const yCol = document.getElementById('builder-y').value;
        const colorCol = document.getElementById('builder-color').value;
        const agg = document.getElementById('builder-agg').value;
        const title = document.getElementById('builder-title').value;
        const preview = document.getElementById('builder-preview');

        if (!xCol) {
            preview.innerHTML = '<p class="text-amber-500">Please select at least an X axis column.</p>';
            return;
        }

        preview.innerHTML = '<div class="flex items-center justify-center gap-2"><svg class="animate-spin w-6 h-6 text-brand-600" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/></svg> Loading data...</div>';

        try {
            const resp = await fetch('/api/builder/data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ x: xCol, y: yCol, color: colorCol, agg }),
            });
            const data = await resp.json();
            if (data.error) {
                preview.innerHTML = `<p class="text-red-500">${data.error}</p>`;
                return;
            }

            preview.innerHTML = '';
            const autoTitle = title || this.generateTitle(chartType, xCol, yCol, agg);

            this.renderChart(preview, chartType, data, autoTitle, xCol, yCol, colorCol);
        } catch (err) {
            preview.innerHTML = `<p class="text-red-500">Error: ${err.message}</p>`;
        }
    },

    generateTitle(type, x, y, agg) {
        if (type === 'histogram') return `Distribution of ${x}`;
        if (type === 'pie') return `${x} Breakdown`;
        if (type === 'box' || type === 'violin') return `${y || x} Distribution`;
        if (agg !== 'none' && y) return `${agg} of ${y} by ${x}`;
        if (y) return `${y} vs ${x}`;
        return `${x}`;
    },

    renderChart(container, type, data, title, xCol, yCol, colorCol) {
        Charts.updateTheme();
        const layout = Charts.layout({ title: { text: title }, height: 420 });
        const config = Charts.config();

        let traces = [];

        switch (type) {
            case 'histogram':
                traces = [{ x: data.x, type: 'histogram', marker: { color: '#3b82f6' }, opacity: 0.85 }];
                layout.xaxis = { title: xCol };
                break;

            case 'bar':
                traces = [{ x: data.x, y: data.y, type: 'bar', marker: { color: '#3b82f6' } }];
                layout.xaxis = { title: xCol };
                layout.yaxis = { title: yCol };
                break;

            case 'scatter':
                if (data.color) {
                    const groups = {};
                    data.x.forEach((v, i) => {
                        const g = data.color[i];
                        if (!groups[g]) groups[g] = { x: [], y: [] };
                        groups[g].x.push(v);
                        groups[g].y.push(data.y[i]);
                    });
                    traces = Object.entries(groups).map(([name, d]) => ({
                        x: d.x, y: d.y, mode: 'markers', type: 'scatter',
                        name, marker: { size: 6, opacity: 0.7 },
                    }));
                } else {
                    traces = [{ x: data.x, y: data.y, mode: 'markers', type: 'scatter', marker: { color: '#3b82f6', size: 6, opacity: 0.7 } }];
                }
                layout.xaxis = { title: xCol };
                layout.yaxis = { title: yCol };
                break;

            case 'line':
                traces = [{ x: data.x, y: data.y, type: 'scatter', mode: 'lines+markers', marker: { color: '#3b82f6', size: 4 }, line: { color: '#3b82f6', width: 2 } }];
                layout.xaxis = { title: xCol };
                layout.yaxis = { title: yCol };
                break;

            case 'box':
                traces = [{ y: data.y || data.x, type: 'box', marker: { color: '#3b82f6' }, name: yCol || xCol }];
                break;

            case 'violin':
                traces = [{ y: data.y || data.x, type: 'violin', marker: { color: '#3b82f6' }, name: yCol || xCol, box: { visible: true }, meanline: { visible: true } }];
                break;

            case 'pie':
                if (data.aggregated) {
                    traces = [{ labels: data.x, values: data.y, type: 'pie', hole: 0.3 }];
                } else {
                    // Count occurrences
                    const counts = {};
                    data.x.forEach(v => { counts[v] = (counts[v] || 0) + 1; });
                    traces = [{ labels: Object.keys(counts), values: Object.values(counts), type: 'pie', hole: 0.3 }];
                }
                break;

            case 'heatmap':
                // 2D histogram / density
                traces = [{ x: data.x, y: data.y, type: 'histogram2d', colorscale: 'Blues' }];
                layout.xaxis = { title: xCol };
                layout.yaxis = { title: yCol };
                break;
        }

        Plotly.newPlot(container, traces, layout, config);
    }
};
