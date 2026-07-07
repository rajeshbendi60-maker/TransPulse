/* ==============================================================
   SOS HANDLING LOGIC: Passenger & Admin
   ============================================================== */
window.SOSHandler = {
    isActive: false,
    countdownInterval: null,
    elapsedInterval: null,
    statusInterval: null,
    activeAlertId: null,
    activeStartedAt: null,
    isSubmitting: false,
    initialized: false,
    
    init: function() {
        if (this.initialized) return;
        const sosButton = document.getElementById('sos-trigger-btn');
        const cancelButton = document.getElementById('sos-cancel-btn');
        const confirmButton = document.getElementById('sos-confirm-btn');
        if (!sosButton && !cancelButton && !confirmButton) return;
        this.initialized = true;
        if (sosButton) sosButton.addEventListener('click', () => this.triggerSOS());
        if (cancelButton) cancelButton.addEventListener('click', () => this.cancelSOS());
        if (confirmButton) confirmButton.addEventListener('click', () => this.confirmSOS());
    },
    
    triggerSOS: function() {
        this.isActive = true;
        document.getElementById('sos-confirmation-modal').style.display = 'flex';
        this.startCountdown();
    },
    
    closeActiveSOSDialogs: function() {
        const premiumModal = document.getElementById('sos-premium-modal');
        const standardModal = document.getElementById('sos-confirmation-modal');
        if (premiumModal) premiumModal.style.display = 'none';
        if (standardModal) standardModal.style.display = 'none';
        document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
        document.documentElement.style.overflow = '';
    },

    closeSuccessModal: function() {
        const modal = document.getElementById('sosSuccessModal');
        if (modal) modal.style.display = 'none';
        this.stopElapsedTimer();
        this.closeActiveSOSDialogs();
    },

    cancelSOS: function() {
        this.isActive = false;
        this.isSubmitting = false;
        clearInterval(this.countdownInterval);
        this.closeActiveSOSDialogs();
    },

    escapeHtml: function(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },

    formatElapsed: function(totalSeconds) {
        const safeSeconds = Math.max(0, Number(totalSeconds) || 0);
        const minutes = String(Math.floor(safeSeconds / 60)).padStart(2, '0');
        const seconds = String(safeSeconds % 60).padStart(2, '0');
        return `${minutes}:${seconds}`;
    },

    stopElapsedTimer: function() {
        clearInterval(this.elapsedInterval);
        clearInterval(this.statusInterval);
        this.elapsedInterval = null;
        this.statusInterval = null;
    },

    startElapsedTimer: function(alertId, startedAt) {
        this.stopElapsedTimer();
        this.activeAlertId = alertId;
        this.activeStartedAt = startedAt ? new Date(startedAt) : new Date();
        if (Number.isNaN(this.activeStartedAt.getTime())) this.activeStartedAt = new Date();
        const tick = () => {
            const timer = document.getElementById('sos-elapsed-timer');
            if (!timer) return;
            const elapsedSeconds = Math.floor((Date.now() - this.activeStartedAt.getTime()) / 1000);
            timer.textContent = this.formatElapsed(elapsedSeconds);
        };
        tick();
        this.elapsedInterval = setInterval(tick, 1000);
        if (!alertId) return;
        this.statusInterval = setInterval(() => {
            fetch(`/api/sos/${alertId}/status`)
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    if (!data || data.timer_active) return;
                    this.stopElapsedTimer();
                    const statusText = document.getElementById('sos-response-status');
                    if (statusText) {
                        statusText.textContent = (data.status || '').toLowerCase() === 'resolved'
                            ? 'Resolved by Admin'
                            : 'Acknowledged by Driver';
                    }
                })
                .catch(() => {});
        }, 3000);
    },

    showSuccessModal: function(data) {
        const payload = data || {};
        const referenceId = payload.id ? `SOS-${String(payload.id).padStart(5, '0')}` : 'SOS-PENDING';
        const emergencyType = payload.emergency_type || payload.reason || 'Emergency';
        this.closeActiveSOSDialogs();
        let modal = document.getElementById('sosSuccessModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'sosSuccessModal';
            document.body.appendChild(modal);
        }
        modal.style.cssText = 'display:none; position:fixed; inset:0; width:100vw; height:100vh; background:rgba(24,5,10,0.78); z-index:200001; align-items:center; justify-content:center; backdrop-filter: blur(10px); padding:18px;';

        modal.innerHTML = `
            <div class="card glass-panel shadow-lg" style="width:100%; max-width:440px; border:1px solid rgba(255,93,108,0.72); border-radius:16px; background: linear-gradient(135deg, rgba(28,6,16,0.98), rgba(4,11,24,0.98)); box-shadow: 0 0 0 1px rgba(255,93,108,0.3), 0 0 44px rgba(255,93,108,0.34), 0 28px 80px -34px rgba(0,0,0,0.95); animation: sosModalRise .28s ease-out;">
                <div class="card-body p-4 p-md-5 text-center">
                    <div style="background: linear-gradient(135deg, #ff5d6c, #ff9f43); border-radius: 16px; width: 76px; height: 76px; display: flex; align-items: center; justify-content: center; margin: 0 auto 22px auto; box-shadow: 0 0 30px rgba(255,93,108,0.55); animation: sosGlowPulse 1.8s ease-in-out infinite;">
                        <span style="font-size: 2.25rem;">&#128680;</span>
                    </div>
                    <h3 class="text-white fw-bold mb-3">SOS Sent Successfully</h3>
                    <div class="text-start mb-4 p-3" style="background: rgba(255,93,108,0.08); border:1px solid rgba(255,93,108,0.28); border-radius:12px;">
                        <p class="text-muted small mb-1">Emergency Type:</p>
                        <p class="text-light fw-bold mb-3">${this.escapeHtml(emergencyType)}</p>
                        <p class="text-light mb-1">Driver Notified</p>
                        <p class="text-light mb-0">Admin Notified</p>
                    </div>
                    <p class="text-muted small mb-1">Reference ID</p>
                    <p class="fw-bold fs-5 mb-3" style="color:#ff9f43;" id="sos-success-ref">${referenceId}</p>
                    <p class="text-muted small mb-1">Elapsed Time</p>
                    <p class="fw-bold display-6 mb-2" style="color:#ff9f43; font-family:monospace;" id="sos-elapsed-timer">00:00</p>
                    <p class="text-muted small mb-4" id="sos-response-status">Emergency response is being arranged.</p>
                    <button type="button" id="sos-success-close-btn" class="btn fw-bold px-5 py-2 rounded-pill" style="background: linear-gradient(135deg, #ff5d6c, #ff9f43); color:#18050a; border:0; box-shadow: 0 0 24px rgba(255,93,108,0.38);">Got It</button>
                </div>
            </div>`;
        const closeBtn = modal.querySelector('#sos-success-close-btn');
        if (closeBtn) closeBtn.addEventListener('click', () => this.closeSuccessModal(), { once: true });
        modal.style.display = 'flex';
        this.startElapsedTimer(payload.id, payload.triggered_at);
    },
    
    confirmSOS: function() {
        if(this.isSubmitting) return; // Prevent duplicate requests
        this.isSubmitting = true;

        clearInterval(this.countdownInterval);
        const reasonEl = document.getElementById('sos-reason');
        const reason = reasonEl && reasonEl.value ? reasonEl.value : 'Other Emergency';
        const busIdEl = document.getElementById('active-bus-id');
        const busId = busIdEl ? busIdEl.value : null;
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || window.TransPulseCSRF || '';
        
        fetch('/api/sos/trigger', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
            body: JSON.stringify({ bus_id: busId, emergency_type: reason, severity: 'critical' })
        })
        .then(async r => {
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(data.error || 'Unable to send SOS alert.');
            return data;
        })
        .then(data => {
            this.isSubmitting = false;
            this.cancelSOS();
            if(data.message || data.id) {
                this.showSuccessModal(data);
            }
        })
        .catch(() => {
            this.isSubmitting = false;
            this.cancelSOS();
        });
    },

    startCountdown: function() {
        let count = 10;
        const timer = document.getElementById('sos-timer');
        if (timer) timer.textContent = count;
        this.countdownInterval = setInterval(() => {
            count--;
            if (timer) timer.textContent = count;
            if (count <= 0) { clearInterval(this.countdownInterval); this.confirmSOS(); }
        }, 1000);
    }
};

