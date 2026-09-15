/**
 * TransPulse - Real-time Notifications Client
 * Connects to SSE stream and displays non-blocking Bootstrap toasts.
 */

document.addEventListener("DOMContentLoaded", function() {
    // 1. Setup Toast Container
    let toastContainer = document.getElementById("toast-container");
    if (!toastContainer) {
        toastContainer = document.createElement("div");
        toastContainer.id = "toast-container";
        toastContainer.className = "toast-container position-fixed bottom-0 end-0 p-3";
        toastContainer.style.zIndex = "1055";
        document.body.appendChild(toastContainer);
    }

    // 2. Connect to SSE
    let eventSource = null;
    let retryCount = 0;

    function connectSSE() {
        if (eventSource) {
            eventSource.close();
        }

        console.log("[Notifications] Connecting to SSE stream...");
        eventSource = new EventSource("/api/notifications/stream");

        eventSource.onmessage = function(event) {
            try {
                // Ignore heartbeats
                if (event.data === ": heartbeat") return;
                
                const data = JSON.parse(event.data);
                if (data.type === "connected") {
                    console.log("[Notifications] SSE Connected successfully.");
                    retryCount = 0;
                    return;
                }

                // If user is actively tracking a route/bus, we can filter here
                // For now, if we are on passenger dashboard, show all relevant alerts
                // Filter by role if specified
                if (data.target_role && data.target_role !== 'all' && data.target_role !== 'none') {
                    // Check if current user role matches
                    if (window.TP_USER_ROLE && window.TP_USER_ROLE !== data.target_role) {
                        return; // targeted at a different role
                    }
                }
                
                // Filter driver-specific notifications
                if (data.target_driver_code && window.TP_DRIVER_CODE) {
                    if (data.target_driver_code !== window.TP_DRIVER_CODE) {
                        return; // targeted at someone else
                    }
                }
                
                // Filter passenger-specific notifications (like SOS updates)
                if (data.passenger_id && window.TP_USER_ID) {
                    if (data.passenger_id != window.TP_USER_ID) {
                        return; // targeted at a different passenger
                    }
                }
                
                showToast(data);

                // Optional: trigger native OS notification if page is backgrounded
                triggerOSNotification(data);

            } catch (err) {
                console.error("[Notifications] Error parsing SSE message", err, event.data);
            }
        };

        eventSource.onerror = function(err) {
            console.warn("[Notifications] SSE connection error. Reconnecting...", err);
            eventSource.close();
            
            // Exponential backoff
            const timeout = Math.min(1000 * Math.pow(2, retryCount), 30000);
            retryCount++;
            setTimeout(connectSSE, timeout);
        };
    }

    // 3. Render Bootstrap Toast
    const recentToasts = new Set();
    
    function showToast(data) {
        // Deduplicate: Don't show the exact same title+body within 10 minutes
        const toastKey = `${data.title}|${data.body}`;
        if (recentToasts.has(toastKey)) return;
        
        recentToasts.add(toastKey);
        setTimeout(() => recentToasts.delete(toastKey), 10 * 60 * 1000); // clear after 10 mins

        // For ALL alerts, we now just highlight the bell icon instead of showing a blocking toast on screen
        const bells = document.querySelectorAll('.fa-bell');
        bells.forEach(bell => {
            bell.classList.add('text-danger');
            bell.parentElement.classList.add('border-danger');
            setTimeout(() => {
                bell.classList.remove('text-danger');
                bell.parentElement.classList.remove('border-danger');
            }, 5000);
        });
    }    


    // 4. OS-Level Notification (Web Push)
    function triggerOSNotification(data) {
        if (!("Notification" in window)) return;
        
        if (Notification.permission === "granted") {
            // Only show OS push if document is hidden (user is in another tab)
            if (document.hidden) {
                new Notification(data.title, {
                    body: data.body,
                    icon: "/favicon.ico"
                });
            }
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission();
        }
    }

    // Helper
    function escapeHtml(unsafe) {
        return (unsafe || "").toString()
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Init
    connectSSE();
    
    // Request permission for background push early
    if ("Notification" in window && Notification.permission === "default") {
        document.body.addEventListener('click', () => {
            if (Notification.permission === "default") Notification.requestPermission();
        }, { once: true });
    }
});
/* TP-v2.0-Release */
