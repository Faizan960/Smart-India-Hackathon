import { initCharts } from './components/charts.js';
import { initMap } from './components/map.js';

import { store } from './state/store.js';
import { detectAnomalies } from './anomaly/detector.js';

// Initialize Theme
function initTheme() {
    const toggle = document.getElementById('themeToggle');
    const icon = document.getElementById('themeIcon');
    
    function updateIcon() {
        if (document.documentElement.classList.contains('dark')) {
            icon.textContent = 'light_mode';
        } else {
            icon.textContent = 'dark_mode';
        }
    }
    
    toggle.addEventListener('click', () => {
        if (document.documentElement.classList.contains('dark')) {
            document.documentElement.classList.remove('dark');
            localStorage.theme = 'light';
        } else {
            document.documentElement.classList.add('dark');
            localStorage.theme = 'dark';
        }
        updateIcon();
        // Trigger chart redraws if any exist
        window.dispatchEvent(new Event('themeChanged'));
    });
    
    updateIcon();
}

// Initialize UI Wiring

function renderInvestigationTable(anomalies) {
    const tbody = document.getElementById('investigationTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    if (anomalies.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center py-8 text-on-surface-variant">No anomalies detected.</td></tr>';
        return;
    }
    
    anomalies.forEach(a => {
        const timeStr = new Date(a.timestamp).toLocaleString();
        
        // Define color classes based on severity
        let sevClass = a.severity === 'CRITICAL' ? 'bg-error text-on-primary' : 'bg-warning text-on-primary';
        // Wait, warning background isn't explicitly defined in tailwind config classes we added, we used bg-error
        if (a.severity !== 'CRITICAL') sevClass = 'bg-tertiary text-on-primary';
        
        let statusClass = 'bg-surface-container-high text-on-surface';
        if (a.status === 'ACKNOWLEDGED') statusClass = 'bg-primary-container text-surface';
        if (a.status === 'VERIFIED') statusClass = 'bg-secondary text-on-primary';
        if (a.status === 'RESOLVED') statusClass = 'bg-surface text-on-surface-variant opacity-50';
        
        const row = document.createElement('tr');
        row.className = 'border-b border-surface-container-low hover:bg-surface-container transition';
        row.innerHTML = `
            <td class="p-3 text-sm">${timeStr}</td>
            <td class="p-3 text-sm font-medium">${a.stationId}</td>
            <td class="p-3 text-sm capitalize">${a.sensor}</td>
            <td class="p-3 text-sm"><span class="px-2 py-1 rounded text-xs font-bold ${sevClass}">${a.severity}</span></td>
            <td class="p-3 text-sm">${a.anomalyType}</td>
            <td class="p-3 text-sm">${(a.confidence * 100).toFixed(1)}%</td>
            <td class="p-3 text-sm"><span class="px-2 py-1 rounded text-xs font-bold cursor-pointer ${statusClass}" onclick="window.cycleStatus('${a.id}')">${a.status}</span></td>
            <td class="p-3 text-sm">
                <button class="text-primary hover:underline text-xs mr-2" onclick="alert('${a.evidence}')">Details</button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// Global function for onclick status toggle
window.cycleStatus = function(anomalyId) {
    const states = ['NEW', 'ACKNOWLEDGED', 'VERIFIED', 'RESOLVED'];
    const anomaly = store.state.anomalies.find(a => a.id === anomalyId);
    if (anomaly) {
        let idx = states.indexOf(anomaly.status);
        anomaly.status = states[(idx + 1) % states.length];
        store.notify(); // re-render
    }
};

function initUI() {
    initMap('mapContainer');
    initCharts();


    // Tab Routing
    document.getElementById('navTabs').addEventListener('click', (e) => {
        if (e.target.tagName !== 'BUTTON' && !e.target.closest('button[data-tab]')) return;
        const btn = e.target.closest('button[data-tab]');
        if (!btn) return;
        const tab = btn.dataset.tab;
        
        [...document.querySelectorAll('#navTabs button[data-tab]')].forEach(b => {
            b.classList.remove('bg-primary', 'text-on-primary');
            b.classList.add('bg-surface-container', 'text-on-surface');
        });
        btn.classList.remove('bg-surface-container', 'text-on-surface');
        btn.classList.add('bg-primary', 'text-on-primary');
        
        [...document.querySelectorAll('.tab-panel')].forEach(p => p.classList.remove('active'));
        const panel = document.getElementById('tab-' + tab);
        if (panel) panel.classList.add('active');
    });

    // Subscribe to store updates to update dashboard
    store.subscribe((state) => {
        // Connection status
        const connText = document.getElementById('connText');
        const connDot = document.getElementById('connDot');
        if (connText && connDot) {
            connText.textContent = state.status;
            connDot.className = 'w-2 h-2 rounded-full ' + 
                (state.status === 'CONNECTED' ? 'bg-secondary' : 
                 state.status === 'DEMO MODE' ? 'bg-tertiary' : 
                 state.status === 'ERROR' ? 'bg-error' : 'bg-outline animate-pulse');
        }
        
        // Update KPIs (finding placeholders in the UI based on classes)
        // This is a naive update since we don't have hardcoded IDs yet
        if (state.data.length > 0) {
            const anomalies = [];
            state.data.forEach(stationData => {
                const detected = detectAnomalies(stationData);
                anomalies.push(...detected);
            });
            
            // Example: updating active anomalies counter if we add an ID to it
            const anomalyCountEl = document.getElementById('kpi-anomalies');
            if (anomalyCountEl) {
                anomalyCountEl.textContent = anomalies.length;
            }
            
            store.state.anomalies = anomalies;
            renderInvestigationTable(anomalies);

        }
    });
}

// Boot
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initUI();
    
    // Initial fetch
    store.fetchLiveData();
    
    // Auto-refresh loop
    setInterval(() => {
        store.fetchLiveData();
    }, store.state.settings.refreshInterval * 1000);
});
