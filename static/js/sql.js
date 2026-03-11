/**
 * DuckDB-WASM client-side SQL query engine
 * Runs entirely in the browser — zero server load after initial CSV download.
 */
const SQLPanel = {
    db: null,
    conn: null,
    loaded: false,
    columns: [],

    async init(columns) {
        this.columns = columns;
        this.bindEvents();
        this.populateExamples();
    },

    bindEvents() {
        const runBtn = document.getElementById('sql-run');
        const editor = document.getElementById('sql-editor');
        if (!runBtn || !editor) return;

        runBtn.addEventListener('click', () => this.runQuery());
        editor.addEventListener('keydown', e => {
            // Ctrl+Enter or Cmd+Enter to run
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                this.runQuery();
            }
            // Tab inserts spaces
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = editor.selectionStart;
                editor.value = editor.value.substring(0, start) + '  ' + editor.value.substring(editor.selectionEnd);
                editor.selectionStart = editor.selectionEnd = start + 2;
            }
        });

        // Example query buttons
        document.querySelectorAll('.sql-example').forEach(btn => {
            btn.addEventListener('click', () => {
                editor.value = btn.dataset.query;
                this.runQuery();
            });
        });
    },

    populateExamples() {
        const container = document.getElementById('sql-examples');
        if (!container || this.columns.length === 0) return;

        const numCols = this.columns.filter(c => c.col_type === 'numeric');
        const catCols = this.columns.filter(c => c.col_type === 'categorical');
        const firstCol = this.columns[0]?.name || '*';

        const examples = [
            { label: 'Preview', query: 'SELECT * FROM data LIMIT 20' },
            { label: 'Row count', query: 'SELECT COUNT(*) AS total_rows FROM data' },
        ];

        if (numCols.length > 0) {
            const nc = numCols[0].name;
            examples.push({
                label: `Stats: ${nc}`,
                query: `SELECT\n  MIN("${nc}") AS min_val,\n  AVG("${nc}") AS avg_val,\n  MAX("${nc}") AS max_val,\n  STDDEV("${nc}") AS std_dev\nFROM data`,
            });
        }
        if (catCols.length > 0 && numCols.length > 0) {
            examples.push({
                label: `Group by ${catCols[0].name}`,
                query: `SELECT "${catCols[0].name}",\n  COUNT(*) AS count,\n  AVG("${numCols[0].name}") AS avg_${numCols[0].name}\nFROM data\nGROUP BY "${catCols[0].name}"\nORDER BY count DESC`,
            });
        }

        container.innerHTML = examples.map(ex =>
            `<button class="sql-example text-xs px-2 py-1 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:border-brand-400 transition-colors" data-query="${ex.query.replace(/"/g, '&quot;')}">${ex.label}</button>`
        ).join('');

        // Re-bind example buttons
        container.querySelectorAll('.sql-example').forEach(btn => {
            btn.addEventListener('click', () => {
                document.getElementById('sql-editor').value = btn.dataset.query;
                this.runQuery();
            });
        });
    },

    async ensureLoaded() {
        if (this.loaded) return true;

        const status = document.getElementById('sql-status');
        status.textContent = 'Loading DuckDB engine...';
        status.className = 'text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300';

        try {
            // Dynamic import DuckDB-WASM
            const DUCKDB_CDN = 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/dist';
            const { default: duckdb_init, ConsoleLogger, selectBundle } = await import(`${DUCKDB_CDN}/duckdb-browser-blocking.mjs`);

            const JSDELIVR_BUNDLES = {
                mvp: {
                    mainModule: `${DUCKDB_CDN}/duckdb-mvp.wasm`,
                    mainWorker: `${DUCKDB_CDN}/duckdb-browser-mvp.worker.js`,
                },
                eh: {
                    mainModule: `${DUCKDB_CDN}/duckdb-eh.wasm`,
                    mainWorker: `${DUCKDB_CDN}/duckdb-browser-eh.worker.js`,
                },
            };

            status.textContent = 'Initializing DuckDB...';

            // Use async API instead of blocking
            const { default: duckdb_async } = await import(`${DUCKDB_CDN}/duckdb-browser.mjs`);
            const bundle = await selectBundle(JSDELIVR_BUNDLES);
            const worker = new Worker(bundle.mainWorker);
            const logger = new ConsoleLogger();
            this.db = new duckdb_async(logger, worker);
            await this.db.instantiate(bundle.mainModule);
            this.conn = await this.db.connect();

            // Fetch CSV and register it
            status.textContent = 'Loading CSV data...';
            const csvResp = await fetch('/api/csv/raw');
            if (!csvResp.ok) throw new Error('Failed to fetch CSV');
            const csvText = await csvResp.text();

            await this.db.registerFileText('data.csv', csvText);
            await this.conn.query(`CREATE TABLE data AS SELECT * FROM read_csv_auto('data.csv')`);

            this.loaded = true;
            status.textContent = 'Ready';
            status.className = 'text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300';
            return true;
        } catch (err) {
            console.error('DuckDB init error:', err);
            status.textContent = 'Load failed';
            status.className = 'text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300';
            document.getElementById('sql-result').innerHTML =
                `<p class="text-red-500 text-sm">Failed to initialize DuckDB: ${err.message}</p>
                 <p class="text-xs text-gray-500 mt-1">This feature requires a modern browser with WebAssembly support.</p>`;
            return false;
        }
    },

    async runQuery() {
        const editor = document.getElementById('sql-editor');
        const resultDiv = document.getElementById('sql-result');
        const runBtn = document.getElementById('sql-run');
        const query = editor.value.trim();

        if (!query) {
            resultDiv.innerHTML = '<p class="text-amber-500 text-sm">Enter a SQL query to run.</p>';
            return;
        }

        runBtn.disabled = true;
        runBtn.innerHTML = '<svg class="animate-spin w-4 h-4 inline mr-1" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/></svg>Running...';
        resultDiv.innerHTML = '<p class="text-gray-400 text-sm">Executing query...</p>';

        const ready = await this.ensureLoaded();
        if (!ready) {
            runBtn.disabled = false;
            runBtn.textContent = 'Run (Ctrl+Enter)';
            return;
        }

        const start = performance.now();
        try {
            const result = await this.conn.query(query);
            const elapsed = ((performance.now() - start) / 1000).toFixed(3);

            const columns = result.schema.fields.map(f => f.name);
            const rows = result.toArray().map(row => {
                const obj = row.toJSON();
                return columns.map(c => obj[c]);
            });

            this.renderResult(columns, rows, elapsed);
        } catch (err) {
            const elapsed = ((performance.now() - start) / 1000).toFixed(3);
            resultDiv.innerHTML = `<div class="text-red-500 text-sm"><p class="font-semibold">Query Error</p><pre class="mt-1 text-xs bg-red-50 dark:bg-red-950 p-2 rounded overflow-x-auto">${this.escapeHtml(err.message)}</pre><p class="text-xs text-gray-500 mt-2">${elapsed}s</p></div>`;
        }

        runBtn.disabled = false;
        runBtn.textContent = 'Run (Ctrl+Enter)';
    },

    renderResult(columns, rows, elapsed) {
        const resultDiv = document.getElementById('sql-result');
        const maxDisplay = 500;
        const truncated = rows.length > maxDisplay;
        const displayRows = truncated ? rows.slice(0, maxDisplay) : rows;

        let html = `<div class="flex items-center justify-between mb-2">
            <span class="text-xs text-gray-500">${rows.length} row${rows.length !== 1 ? 's' : ''} ${truncated ? `(showing ${maxDisplay})` : ''} &middot; ${elapsed}s</span>
            <button id="sql-export" class="text-xs text-brand-600 hover:underline">Export CSV</button>
        </div>`;

        html += '<div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800 max-h-[400px] overflow-y-auto">';
        html += '<table class="text-xs w-full"><thead class="bg-gray-100 dark:bg-gray-800 sticky top-0"><tr>';
        columns.forEach(c => {
            html += `<th class="px-3 py-2 text-left font-medium whitespace-nowrap">${this.escapeHtml(String(c))}</th>`;
        });
        html += '</tr></thead><tbody class="divide-y divide-gray-100 dark:divide-gray-800">';

        displayRows.forEach(row => {
            html += '<tr class="hover:bg-gray-50 dark:hover:bg-gray-800/50">';
            row.forEach(v => {
                const val = v != null ? String(v) : '<span class="text-gray-300">NULL</span>';
                html += `<td class="px-3 py-1.5 whitespace-nowrap">${v != null ? this.escapeHtml(String(v)) : '<span class="text-gray-300 italic">NULL</span>'}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table></div>';
        resultDiv.innerHTML = html;

        // Export button
        document.getElementById('sql-export')?.addEventListener('click', () => {
            this.exportCSV(columns, rows);
        });
    },

    exportCSV(columns, rows) {
        const csvContent = [
            columns.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','),
            ...rows.map(row =>
                row.map(v => v != null ? `"${String(v).replace(/"/g, '""')}"` : '').join(',')
            )
        ].join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'query_result.csv';
        a.click();
        URL.revokeObjectURL(url);
    },

    escapeHtml(text) {
        const el = document.createElement('span');
        el.textContent = text;
        return el.innerHTML;
    }
};
