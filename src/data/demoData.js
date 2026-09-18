
// Deterministic demo data generator
// Generates realistic-looking station data spread across India
// without using Math.random() for visible telemetry

const DEMO_STATIONS = [
    { id: 'MH-042', name: 'Mumbai Colaba', state: 'Maharashtra', district: 'Mumbai', lat: 18.9067, lng: 72.8147, temp: 28.6, hum: 71, pres: 1007, wind: 14 },
    { id: 'MH-018', name: 'Pune Shivajinagar', state: 'Maharashtra', district: 'Pune', lat: 18.5314, lng: 73.8446, temp: 29.8, hum: 62, pres: 1012, wind: 8 },
    { id: 'DL-001', name: 'New Delhi Safdarjung', state: 'Delhi', district: 'New Delhi', lat: 28.5849, lng: 77.2084, temp: 34.2, hum: 45, pres: 1004, wind: 12 },
    { id: 'RJ-044', name: 'Jaipur Sanganer', state: 'Rajasthan', district: 'Jaipur', lat: 26.8243, lng: 75.8119, temp: 36.1, hum: 38, pres: 1003, wind: 15 },
    { id: 'RJ-113', name: 'Jodhpur CAZRI', state: 'Rajasthan', district: 'Jodhpur', lat: 26.2570, lng: 73.0031, temp: 37.4, hum: 82.4, pres: 1002, wind: 18 },
    { id: 'KA-087', name: 'Bengaluru GKVK', state: 'Karnataka', district: 'Bengaluru', lat: 13.0784, lng: 77.5913, temp: 26.3, hum: 68, pres: 1008.2, wind: 6 },
    { id: 'KA-012', name: 'Mangaluru', state: 'Karnataka', district: 'Mangalore', lat: 12.9141, lng: 74.8560, temp: 30.1, hum: 78, pres: 1009, wind: 11 },
    { id: 'TN-055', name: 'Chennai Nungambakkam', state: 'Tamil Nadu', district: 'Chennai', lat: 13.0674, lng: 80.2376, temp: 31.1, hum: 74, pres: 1008, wind: 13 },
    { id: 'TN-012', name: 'Madurai Airport', state: 'Tamil Nadu', district: 'Madurai', lat: 9.8344, lng: 78.0934, temp: 33.5, hum: 100.0, pres: 1006, wind: 7 },
    { id: 'KL-021', name: 'Kochi', state: 'Kerala', district: 'Ernakulam', lat: 9.9312, lng: 76.2673, temp: 29.4, hum: 82, pres: 1010, wind: 9 },
    { id: 'KL-007', name: 'Wayanad', state: 'Kerala', district: 'Wayanad', lat: 11.6854, lng: 76.1320, temp: 24.2, hum: 88, pres: 1015, wind: 78.4 },
    { id: 'UT-019', name: 'Dehradun Valley', state: 'Uttarakhand', district: 'Dehradun', lat: 30.3165, lng: 78.0322, temp: 22.1, hum: 72, pres: 1014, wind: 5 },
    { id: 'HP-004', name: 'Shimla Ridge', state: 'Himachal Pradesh', district: 'Shimla', lat: 31.1048, lng: 77.1734, temp: -18.4, hum: 65, pres: 1020, wind: 3 },
    { id: 'WB-031', name: 'Kolkata Alipore', state: 'West Bengal', district: 'Kolkata', lat: 22.5326, lng: 88.3283, temp: 32.4, hum: 76, pres: 1005, wind: 10 },
    { id: 'GJ-015', name: 'Ahmedabad', state: 'Gujarat', district: 'Ahmedabad', lat: 23.0225, lng: 72.5714, temp: 35.8, hum: 42, pres: 1004, wind: 16 },
    { id: 'AP-022', name: 'Hyderabad Begumpet', state: 'Telangana', district: 'Hyderabad', lat: 17.4537, lng: 78.4670, temp: 30.6, hum: 58, pres: 1007, wind: 11 },
    { id: 'OR-008', name: 'Bhubaneswar', state: 'Odisha', district: 'Khurda', lat: 20.2961, lng: 85.8245, temp: 31.2, hum: 73, pres: 1006, wind: 14 },
    { id: 'AS-003', name: 'Guwahati', state: 'Assam', district: 'Kamrup', lat: 26.1445, lng: 91.7362, temp: 27.8, hum: 80, pres: 1008, wind: 7 },
    { id: 'PB-011', name: 'Ludhiana', state: 'Punjab', district: 'Ludhiana', lat: 30.9010, lng: 75.8573, temp: 33.6, hum: 52, pres: 1003, wind: 9 },
    { id: 'MP-019', name: 'Bhopal', state: 'Madhya Pradesh', district: 'Bhopal', lat: 23.2599, lng: 77.4126, temp: 31.4, hum: 55, pres: 1006, wind: 8 },
];

