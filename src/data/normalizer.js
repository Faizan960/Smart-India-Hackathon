
// Normalizes raw IMD responses into our standard data model
export function normalizeAWSData(rawData) {
    if (!rawData || !rawData.data) return [];
    
    return rawData.data.map(item => ({
        id: item.station_id || item.id,
        callSign: item.station_name || "Unknown",
        station: item.station_name,
        district: item.district,
        state: item.state,
        latitude: parseFloat(item.latitude || 0),
        longitude: parseFloat(item.longitude || 0),
        timestamp: item.observation_time || new Date().toISOString(),
        temperature: parseFloat(item.temperature || item.air_temp || 0),
        humidity: parseFloat(item.humidity || item.rel_humidity || 0),
        windSpeed: parseFloat(item.wind_speed || 0),
        windDirection: parseFloat(item.wind_direction || 0),
        pressure: parseFloat(item.pressure || item.station_pressure || 0),
        rainfall: parseFloat(item.rainfall || 0)
    }));
}
