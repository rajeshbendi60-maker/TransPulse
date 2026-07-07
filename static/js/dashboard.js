(function() {
    if (window.__tpDashboardInitialized) return;
    window.__tpDashboardInitialized = true;

    function resolveNavigationUrl(element) {
        const anchor = element.closest('a[href]');
        if (anchor) return anchor.getAttribute('href');

        const navElement = element.closest('[onclick]');
        if (!navElement) return null;
        const onclick = navElement.getAttribute('onclick') || '';
        const match = onclick.match(/window\.location\.href\s*=\s*['"]([^'"]+)['"]/);
        return match ? match[1] : null;
    }

    function isFastNavigationUrl(url) {
        if (!url || url === '#' || url.startsWith('javascript:')) return false;
        try {
            const parsed = new URL(url, window.location.href);
            return parsed.origin === window.location.origin;
        } catch (error) {
            return false;
        }
    }

    document.addEventListener('click', (event) => {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }

        const url = resolveNavigationUrl(event.target);
        if (!isFastNavigationUrl(url)) return;

        window.__tpNavigating = true;
        event.preventDefault();
        event.stopImmediatePropagation();
        window.location.assign(url);
    }, true);

    // Register service worker for PWA support
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/static/service-worker.js')
                .then((registration) => {
                    console.log('ServiceWorker registration successful:', registration.scope);
                })
                .catch((error) => {
                    console.log('ServiceWorker registration failed:', error);
                });
        });
    }

    // Handle updates to the service worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.addEventListener('controllerchange', () => {
            console.log('ServiceWorker updated, reloading...');
            window.location.reload();
        });
    }

    // Dark theme management
    const themeManager = {
        init: function() {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');
            const theme = localStorage.getItem('theme') || (prefersDark.matches ? 'dark' : 'light');
            this.setTheme(theme);

            prefersDark.addEventListener('change', () => {
                this.setTheme(prefersDark.matches ? 'dark' : 'light');
            });
        },

        setTheme: function(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
        },
    };

    themeManager.init();

    // Auto-hide notifications
    document.querySelectorAll('.alert').forEach((alert) => {
        if (!alert.classList.contains('alert-permanent')) {
            setTimeout(() => {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }, 5000);
        }
    });

    // Format timestamps
    function formatTime(isoString) {
        const date = new Date(isoString);
        const now = new Date();
        const diff = now - date;
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (seconds < 60) return 'Just now';
        if (minutes < 60) return `${minutes}m ago`;
        if (hours < 24) return `${hours}h ago`;
        if (days < 7) return `${days}d ago`;
        return date.toLocaleDateString();
    }

    // Initialize time formatters
    document.querySelectorAll('[data-time]').forEach((el) => {
        const isoTime = el.getAttribute('data-time');
        if (isoTime) {
            el.textContent = formatTime(isoTime);
            el.title = new Date(isoTime).toLocaleString();
        }
    });

    // Tooltip initialization
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
        new bootstrap.Tooltip(el);
    });

    // Popover initialization
    document.querySelectorAll('[data-bs-toggle="popover"]').forEach((el) => {
        new bootstrap.Popover(el);
    });

    // Mobile menu auto-close on link click
    const mobileMenu = document.getElementById('mobileMenu');
    if (mobileMenu) {
        mobileMenu.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', () => {
                const offcanvas = bootstrap.Offcanvas.getInstance(mobileMenu);
                if (offcanvas) offcanvas.hide();
            });
        });
    }

    // Page visibility handler
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            // Emit refresh event for dashboards
            window.dispatchEvent(new Event('page-visible'));
        }
    });

    // Global error handler
    window.addEventListener('error', (event) => {
        console.error('Global error:', event.error);
    });

    // Handle unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
        console.error('Unhandled promise rejection:', event.reason);
    });

    // Accessibility: Enhanced keyboard navigation
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            document.querySelectorAll('[data-bs-toggle="offcanvas"].show').forEach((el) => {
                bootstrap.Offcanvas.getInstance(el)?.hide();
            });
        }
    });

    // Export utilities globally
    window.TransPulseDashboard = {
        formatTime,
        themeManager,
        refreshPage: function() {
            location.reload();
        },
        goBack: function() {
            window.history.back();
        },
    };
})();

