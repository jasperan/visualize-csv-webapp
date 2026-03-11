/**
 * Chart rendering module using Plotly.js
 */
const Charts = {
    darkMode: document.documentElement.classList.contains('dark'),

    layout(overrides = {}) {
        const bg = this.darkMode ? '#111827' : '#ffffff';
        const fg = this.darkMode ? '#e5e7eb' : '#374151';
        const grid = this.darkMode ? '#1f2937' : '#f3f4f6';
        return Object.assign({
            paper_bgcolor: bg,
            plot_bgcolor: bg,
            font: { color: fg, size: 12 },
            margin: { t: 40, r: 20, b: 50, l: 60 },
            xaxis: { gridcolor: grid },
            yaxis: { gridcolor: grid },
        }, overrides);
    },

    config() {
        return { responsive: true, displayModeBar: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] };
    },

    renderHistogram(container, chart) {
        Plotly.newPlot(container, [{
            x: chart.data,
            type: 'histogram',
            marker: { color: '#3b82f6', line: { color: '#2563eb', width: 1 } },
            opacity: 0.85,
        }], this.layout({ title: { text: chart.title }, xaxis: { title: chart.x } }), this.config());
    },

    renderScatter(container, chart) {
        Plotly.newPlot(container, [{
            x: chart.data_x,
            y: chart.data_y,
            mode: 'markers',
            type: 'scatter',
            marker: { color: '#3b82f6', size: 5, opacity: 0.6 },
        }], this.layout({
            title: { text: chart.title },
            xaxis: { title: chart.x },
            yaxis: { title: chart.y },
        }), this.config());
    },

    renderBar(container, chart) {
        Plotly.newPlot(container, [{
            x: chart.x,
            y: chart.y,
            type: 'bar',
            marker: { color: '#3b82f6' },
        }], this.layout({
            title: { text: chart.title },
            xaxis: { title: chart.x_label },
            yaxis: { title: chart.y_label },
        }), this.config());
    },

    renderBox(container, chart) {
        const traces = chart.data.map((d, i) => ({
            y: d.values,
            name: d.name,
            type: 'box',
            marker: { color: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'][i % 6] },
        }));
        Plotly.newPlot(container, traces, this.layout({ title: { text: chart.title }, showlegend: true }), this.config());
    },

    renderTimeseries(container, chart) {
        Plotly.newPlot(container, [{
            x: chart.x,
            y: chart.y,
            type: 'scatter',
            mode: 'lines+markers',
            marker: { color: '#3b82f6', size: 3 },
            line: { color: '#3b82f6', width: 2 },
        }], this.layout({
            title: { text: chart.title },
            xaxis: { title: chart.x_label },
            yaxis: { title: chart.y_label },
        }), this.config());
    },

    renderHeatmap(container, chart) {
        Plotly.newPlot(container, [{
            z: chart.values,
            x: chart.labels,
            y: chart.labels,
            type: 'heatmap',
            colorscale: 'RdBu',
            zmid: 0,
            text: chart.values.map(row => row.map(v => v !== null ? v.toFixed(2) : '')),
            texttemplate: '%{text}',
            textfont: { size: 10 },
        }], this.layout({
            title: { text: chart.title },
            height: 500,
            yaxis: { autorange: 'reversed' },
        }), this.config());
    },

    render(container, chart) {
        const div = document.createElement('div');
        div.className = 'bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4';
        div.style.minHeight = '350px';
        container.appendChild(div);

        const renderers = {
            histogram: 'renderHistogram',
            scatter: 'renderScatter',
            bar: 'renderBar',
            box: 'renderBox',
            timeseries: 'renderTimeseries',
            heatmap: 'renderHeatmap',
        };
        const method = renderers[chart.type];
        if (method) this[method](div, chart);
    },

    renderDynamic(container, spec, df_data) {
        // Render a chart from an LLM-generated spec
        const div = document.createElement('div');
        div.className = 'bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 mt-3';
        div.style.minHeight = '300px';
        container.appendChild(div);

        try {
            const type = spec.type || 'bar';
            if (type === 'pie') {
                Plotly.newPlot(div, [{ labels: spec.x, values: spec.y, type: 'pie' }],
                    this.layout({ title: { text: spec.title || '' } }), this.config());
            } else {
                Plotly.newPlot(div, [{
                    x: spec.x, y: spec.y,
                    type: type === 'line' ? 'scatter' : type,
                    mode: type === 'line' ? 'lines+markers' : undefined,
                    marker: { color: '#3b82f6' },
                }], this.layout({ title: { text: spec.title || '' } }), this.config());
            }
        } catch (e) {
            div.innerHTML = `<p class="text-red-500 text-sm">Could not render chart: ${e.message}</p>`;
        }
    },

    updateTheme() {
        this.darkMode = document.documentElement.classList.contains('dark');
    }
};

window.addEventListener('themechange', () => Charts.updateTheme());
