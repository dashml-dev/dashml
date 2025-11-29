/**
 * DashML Auto-reload System
 * Detects .dashml file changes and auto-reloads the dashboard
 */
class DashMLAutoReload {
    constructor(options = {}) {
        this.pollInterval = options.pollInterval || 1000; // 1 second
        this.reloadCallback = options.onReload || this.defaultReload;
        this.lastTimestamp = null;
        this.isPolling = false;
        this.dashmlPath = options.dashmlPath;
    }

    start() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        console.log('🔄 Auto-reload enabled');
        this.poll();
    }

    stop() {
        this.isPolling = false;
        console.log('⏸️  Auto-reload disabled');
    }

    async poll() {
        if (!this.isPolling) return;

        try {
            // Check reload flag file
            const response = await fetch('.dashml_reload?' + Date.now(), {
                cache: 'no-store'
            });
            
            if (response.ok) {
                const timestamp = await response.text();
                
                if (this.lastTimestamp && timestamp !== this.lastTimestamp) {
                    console.log('🔄 DashML file changed, reloading...');
                    await this.reloadCallback();
                }
                
                this.lastTimestamp = timestamp;
            }
        } catch (error) {
            // Flag file doesn't exist yet or server error - that's ok
        }

        // Continue polling
        setTimeout(() => this.poll(), this.pollInterval);
    }

    async defaultReload() {
        // Simple page reload
        window.location.reload();
    }
}

/**
 * Smart DashML reload without full page refresh
 */
async function reloadDashMLOnly() {
    const dashmlPath = document.getElementById('dashmlPath')?.value || 'dashml_example.dashml';
    
    try {
        const transformer = await DashMLTransformer.fromYAML(dashmlPath);
        const renderer = new DashMLPlotlyRenderer(transformer);
        
        await renderer.renderDashboard({
            containerId: 'dashboard',
            showTitle: true,
            showSelector: true
        });
        
        // Show reload notification
        showReloadNotification();
    } catch (error) {
        console.error('Reload error:', error);
    }
}

function showReloadNotification() {
    const notification = document.createElement('div');
    notification.textContent = '🔄 Dashboard reloaded';
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #4CAF50;
        color: white;
        padding: 12px 24px;
        border-radius: 6px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 10000;
        font-family: sans-serif;
        font-size: 14px;
        animation: slideIn 0.3s ease-out;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 2000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

