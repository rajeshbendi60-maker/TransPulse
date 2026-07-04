(function() {
    window.TransPulseUtils = {
        animateCounter: function(element, endValue, duration = 1500) {
            if (!element || !element.textContent) return;
            const startValue = 0;
            const startTime = Date.now();
            
            function animate() {
                const elapsed = Date.now() - startTime;
                const progress = Math.min(elapsed / duration, 1);
                const easeOutQuad = 1 - (1 - progress) * (1 - progress);
                const current = Math.floor(startValue + (endValue - startValue) * easeOutQuad);
                
                element.textContent = current.toLocaleString();
                if (progress < 1) requestAnimationFrame(animate);
                else element.textContent = endValue.toLocaleString();
            }
            animate();
        },

        initCounters: function() {
            document.querySelectorAll('[data-counter]').forEach(element => {
                const value = parseInt(element.getAttribute('data-counter'), 10);
                if (!isNaN(value)) {
                    const observer = new IntersectionObserver((entries) => {
                        if (entries[0].isIntersecting) {
                            this.animateCounter(element, value);
                            observer.unobserve(element);
                        }
                    }, { threshold: 0.5 });
                    observer.observe(element);
                }
            });
        },

        formatTime: function(seconds) {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = seconds % 60;
            if (hours > 0) return `${hours}h ${minutes}m`;
            return `${minutes}m ${secs}s`;
        },

        formatDistance: function(km) {
            if (km < 1) return `${(km * 1000).toFixed(0)}m`;
            return `${km.toFixed(1)}km`;
        },

        formatETA: function(minutes) {
            if (minutes <= 2) return `<span style="color:#ff5d6c">${minutes}m</span>`;
            if (minutes <= 5) return `<span style="color:#f5b342">${minutes}m</span>`;
            return `<span style="color:#22d39a">${minutes}m</span>`;
        },

        smoothScroll: function(target) {
            if (typeof target === 'string') target = document.querySelector(target);
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        },

        showToast: function(message, type = 'info', duration = 3000) {
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            toast.setAttribute('role', 'alert');
            toast.style.position = 'fixed';
            toast.style.bottom = '20px';
            toast.style.right = '20px';
            toast.style.zIndex = '999999';
            toast.style.padding = '12px 20px';
            toast.innerHTML = `<div class="toast-body">${message}</div>`;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), duration);
        },

        initPWA: function() {
            window.deferredInstallPrompt = null;
            window.__tpCanInstallPWA = false;
            this.updateInstallSurfaces();
            window.addEventListener('beforeinstallprompt', (e) => {
                e.preventDefault();
                if (this.isStandalonePWA()) {
                    window.deferredInstallPrompt = null;
                    window.__tpCanInstallPWA = false;
                    this.updateInstallSurfaces();
                    return;
                }
                window.deferredInstallPrompt = e;
                window.__tpCanInstallPWA = true;
                this.updateInstallSurfaces();
            });
            window.addEventListener('appinstalled', () => {
                window.deferredInstallPrompt = null;
                window.__tpCanInstallPWA = false;
                this.updateInstallSurfaces();
            });
            const syncState = () => this.syncPWAInstallState();
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden) setTimeout(syncState, 150);
            });
            window.addEventListener('focus', syncState);
            window.addEventListener('pageshow', syncState);
            const displayMode = window.matchMedia('(display-mode: standalone)');
            if (displayMode.addEventListener) {
                displayMode.addEventListener('change', syncState);
            } else if (displayMode.addListener) {
                displayMode.addListener(syncState);
            }
        },

        isStandalonePWA: function() {
            return window.matchMedia('(display-mode: standalone)').matches ||
                window.navigator.standalone === true;
        },

        isPWAInstalled: function() {
            return this.isStandalonePWA();
        },

        canInstallPWA: function() {
            return !this.isPWAInstalled() &&
                window.__tpCanInstallPWA === true &&
                !!window.deferredInstallPrompt;
        },

        syncPWAInstallState: function() {
            if (this.isStandalonePWA()) {
                window.deferredInstallPrompt = null;
                window.__tpCanInstallPWA = false;
            }
            this.updateInstallSurfaces();
        },

        updateInstallSurfaces: function() {
            const installButton = document.getElementById('pwa-install-link');
            if (installButton) {
                installButton.classList.toggle('d-none', !this.canInstallPWA());
            }
        },

        showPremiumModal: function(options = {}) {
            const type = options.type || 'success';
            const isDanger = type === 'danger' || type === 'error' || type === 'delete';
            const title = options.title || (isDanger ? 'Action Completed' : 'Success');
            const message = options.message || '';
            const icon = options.icon || (isDanger ? '&#128465;' : '&#10003;');
            const accent = isDanger ? '#ff5d6c' : '#34d2ff';
            const accent2 = isDanger ? '#ff9f43' : '#4f8dff';
            const buttonText = options.buttonText || 'Got It';

            let modal = document.getElementById('tp-premium-action-modal');
            if (!modal) {
                modal = document.createElement('div');
                modal.id = 'tp-premium-action-modal';
                modal.style.cssText = 'display:none; position:fixed; inset:0; background:rgba(0,0,0,0.84); z-index:250000; align-items:center; justify-content:center; backdrop-filter: blur(8px); padding:18px;';
                document.body.appendChild(modal);
            }

            modal.innerHTML = `
                <div class="card glass-panel shadow-lg" style="width:100%; max-width:430px; border-color:${accent}; border-radius:16px; background:linear-gradient(135deg, ${isDanger ? '#1c0610' : '#071d34'}, #040b18); box-shadow:0 0 0 1px ${accent}55, 0 0 38px ${accent}38, 0 28px 80px -34px rgba(0,0,0,0.95); animation:sosModalRise .28s ease-out;">
                    <div class="card-body p-4 p-md-5 text-center">
                        <div style="width:72px; height:72px; border-radius:16px; margin:0 auto 22px; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg, ${accent}, ${accent2}); color:#03101d; font-size:2rem; font-weight:800; box-shadow:0 0 30px ${accent}70; animation:sosGlowPulse 1.8s ease-in-out infinite;">${icon}</div>
                        <h3 class="text-white fw-bold mb-3">${title}</h3>
                        <p class="text-muted mb-4">${message}</p>
                        <button type="button" class="btn fw-bold px-5 py-2 rounded-pill" style="background:linear-gradient(135deg, ${accent}, ${accent2}); color:#03101d; border:0; box-shadow:0 0 24px ${accent}55;">${buttonText}</button>
                    </div>
                </div>`;
            const closeBtn = modal.querySelector('button');
            closeBtn.addEventListener('click', () => {
                modal.style.display = 'none';
                if (typeof options.onClose === 'function') options.onClose();
            }, { once: true });
            modal.style.display = 'flex';
        },

        enhanceFlashMessages: function() {
            const alerts = Array.from(document.querySelectorAll('main .alert'));
            alerts.forEach((alert) => {
                const message = alert.textContent.replace(/\s+/g, ' ').trim();
                if (!message) return;
                const isDanger = alert.classList.contains('alert-danger');
                const isSuccess = alert.classList.contains('alert-success');
                if (!isDanger && !isSuccess) return;
                try {
                    const handledDeleteFlash = sessionStorage.getItem('tp-suppress-next-bus-delete-flash') || '';
                    if (handledDeleteFlash && message.toLowerCase() === handledDeleteFlash.toLowerCase()) {
                        alert.classList.add('d-none');
                        sessionStorage.removeItem('tp-suppress-next-bus-delete-flash');
                        return;
                    }
                } catch (error) {
                    console.warn('Unable to read delete flash suppression flag.', error);
                }
                alert.classList.add('d-none');
                const deleteText = /deleted/i.test(message);
                this.showPremiumModal({
                    type: isDanger ? 'danger' : (deleteText ? 'delete' : 'success'),
                    title: isDanger ? 'Action Needs Attention' : (deleteText ? 'Deleted Successfully' : 'Success'),
                    message,
                    icon: isDanger ? '&#9888;' : (deleteText ? '&#128465;' : '&#10003;')
                });
            });
        },

        replaceNativeAlerts: function() {
            if (window.__tpAlertWrapped) return;
            window.__tpAlertWrapped = true;
            const nativeAlert = window.alert.bind(window);
            window.alert = (message) => {
                if (document.body && window.TransPulseUtils) {
                    window.TransPulseUtils.showPremiumModal({
                        type: /delete|error|fail|invalid|required/i.test(String(message)) ? 'danger' : 'success',
                        title: /delete|error|fail|invalid|required/i.test(String(message)) ? 'Action Needs Attention' : 'Notice',
                        message: String(message),
                        icon: /delete|error|fail|invalid|required/i.test(String(message)) ? '&#9888;' : '&#10003;'
                    });
                    return;
                }
                nativeAlert(message);
            };
        },

        triggerManualInstall: function() {
            if (!this.canInstallPWA()) {
                this.updateInstallSurfaces();
                return;
            }
            const promptEvent = window.deferredInstallPrompt;
            window.deferredInstallPrompt = null;
            window.__tpCanInstallPWA = false;
            this.updateInstallSurfaces();
            promptEvent.prompt();
            promptEvent.userChoice.finally(() => {
                this.updateInstallSurfaces();
            });
        },

        setLoading: function(element, isLoading = true) {
            if (isLoading) {
                element.classList.add('loading');
                element.disabled = true;
                element.innerHTML = 'Loading...';
            } else {
                element.classList.remove('loading');
                element.disabled = false;
            }
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            window.TransPulseUtils.initCounters();
            window.TransPulseUtils.initPWA();
            window.TransPulseUtils.replaceNativeAlerts();
            window.TransPulseUtils.enhanceFlashMessages();
        });
    } else {
        window.TransPulseUtils.initCounters();
        window.TransPulseUtils.initPWA();
        window.TransPulseUtils.replaceNativeAlerts();
        window.TransPulseUtils.enhanceFlashMessages();
    }
})();