window.AdminSOS = {
    interval: null,
    alarmInterval: null,
    triggeredAlertIds: new Set(),
    audioContext: null,
    initialized: false,

    init: function() {
        if (!document.getElementById('admin-sos-container')) return;
        if (this.initialized) return;
        this.initialized = true;
        const AudioCtor = window.AudioContext || window.webkitAudioContext;
        if (AudioCtor) {
            this.audioContext = new AudioCtor();
            document.addEventListener('click', () => this.unlockAudio(), { once: true });
        }
        this.loadAlerts();
        this.interval = setInterval(() => { if (!document.hidden) this.loadAlerts(); }, 5000);
    },

    unlockAudio: function() {
        if (this.audioContext && this.audioContext.state === 'suspended') {
            this.audioContext.resume().catch(() => {});
        }
    },

    playAlertSound: function() {
        if (!this.audioContext) return;
        if (this.audioContext.state === 'suspended') {
            this.audioContext.resume().catch(() => {});
        }
        const osc = this.audioContext.createOscillator();
        const gain = this.audioContext.createGain();
        osc.connect(gain);
        gain.connect(this.audioContext.destination);
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.001, this.audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.18, this.audioContext.currentTime + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.001, this.audioContext.currentTime + 0.45);
        osc.start();
        osc.stop(this.audioContext.currentTime + 0.5);
    },

    startAlarm: function() {
        if (this.alarmInterval) return;
        this.playAlertSound();
        this.alarmInterval = setInterval(() => this.playAlertSound(), 1200);
    },

    stopAlarm: function() {
        if (!this.alarmInterval) return;
        clearInterval(this.alarmInterval);
        this.alarmInterval = null;
    },

    loadAlerts: function() {
        fetch('/api/admin/sos')
            .then(r => {
                if (!r.ok) throw new Error('SOS fetch failed');
                return r.json();
            })
            .then(data => {
                const alerts = data.alerts || [];
                const container = document.getElementById('admin-sos-container');
                if (!alerts.length && container && container.dataset.driverSosFallback === 'true') {
                    this.stopAlarm();
                    this.renderAlerts([]);
                    return;
                }
                const hasActiveAlert = alerts.length > 0;
                if (hasActiveAlert) this.startAlarm();
                else this.stopAlarm();

                alerts.forEach(a => {
                    if (!this.triggeredAlertIds.has(a.id) && ['active', 'new'].includes((a.status || 'NEW').toLowerCase())) {
                        this.triggeredAlertIds.add(a.id);
                        this.triggerEmergencyPopup(a);
                    }
                });
                this.renderAlerts(alerts);
            })
            .catch(() => this.stopAlarm());
    },

    loadDriverNotificationSOSFallback: function() {
        const container = document.getElementById('admin-sos-container');
        const assignedBusNumber = (container && container.dataset.assignedBusNumber || '').trim().toUpperCase();
        return fetch('/api/notifications')
            .then(r => {
                if (!r.ok) throw new Error('Notification SOS fetch failed');
                return r.json();
            })
            .then(data => {
                const alerts = (data.notifications || [])
                    .filter(n => /SOS|EMERGENCY|DISTRESS/i.test(`${n.title || ''} ${n.message || ''}`))
                    .filter(n => !n.is_read)
                    .map(n => this.alertFromNotification(n));
                const filteredAlerts = assignedBusNumber
                    ? alerts.filter(a => String(a.bus_number || '').trim().toUpperCase() === assignedBusNumber)
                    : alerts;

                const hasActiveAlert = filteredAlerts.some(a => ['active', 'new'].includes((a.status || 'NEW').toLowerCase()));
                if (hasActiveAlert) this.startAlarm();
                else this.stopAlarm();

                filteredAlerts.forEach(a => {
                    if (!this.triggeredAlertIds.has(a.id)) {
                        this.triggeredAlertIds.add(a.id);
                        this.triggerEmergencyPopup(a);
                    }
                });
                this.renderAlerts(filteredAlerts);
            })
            .catch(() => {
                this.stopAlarm();
                this.renderAlerts([]);
            });
    },

    alertFromNotification: function(notification) {
        const message = notification.message || '';
        const match = message.match(/\[SOS[^\]]*\]\s*([^:]+):\s*(.*?)(?:\s+(?:-|\u2014)\s+passenger\s+(.+?)\s+needs|\s*$)/i);
        return {
            id: `notification-${notification.id}`,
            passenger_name: (match && match[3]) || 'Passenger',
            bus_number: (match && match[1] ? match[1].trim() : 'Assigned Bus'),
            route_name: 'Assigned Route',
            reason: (match && match[2] ? match[2].trim() : 'Emergency'),
            severity: 'critical',
            status: 'active',
            triggered_at: notification.timestamp || '',
            can_resolve: false
        };
    },

    triggerEmergencyPopup: function(a) {
        this.playAlertSound();
        const body = document.getElementById('sos-modal-body');
        const modalEl = document.getElementById('sosEmergencyModal');
        if (!body || !modalEl) return;

        const reporterLabel = a.reporter_role === 'driver' ? 'Driver' : 'Passenger';
        body.innerHTML = `
            <p><strong>${this.escapeHtml(reporterLabel)}:</strong> ${this.escapeHtml(a.passenger_name || 'Unknown')}</p>
            <p><strong>Bus:</strong> ${this.escapeHtml(a.bus_number || 'Unknown')}</p>
            <p><strong>Route:</strong> ${this.escapeHtml(a.route_name || 'Unknown')}</p>
            <p><strong>Issue:</strong> ${this.escapeHtml(a.reason || 'Emergency')}</p>
        `;
        
        const ackBtn = document.getElementById('modal-ack-btn');
        if (ackBtn) ackBtn.onclick = () => this.updateStatus(a.id, 'acknowledged');
        
        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            const modal = new bootstrap.Modal(modalEl);
            modal.show();
        }
    },

    hideModal: function() {
        const modalEl = document.getElementById('sosEmergencyModal');
        if (!modalEl) return;
        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        }
        document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
    },

    updateStatus: function(id, status) {
        const alertId = String(id).replace('notification-', '');
        const rawId = String(id);
        if (status === 'acknowledged' || rawId.startsWith('notification-')) {
            fetch(`/api/sos/driver/acknowledge/${alertId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
                }
            }).finally(() => {
                this.hideModal();
                this.closeDetailModal();
                this.loadAlerts();
            });
            return;
        }
        fetch(`/api/sos/resolve/${alertId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify({ resolution_notes: 'Resolved by Admin' })
        }).then(() => {
            this.hideModal(); 
            this.closeDetailModal();
            this.loadAlerts(); 
        });
    },

    escapeHtml: function(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },

    formatAlertTime: function(value) {
        if (!value) return '--';
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return '--';
        return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },

    formatAlertDateTime: function(value) {
        if (!value) return '--';
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return '--';
        return parsed.toLocaleString([], {
            year: 'numeric',
            month: 'short',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    ensureDetailModal: function() {
        let modal = document.getElementById('sos-detail-modal');
        if (modal) return modal;
        modal = document.createElement('div');
        modal.id = 'sos-detail-modal';
        modal.style.cssText = 'display:none; position:fixed; inset:0; width:100vw; height:100vh; background:rgba(4,11,24,0.88); z-index:200010; align-items:center; justify-content:center; backdrop-filter:blur(8px); padding:18px;';
        modal.innerHTML = `
            <div class="card glass-panel shadow-lg" style="width:100%; max-width:520px; border:1px solid rgba(255,93,108,0.6); border-radius:16px; background:linear-gradient(135deg, rgba(28,6,16,0.98), rgba(4,11,24,0.98));">
                <div class="card-body p-4">
                    <div class="d-flex justify-content-between align-items-start gap-3 mb-3">
                        <div>
                            <h4 class="text-danger fw-bold mb-1">SOS Details</h4>
                            <p class="text-muted small mb-0" id="sos-detail-ref">SOS</p>
                        </div>
                        <button type="button" class="btn btn-sm btn-outline-light" onclick="window.AdminSOS.closeDetailModal()">Close</button>
                    </div>
                    <div id="sos-detail-body" class="small" style="color:#d9e8ff;"></div>
                    <div id="sos-detail-actions" class="d-flex gap-2 flex-wrap mt-4"></div>
                </div>
            </div>`;
        document.body.appendChild(modal);
        return modal;
    },

    closeDetailModal: function() {
        const modal = document.getElementById('sos-detail-modal');
        if (modal) modal.style.display = 'none';
    },

    openAlertDetails: function(alertJson) {
        const a = typeof alertJson === 'string' ? JSON.parse(alertJson) : alertJson;
        const modal = this.ensureDetailModal();
        const status = (a.status || 'NEW').toUpperCase();
        const statusLower = (a.status || 'NEW').toLowerCase();
        const locationText = a.latitude && a.longitude
            ? `${this.escapeHtml(Number(a.latitude).toFixed(5))}, ${this.escapeHtml(Number(a.longitude).toFixed(5))}`
            : 'Not available';
        const ref = modal.querySelector('#sos-detail-ref');
        const body = modal.querySelector('#sos-detail-body');
        const actions = modal.querySelector('#sos-detail-actions');
        if (ref) ref.textContent = `SOS-${String(a.id).padStart(5, '0')}`;
        if (body) {
            body.innerHTML = `
                <div class="mb-2"><span class="text-muted">${a.reporter_role === 'driver' ? 'Driver Name' : 'Passenger Name'}:</span> <span class="text-white fw-bold">${this.escapeHtml(a.passenger_name || 'Unknown')}</span></div>
                <div class="mb-2"><span class="text-muted">${a.reporter_role === 'driver' ? 'Driver ID' : 'Passenger ID'}:</span> <span class="text-white">${this.escapeHtml(a.passenger_id || '--')}</span></div>
                <div class="mb-2"><span class="text-muted">Bus ID:</span> <span class="text-white fw-bold">${this.escapeHtml(a.bus_number || 'Unknown')}</span></div>
                <div class="mb-2"><span class="text-muted">Emergency Type:</span> <span class="text-danger fw-bold">${this.escapeHtml(a.emergency_type || a.reason || 'Emergency')}</span></div>
                <div class="mb-2"><span class="text-muted">Time:</span> <span class="text-white">${this.escapeHtml(this.formatAlertDateTime(a.triggered_at))}</span></div>
                <div class="mb-2"><span class="text-muted">GPS Location:</span> <span class="text-white">${locationText}</span></div>
                <div><span class="text-muted">Status:</span> <span class="text-warning fw-bold">${this.escapeHtml(status)}</span></div>
            `;
        }
        if (actions) {
            const alertId = JSON.stringify(a.id);
            if (a.can_acknowledge && ['new', 'active'].includes(statusLower)) {
                actions.innerHTML = `<button class="btn btn-warning text-dark fw-bold" onclick='window.AdminSOS.updateStatus(${alertId}, "acknowledged")'>Acknowledge</button>`;
            } else if (a.can_resolve) {
                actions.innerHTML = `
                    <button class="btn btn-outline-info" onclick="window.location.href='/notifications'">Contact Passenger</button>
                    <button class="btn btn-outline-info" onclick="window.location.href='/notifications'">Contact Driver</button>
                    <button class="btn btn-danger fw-bold" onclick='window.AdminSOS.updateStatus(${alertId}, "resolved")'>Mark Resolved</button>`;
            } else {
                actions.innerHTML = '';
            }
        }
        modal.style.display = 'flex';
    },

    renderAlerts: function(alerts) {
        const container = document.getElementById('admin-sos-container');
        const badge = document.getElementById('sos-count-badge');
        if (!container) return;
        if (badge) {
            badge.textContent = `${alerts.length} ${alerts.length === 1 ? 'Alert' : 'Alerts'}`;
            badge.style.display = alerts.length > 0 ? 'inline-block' : 'none';
        }
        
        if (alerts.length === 0) {
            const emptyMessage = container.dataset.emptyMessage || 'Fleet Secure. No active SOS.';
            container.innerHTML = `<div class="text-center py-4" style="color: #22d39a; font-weight: 600;">${this.escapeHtml(emptyMessage)}</div>`;
            return;
        }

        let html = '<div style="display:flex; flex-direction:column; gap:12px;">';
        const isDriverView = container.dataset.driverSosFallback === 'true';
        alerts.forEach(a => {
            const color = a.severity === 'critical' ? '#ff5d6c' : '#f5b342';
            const status = (a.status || 'active').toUpperCase();
            const statusLower = (a.status || 'active').toLowerCase();
            const statusBadge = statusLower === 'acknowledged' ? 'bg-warning text-dark' : 'bg-danger';
            const statusTextClass = statusLower === 'acknowledged' ? 'text-warning' : 'text-danger';
            const alertTitle = statusLower === 'acknowledged' ? 'SOS ACKNOWLEDGED' : 'NEW SOS';
            const alertId = JSON.stringify(a.id);
            const alertPayload = this.escapeHtml(JSON.stringify(a));
            const actionsHtml = isDriverView
                ? `<button class="btn btn-sm btn-danger fw-bold" onclick='window.AdminSOS.openAlertDetails(${alertPayload})'>Open SOS</button>`
                : `<button class="btn btn-sm btn-outline-light" onclick='window.AdminSOS.openAlertDetails(${alertPayload})'>View SOS</button>
                   <button class="btn btn-sm btn-outline-info" onclick="window.location.href='/notifications'">Contact Passenger</button>
                   <button class="btn btn-sm btn-outline-info" onclick="window.location.href='/notifications'">Contact Driver</button>
                   ${a.can_resolve ? `<button class="btn btn-sm btn-danger fw-bold" onclick='window.AdminSOS.updateStatus(${alertId}, "resolved")'>Mark Resolved</button>` : ''}`;
            html += `<div style="border:1px solid rgba(255,93,108,0.45); border-left: 5px solid ${color}; background: linear-gradient(135deg, rgba(255,93,108,0.14), rgba(4,11,24,0.92)); padding: 16px; border-radius: 12px; box-shadow: 0 0 26px rgba(255,93,108,0.16);">
                        <div class="d-flex justify-content-between align-items-start gap-2 mb-2">
                            <div>
                                <div class="fw-bold ${statusTextClass} mb-1" style="letter-spacing:0.04em;">
                                    <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#ff2f45;box-shadow:0 0 0 0 rgba(255,47,69,0.72);animation:livePulse 1.35s ease-out infinite;margin-right:6px;"></span>
                                    ${alertTitle}
                                </div>
                                <h5 class="text-white fw-bold mb-0">${this.escapeHtml(a.bus_number || 'Unknown Bus')}</h5>
                            </div>
                            <span class="badge ${statusBadge}">${this.escapeHtml(status)}</span>
                        </div>
                        <div class="small" style="color:#d9e8ff;">
                            <div><span class="text-muted">${a.reporter_role === 'driver' ? 'Driver' : 'Passenger'}:</span> <span class="text-white fw-bold">${this.escapeHtml(a.passenger_name || 'Unknown')}</span></div>
                            <div class="text-white fw-semibold mt-1">${this.escapeHtml(a.reason || 'Emergency')}</div>
                            <div class="text-muted mt-1">${this.escapeHtml(this.formatAlertTime(a.triggered_at))}</div>
                            <div class="mt-2"><span class="text-muted">Status</span><br><span class="${statusTextClass} fw-bold">${this.escapeHtml(status)}</span></div>
                        </div>
                        <div class="mt-3 d-flex gap-2 flex-wrap">
                            ${actionsHtml}
                        </div>
                     </div>`;
        });
        html += '</div>';
        container.innerHTML = html;
    }
};

document.addEventListener('DOMContentLoaded', () => {
    if (window.SOSHandler) window.SOSHandler.init();
    const adminContainer = document.getElementById('admin-sos-container');
    if (window.AdminSOS && adminContainer && adminContainer.dataset.autoInit === 'true') {
        window.AdminSOS.init();
    }
});
