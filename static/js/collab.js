/**
 * Real-time Collaboration Module
 *
 * Connects to SocketIO for multi-user shared exploration.
 * Gracefully degrades if SocketIO is unavailable.
 */
const Collab = {
    socket: null,
    roomId: null,
    participants: [],
    enabled: false,

    init() {
        this.bindEvents();
        this.checkUrlRoom();
    },

    bindEvents() {
        document.getElementById('collab-create')?.addEventListener('click', () => this.createRoom());
        document.getElementById('collab-join')?.addEventListener('click', () => this.joinPrompt());
        document.getElementById('collab-leave')?.addEventListener('click', () => this.leave());
        document.getElementById('collab-share-link')?.addEventListener('click', () => this.copyLink());
    },

    checkUrlRoom() {
        const params = new URLSearchParams(window.location.search);
        const roomId = params.get('room');
        if (roomId) {
            document.getElementById('collab-room-input').value = roomId;
            this.join(roomId);
        }
    },

    async createRoom() {
        try {
            const resp = await fetch('/api/collab/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: this.getUsername() }),
            });
            const data = await resp.json();
            this.roomId = data.room_id;
            this.enabled = data.websocket;

            if (this.enabled) {
                this.connectSocket();
            }
            this.updateUI('connected');
            this.showNotice(`Room created: ${data.room_id}`);
        } catch (err) {
            this.showNotice('Failed to create room: ' + err.message, 'error');
        }
    },

    joinPrompt() {
        const input = document.getElementById('collab-room-input');
        const roomId = input?.value.trim();
        if (!roomId) {
            this.showNotice('Enter a room ID to join.', 'warning');
            input?.focus();
            return;
        }
        this.join(roomId);
    },

    async join(roomId) {
        try {
            const resp = await fetch(`/api/collab/${encodeURIComponent(roomId)}/info`);
            if (!resp.ok) {
                // Room doesn't exist, create it
                this.roomId = roomId;
                await this.createRoomWithId(roomId);
                return;
            }
            const data = await resp.json();
            this.roomId = roomId;
            this.enabled = data.websocket;
            this.participants = data.participants;

            if (this.enabled) {
                this.connectSocket();
            }
            this.updateUI('connected');
            this.renderParticipants();
            this.showNotice(`Joined room: ${roomId}`);
        } catch (err) {
            this.showNotice('Failed to join: ' + err.message, 'error');
        }
    },

    async createRoomWithId(roomId) {
        try {
            const resp = await fetch('/api/collab/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: this.getUsername() }),
            });
            const data = await resp.json();
            this.roomId = data.room_id;
            this.enabled = data.websocket;
            if (this.enabled) this.connectSocket();
            this.updateUI('connected');
            this.showNotice(`Room created: ${data.room_id}`);
        } catch (err) {
            this.showNotice('Failed: ' + err.message, 'error');
        }
    },

    connectSocket() {
        if (this.socket) this.socket.disconnect();

        // Load socket.io client dynamically
        if (typeof io === 'undefined') {
            const script = document.createElement('script');
            script.src = 'https://cdn.socket.io/4.7.5/socket.io.min.js';
            script.onload = () => this._initSocket();
            document.head.appendChild(script);
        } else {
            this._initSocket();
        }
    },

    _initSocket() {
        this.socket = io({ transports: ['websocket', 'polling'] });

        this.socket.on('connect', () => {
            this.socket.emit('join', {
                room: this.roomId,
                name: this.getUsername(),
            });
        });

        this.socket.on('user_joined', (data) => {
            this.participants = data.participants;
            this.renderParticipants();
            this.showNotice(`${data.name} joined`, 'info');
        });

        this.socket.on('user_left', (data) => {
            this.participants = data.participants;
            this.renderParticipants();
        });

        this.socket.on('tab_changed', (data) => {
            // Show indicator of what tab other users are viewing
            this.updateParticipantTab(data.sid, data.tab);
        });

        this.socket.on('chart_received', (data) => {
            this.showNotice('A collaborator shared a chart configuration.', 'info');
        });

        this.socket.on('chat_broadcast', (data) => {
            this.addChatMessage(data);
        });

        // Track local tab changes
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                if (this.socket && this.roomId) {
                    this.socket.emit('tab_change', {
                        room: this.roomId,
                        tab: btn.dataset.tab,
                    });
                }
            });
        });
    },

    leave() {
        if (this.socket) {
            this.socket.emit('leave', { room: this.roomId });
            this.socket.disconnect();
            this.socket = null;
        }
        this.roomId = null;
        this.participants = [];
        this.enabled = false;
        this.updateUI('disconnected');
        this.renderParticipants();
    },

    copyLink() {
        if (!this.roomId) return;
        const url = `${window.location.origin}${window.location.pathname}?room=${encodeURIComponent(this.roomId)}`;
        navigator.clipboard.writeText(url).then(() => {
            this.showNotice('Link copied!');
        }).catch(() => {
            prompt('Copy this link:', url);
        });
    },

    updateUI(state) {
        const createBtn = document.getElementById('collab-create');
        const joinSection = document.getElementById('collab-join-section');
        const activeSection = document.getElementById('collab-active-section');
        const roomDisplay = document.getElementById('collab-room-display');

        if (state === 'connected') {
            if (joinSection) joinSection.style.display = 'none';
            if (activeSection) activeSection.style.display = '';
            if (roomDisplay) roomDisplay.textContent = this.roomId;
        } else {
            if (joinSection) joinSection.style.display = '';
            if (activeSection) activeSection.style.display = 'none';
        }
    },

    renderParticipants() {
        const container = document.getElementById('collab-participants');
        if (!container) return;

        if (this.participants.length === 0) {
            container.innerHTML = '<span class="text-xs text-gray-400">No one here yet</span>';
            return;
        }

        container.innerHTML = this.participants.map(p =>
            `<span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full" style="background: ${p.color}20; color: ${p.color}">
                <span class="w-2 h-2 rounded-full" style="background: ${p.color}"></span>
                ${this.escapeHtml(p.name)}
            </span>`
        ).join(' ');
    },

    updateParticipantTab(sid, tab) {
        // Visual indicator (could be enhanced)
        const participant = this.participants.find(p => p.sid === sid);
        if (participant) {
            participant.currentTab = tab;
        }
    },

    addChatMessage(data) {
        const container = document.getElementById('collab-chat-messages');
        if (!container) return;
        const msg = document.createElement('div');
        msg.className = 'text-xs p-2 rounded bg-gray-50 dark:bg-gray-800';
        msg.innerHTML = `<span class="font-medium" style="color: ${data.color}">${this.escapeHtml(data.name)}</span>: ${this.escapeHtml(data.message)}`;
        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;
    },

    showNotice(msg, type = 'success') {
        const area = document.getElementById('collab-notices');
        if (!area) return;
        const colors = { success: 'text-green-600', warning: 'text-amber-600', error: 'text-red-600', info: 'text-brand-600' };
        area.innerHTML = `<span class="text-xs ${colors[type] || colors.success}">${this.escapeHtml(msg)}</span>`;
        setTimeout(() => { if (area.textContent === msg) area.innerHTML = ''; }, 4000);
    },

    getUsername() {
        return localStorage.getItem('collab_name') || 'User ' + Math.floor(Math.random() * 1000);
    },

    escapeHtml(text) {
        const el = document.createElement('span');
        el.textContent = text;
        return el.innerHTML;
    },
};
