
// Expose the existing AWS_DATA from the global scope (loaded via script tag) or export it here
// We assume it's loaded before modules, or we can export a smaller synthetic set
export function getDemoData() {
    if (window.AWS_DATA) {
        // Flatten the stations array into individual observations for the normalizer
        let flat = [];
        for (let station in window.AWS_DATA.stations) {
            let obs = window.AWS_DATA.stations[station];
            if(obs && obs.length > 0) {
                // Grab the latest observation for the current state
                let latest = obs[obs.length - 1];
                flat.push({
                    id: station,
                    station_name: station,
                    state: "Maharashtra",
                    district: "Mumbai",
                    latitude: 18.9 + Math.random(),
                    longitude: 72.8 + Math.random(),
                    temperature: latest.temp,
                    humidity: latest.hum,
                    pressure: latest.pres,
                    observation_time: latest.t
                });
            }
        }
        return { data: flat };
    }
    return { data: [] };
}
