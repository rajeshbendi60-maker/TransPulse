window.TransPulseTrackingHistory = {
    storageKey: 'transpulse_live_tracking_history',

    escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },

    read() {
        try {
            const records = JSON.parse(localStorage.getItem(this.storageKey) || '[]');
            return Array.isArray(records) ? records : [];
        } catch (e) {
            return [];
        }
    },

    write(records) {
        localStorage.setItem(this.storageKey, JSON.stringify(records.slice(0, 25)));
    },

    normalizeStatus(bus) {
        const rawStatus = String(bus.status || '').toLowerCase();
        const delayStatus = String(bus.delay_status || bus.schedule_status || '').toLowerCase();
        const delayMinutes = Number(bus.current_delay_minutes || 0);

        if (rawStatus.includes('completed') || rawStatus.includes('arrived terminal')) {
            return 'Completed';
        }

        if (bus.service_status === 'delayed' || delayMinutes > 0 || (delayStatus && !delayStatus.includes('on time'))) {
            return 'Delayed';
        }

        return 'In Progress';
    },

    saveFromBus(bus) {
        if (!bus || (!bus.bus_number && !bus.bus_id)) return;

        const busId = String(bus.bus_number || bus.bus_id).trim();
        if (!busId) return;

        const records = this.read().filter(record => String(record.busId || '').toLowerCase() !== busId.toLowerCase());
        records.unshift({
            busId,
            route: bus.route_name || 'Assigned Route',
            source: bus.source_stop || '--',
            destination: bus.destination_stop || '--',
            trackedAt: new Date().toISOString(),
            status: this.normalizeStatus(bus)
        });

        this.write(records);
        this.renderAll();
    },

    statusClass(status) {
        if (status === 'Delayed') return 'tracking-status-delayed';
        if (status === 'Completed') return 'tracking-status-completed';
        return 'tracking-status-progress';
    },

    formatTime(value) {
        if (!value) return '--';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return '--';
        return date.toLocaleString([], {
            year: 'numeric',
            month: 'short',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    deleteRecord(busId) {
        const records = this.read().filter(record => String(record.busId || '') !== String(busId || ''));
        this.write(records);
        this.renderAll();
    },

    renderPanel(panel) {
        const body = panel.querySelector('[data-tracking-history-body]');
        const empty = panel.querySelector('[data-tracking-history-empty]');
        const tableWrap = panel.querySelector('[data-tracking-history-table]');
        if (!body || !tableWrap) return;

        if (empty) empty.classList.add('d-none');
        tableWrap.classList.remove('d-none');

        const records = this.read();
        if (!records.length) {
            body.innerHTML = `
                <tr>
                    <td colspan="6" class="tracking-history-empty">No recently tracked vehicles.</td>
                </tr>`;
            return;
        }

        body.innerHTML = records.map(record => {
            const busId = this.escapeHtml(record.busId || '--');
            const route = this.escapeHtml(record.route || '--');
            const source = this.escapeHtml(record.source || '--');
            const destination = this.escapeHtml(record.destination || '--');
            const status = record.status || 'In Progress';
            const statusText = this.escapeHtml(status);
            const trackedAt = this.escapeHtml(this.formatTime(record.trackedAt));
            const encodedBus = encodeURIComponent(record.busId || '');

            return `
                <tr>
                    <td class="fw-bold text-white">${busId}</td>
                    <td>${route}</td>
                    <td>${source} <span class="text-info">&rarr;</span> ${destination}</td>
                    <td>${trackedAt}</td>
                    <td><span class="tracking-status-badge ${this.statusClass(status)}">${statusText}</span></td>
                    <td>
                        <div class="d-flex flex-wrap gap-2">
                            <a class="tracking-history-action" href="/tracking/${encodedBus}">View</a>
                            <button type="button" class="tracking-history-action tracking-history-action-delete" data-delete-tracking-history="${busId}">Delete</button>
                        </div>
                    </td>
                </tr>`;
        }).join('');
    },

    renderAll() {
        document.querySelectorAll('[data-tracking-history-panel]').forEach(panel => this.renderPanel(panel));
    },

    init() {
        this.renderAll();
        document.addEventListener('click', event => {
            const deleteButton = event.target.closest('[data-delete-tracking-history]');
            if (!deleteButton) return;
            event.preventDefault();
            this.deleteRecord(deleteButton.getAttribute('data-delete-tracking-history'));
        });
    }
};

document.addEventListener('DOMContentLoaded', () => {
    if (window.TransPulseTrackingHistory) window.TransPulseTrackingHistory.init();
});
