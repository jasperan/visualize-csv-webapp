/**
 * AI Chat module — talk to your CSV via Ollama
 */
const Chat = {
    messagesEl: null,
    inputEl: null,
    formEl: null,
    busy: false,

    init() {
        this.messagesEl = document.getElementById('chat-messages');
        this.inputEl = document.getElementById('chat-input');
        this.formEl = document.getElementById('chat-form');

        if (!this.formEl) return;

        this.formEl.addEventListener('submit', e => {
            e.preventDefault();
            this.send();
        });

        // Click-to-ask suggestions
        document.querySelectorAll('.chat-suggestion').forEach(el => {
            el.addEventListener('click', () => {
                this.inputEl.value = el.textContent.replace(/^"|"$/g, '');
                this.send();
            });
        });

        // Chat toggle for small screens
        const toggle = document.getElementById('chat-toggle');
        const sidebar = document.getElementById('chat-sidebar');
        if (toggle && sidebar) {
            toggle.addEventListener('click', () => {
                sidebar.classList.toggle('hidden');
                sidebar.classList.toggle('fixed');
                sidebar.classList.toggle('inset-0');
                sidebar.classList.toggle('z-50');
                sidebar.classList.toggle('w-full');
            });
        }

        this.checkOllama();
    },

    async checkOllama() {
        const badge = document.getElementById('ollama-status');
        if (!badge) return;
        try {
            const resp = await fetch('/api/ollama/status');
            const data = await resp.json();
            if (data.available) {
                badge.textContent = 'online';
                badge.className = 'text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300';
            } else {
                badge.textContent = 'offline';
                badge.className = 'text-xs px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300';
            }
        } catch {
            badge.textContent = 'offline';
            badge.className = 'text-xs px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300';
        }
    },

    addMessage(role, content) {
        const div = document.createElement('div');
        div.className = 'chat-msg text-sm rounded-lg p-3 ' +
            (role === 'user'
                ? 'bg-brand-600 text-white ml-8'
                : 'bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-300 mr-4');
        div.innerHTML = content;
        this.messagesEl.appendChild(div);
        this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
        return div;
    },

    async send() {
        const question = this.inputEl.value.trim();
        if (!question || this.busy) return;

        this.busy = true;
        this.inputEl.value = '';
        this.addMessage('user', this.escapeHtml(question));

        const thinkingEl = this.addMessage('assistant',
            '<div class="flex items-center gap-2"><svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/></svg> Thinking...</div>'
        );

        try {
            const resp = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question }),
            });
            const data = await resp.json();
            thinkingEl.remove();

            let html = `<p>${this.escapeHtml(data.answer || 'No answer returned.')}</p>`;

            if (data.computed) {
                html += `<div class="mt-2 px-2 py-1 bg-brand-600/10 rounded text-xs font-mono">${this.escapeHtml(data.computed)}</div>`;
            }

            if (data.code) {
                html += `<details class="mt-2"><summary class="text-xs text-gray-400 cursor-pointer">Show code</summary><pre class="mt-1 text-xs bg-gray-100 dark:bg-gray-900 p-2 rounded overflow-x-auto">${this.escapeHtml(data.code)}</pre></details>`;
            }

            if (data.table) {
                html += this.renderMiniTable(data.table);
            }

            if (data.exec_error) {
                html += `<p class="mt-2 text-xs text-red-500">Execution error: ${this.escapeHtml(data.exec_error)}</p>`;
            }

            const msgEl = this.addMessage('assistant', html);

            if (data.chart) {
                Charts.renderDynamic(msgEl, data.chart);
            }

        } catch (err) {
            thinkingEl.remove();
            this.addMessage('assistant', `<p class="text-red-500">Error: ${this.escapeHtml(err.message)}</p>`);
        }

        this.busy = false;
    },

    renderMiniTable(table) {
        let html = '<div class="mt-2 overflow-x-auto"><table class="text-xs w-full">';
        html += '<thead><tr>' + table.columns.map(c => `<th class="px-2 py-1 text-left bg-gray-100 dark:bg-gray-800">${this.escapeHtml(String(c))}</th>`).join('') + '</tr></thead>';
        html += '<tbody>';
        for (const row of table.rows.slice(0, 20)) {
            html += '<tr>' + row.map(v => `<td class="px-2 py-1 border-t border-gray-200 dark:border-gray-700">${this.escapeHtml(String(v ?? ''))}</td>`).join('') + '</tr>';
        }
        if (table.rows.length > 20) {
            html += `<tr><td colspan="${table.columns.length}" class="px-2 py-1 text-gray-400 text-center">...and ${table.rows.length - 20} more rows</td></tr>`;
        }
        html += '</tbody></table></div>';
        return html;
    },

    escapeHtml(text) {
        const el = document.createElement('span');
        el.textContent = text;
        return el.innerHTML;
    }
};
