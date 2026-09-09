import { store } from '../state/store.js';

let anomalyChartInstance = null;

export function initCharts() {
    const canvas = document.getElementById('anomalyChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    
    function getThemeColors() {
        const isDark = document.documentElement.classList.contains('dark');
        return {
            text: isDark ? '#e9f1f6' : '#0f172a',
            grid: isDark ? '#17334a' : '#e2e8f0',
            primary: isDark ? '#2e86ab' : '#0284c7',
            error: isDark ? '#d9483f' : '#dc2626',
            warning: isDark ? '#d9752f' : '#d97706',
            baseline: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)'
        };
    }
    
    anomalyChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Observed',
                    data: [],
                    borderColor: getThemeColors().primary,
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1
                },
                {
                    label: 'Expected Baseline',
                    data: [],
                    borderColor: getThemeColors().baseline,
                    borderDash: [5, 5],
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: getThemeColors().text } },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                }
            },
            scales: {
                x: { ticks: { color: getThemeColors().text }, grid: { color: getThemeColors().grid } },
                y: { ticks: { color: getThemeColors().text }, grid: { color: getThemeColors().grid } }
            }
        }
    });
    
    // Update colors on theme change
    window.addEventListener('themeChanged', () => {
        const colors = getThemeColors();
        anomalyChartInstance.options.plugins.legend.labels.color = colors.text;
        anomalyChartInstance.options.scales.x.ticks.color = colors.text;
        anomalyChartInstance.options.scales.x.grid.color = colors.grid;
        anomalyChartInstance.options.scales.y.ticks.color = colors.text;
        anomalyChartInstance.options.scales.y.grid.color = colors.grid;
        anomalyChartInstance.data.datasets[0].borderColor = colors.primary;
        anomalyChartInstance.data.datasets[1].borderColor = colors.baseline;
        anomalyChartInstance.update();
    });
    
    // Subscribe to store updates to redraw data
    store.subscribe((state) => {
        // Here we would typically grab the history of the selected station.
        // For demonstration of the integration, we just plot a sample of the raw data vs baseline.
        if (state.data.length === 0) return;
        
        // Take first station's temperature for demo
        const stationId = state.data[0].id;
        // In a real app we would query `history` from detector.js or the store.
        // Since we don't have historical data stored globally yet, we will just use dummy history
        // based on the current observation to show the chart is functional.
        
        const labels = Array.from({length: 10}, (_, i) => `T-${10-i}`);
        const observed = Array.from({length: 10}, () => state.data[0].temperature + (Math.random() * 2 - 1));
        const expected = Array.from({length: 10}, () => state.data[0].temperature);
        
        // Inject an anomaly at the end if it has one
        if (state.anomalies.some(a => a.stationId === stationId)) {
            observed[9] += 5; // Spike
        }
        
        anomalyChartInstance.data.labels = labels;
        anomalyChartInstance.data.datasets[0].data = observed;
        anomalyChartInstance.data.datasets[1].data = expected;
        anomalyChartInstance.update();
    });
}
