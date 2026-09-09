
import { getAllAWSData } from '../api/imd.js';
import { normalizeAWSData } from '../data/normalizer.js';
import { getDemoData } from '../data/demoData.js';

export const store = {
    state: {
        status: 'OFFLINE', // CONNECTED, CONNECTING, OFFLINE, DEMO MODE, ERROR
        lastSync: null,
        data: [],
        anomalies: [],
        settings: {
            refreshInterval: 300, // seconds
            theme: localStorage.getItem('theme') || 'dark',
            useDemo: false
        }
    },
    
    listeners: [],
    
    subscribe(listener) {
        this.listeners.push(listener);
    },
    
    notify() {
        this.listeners.forEach(l => l(this.state));
    },

    async fetchLiveData() {
        if (this.state.settings.useDemo) {
            this.setDemoData();
            return;
        }

        this.state.status = 'CONNECTING';
        this.notify();

        try {
            const raw = await getAllAWSData();
            const normalized = normalizeAWSData(raw);
            this.state.data = normalized;
            this.state.status = 'CONNECTED';
            this.state.lastSync = new Date().toLocaleTimeString();
            
            // Cache to local storage
            try {
                localStorage.setItem('aws_cache', JSON.stringify(normalized));
                localStorage.setItem('aws_cache_time', Date.now());
            } catch(e) { console.warn("Cache write failed", e); }
            
            this.notify();
        } catch (error) {
            console.warn("Falling back to cache/demo due to error", error);
            
            // Try cache
            const cached = localStorage.getItem('aws_cache');
            const cacheTime = localStorage.getItem('aws_cache_time');
            if (cached && cacheTime && (Date.now() - parseInt(cacheTime) < 3600000)) { // 1 hour max
                this.state.data = JSON.parse(cached);
                this.state.status = 'ERROR'; // Showing cache
                this.notify();
            } else {
                this.setDemoData();
            }
        }
    },

    setDemoData() {
        const raw = getDemoData();
        this.state.data = normalizeAWSData(raw);
        this.state.status = 'DEMO MODE';
        this.notify();
    }
};