// Generate deterministic 24h temperature history for a station
export function getDemoHistory(stationId, hours = 24) {
    const station = DEMO_STATIONS.find(s => s.id === stationId) || DEMO_STATIONS[0];
    const baseTemp = station.temp > 40 ? 30 : station.temp < -10 ? 10 : station.temp;
    const points = hours * 6; // every 10 minutes
    const now = Date.now();
    const labels = [];
    const observed = [];
    const expected = [];
    
    // Simple seed based on station ID characters
    const seed = stationId.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
    
    for (let i = 0; i < points; i++) {
        const t = now - (points - i) * 10 * 60 * 1000;
        const hour = new Date(t).getHours() + new Date(t).getMinutes() / 60;
        
        // Deterministic diurnal curve: cooler at night, warmer during day
        const diurnalOffset = 4 * Math.sin((hour - 6) * Math.PI / 12);
        const exp = baseTemp + diurnalOffset;
        
        // Small deterministic variation based on index and seed
        const variation = 0.3 * Math.sin(i * 0.7 + seed * 0.1) + 0.2 * Math.sin(i * 1.3 + seed * 0.3);
        let obs = exp + variation;
        
        // Inject anomaly near the end for anomalous stations
        if (stationId === 'MH-042' && i === points - 3) {
            obs = 47.2; // The spike
        } else if (stationId === 'HP-004' && i === points - 5) {
            obs = -18.4; // Cold spike
        }
        
        const date = new Date(t);
        labels.push(date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false }));
        observed.push(Math.round(obs * 10) / 10);
        expected.push(Math.round(exp * 10) / 10);
    }
    
    return { labels, observed, expected };
}

export function getDemoData() {
    if (window.AWS_DATA) {
        // Flatten the stations array into individual observations for the normalizer
        let flat = [];
        for (let station in window.AWS_DATA.stations) {
            let obs = window.AWS_DATA.stations[station];
            if(obs && obs.length > 0) {
                let latest = obs[obs.length - 1];
                // Try to find matching demo station for proper coordinates
                const demoStation = DEMO_STATIONS.find(s => s.id === station);
                flat.push({
                    id: station,
                    station_name: demoStation ? demoStation.name : station,
                    state: demoStation ? demoStation.state : "Unknown",
                    district: demoStation ? demoStation.district : "Unknown",
                    latitude: demoStation ? demoStation.lat : 20 + flat.length * 0.5,
                    longitude: demoStation ? demoStation.lng : 75 + flat.length * 0.3,
                    temperature: latest.temp,
                    humidity: latest.hum,
                    pressure: latest.pres,
                    observation_time: latest.t
                });
            }
        }
        return { data: flat };
    }
    
    // Fallback: use built-in demo stations
    return {
        data: DEMO_STATIONS.map(s => ({
            id: s.id,
            station_name: s.name,
            state: s.state,
            district: s.district,
            latitude: s.lat,
            longitude: s.lng,
            temperature: s.temp,
            humidity: s.hum,
            pressure: s.pres,
            wind_speed: s.wind,
            observation_time: new Date().toISOString()
        }))
    };
}
