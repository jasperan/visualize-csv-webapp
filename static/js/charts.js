/**
 * Chart rendering module using Plotly.js
 */
const Charts = {
    darkMode: document.documentElement.classList.contains('dark'),

    layout(overrides = {}) {
        const theme = getComputedStyle(document.documentElement);
        const bg = theme.getPropertyValue('--surface').trim();
        const fg = theme.getPropertyValue('--ink').trim();
        const grid = theme.getPropertyValue('--line').trim();
        return {
            paper_bgcolor: bg,
            plot_bgcolor: bg,
            font: { color: fg, size: 11, family: 'Segoe UI, sans-serif' },
            colorway: ['#537a53', '#9baa6d', '#b59167', '#799698', '#bcb58e', '#8f7664'],
            margin: { t: 72, r: 24, b: 76, l: 60 },
            ...overrides,
            title: { x: 0.06, xanchor: 'left', y: 0.9, yanchor: 'bottom', font: { size: 14 }, ...overrides.title },
            xaxis: { gridcolor: grid, automargin: true, ...overrides.xaxis },
            yaxis: { gridcolor: grid, automargin: true, ...overrides.yaxis },
        };
    },

    config() {
        return { responsive: true, displayModeBar: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] };
    },

    renderHistogram(container, chart) {
        Plotly.newPlot(container, [{
            x: chart.data,
            type: 'histogram',
            marker: { color: '#537a53', line: { color: '#365c42', width: 1 } },
            opacity: 0.85,
        }], this.layout({ title: { text: chart.title }, xaxis: { title: chart.x } }), this.config());
    },

    renderScatter(container, chart) {
        Plotly.newPlot(container, [{
            x: chart.data_x,
            y: chart.data_y,
            mode: 'markers',
            type: 'scatter',
            marker: { color: '#537a53', size: 5, opacity: 0.6 },
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
            marker: { color: '#537a53' },
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
            marker: { color: ['#537a53', '#9baa6d', '#b59167', '#799698', '#bcb58e', '#8f7664'][i % 6] },
        }));
        Plotly.newPlot(container, traces, this.layout({ title: { text: chart.title }, showlegend: true }), this.config());
    },

    renderTimeseries(container, chart) {
        Plotly.newPlot(container, [{
            x: chart.x,
            y: chart.y,
            type: 'scatter',
            mode: 'lines+markers',
            marker: { color: '#537a53', size: 3 },
            line: { color: '#537a53', width: 2 },
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
            histogram: this.renderHistogram,
            scatter: this.renderScatter,
            bar: this.renderBar,
            box: this.renderBox,
            timeseries: this.renderTimeseries,
            heatmap: this.renderHeatmap,
        };
        const renderer = renderers[chart.type];
        if (renderer) renderer.call(this, div, chart);
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
                    marker: { color: '#537a53' },
                }], this.layout({ title: { text: spec.title || '' } }), this.config());
            }
        } catch (e) {
            div.innerHTML = `<p class="text-red-500 text-sm">Could not render chart: ${e.message}</p>`;
        }
    },

    updateTheme() {
        this.darkMode = document.documentElement.classList.contains('dark');
        const theme = this.layout();
        document.querySelectorAll('.js-plotly-plot').forEach(plot => {
            Plotly.relayout(plot, {
                paper_bgcolor: theme.paper_bgcolor,
                plot_bgcolor: theme.plot_bgcolor,
                'font.color': theme.font.color,
                'xaxis.gridcolor': theme.xaxis.gridcolor,
                'yaxis.gridcolor': theme.yaxis.gridcolor,
            });
        });
    }
};

window.addEventListener('themechange', () => Charts.updateTheme());
