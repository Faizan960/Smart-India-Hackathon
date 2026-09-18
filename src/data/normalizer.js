export function normalizeAWSData(payload) {
  if (payload?.source === "WeatherAPI") {
    const loc = payload.data?.location;
    const cur = payload.data?.current;
    if (!loc || !cur) return [];
    
    return [{
      id: loc.name.toUpperCase().replace(/\s+/g, "_"),
      callSign: loc.name,
      station: loc.name,
      district: loc.name,
      state: loc.region,
      date: loc.localtime?.split(" ")[0] || null,
      time: loc.localtime?.split(" ")[1] || null,
      timestamp: cur.last_updated || new Date().toISOString(),
      temperature: toNumber(cur.temp_c),
      dewPoint: toNumber(cur.dewpoint_c),
      humidity: toNumber(cur.humidity),
      windDirection: toNumber(cur.wind_degree),
      windSpeed: toNumber(cur.wind_kph),
      pressure: toNumber(cur.pressure_mb),
      minTemperature: null,
      maxTemperature: null,
      latitude: toNumber(loc.lat),
      longitude: toNumber(loc.lon),
      weatherCode: cur.condition?.code || null,
      nebulosity: toNumber(cur.cloud),
      feelsLike: toNumber(cur.feelslike_c)
    }];
  }

  const root = payload?.data ?? payload;
  const rows =
    Array.isArray(root?.data) ? root.data :
    Array.isArray(root) ? root :
    Array.isArray(root?.stations) ? root.stations :
    [];

  return rows.map((item) => ({
    id: item.ID ?? item.id ?? item.station_id ?? null,
    callSign: item.CALL_SIGN ?? item.call_sign ?? item.station_name ?? null,
    station: item.STATION ?? item.station ?? item.station_name ?? null,
    district: item.DISTRICT ?? item.district ?? null,
    state: item.STATE ?? item.state ?? null,
    date: item.DATE ?? item.date ?? null,
    time: item.TIME ?? item.time ?? null,
    timestamp: toTimestamp(item),
    temperature: toNumber(item.CURR_TEMP ?? item.temperature ?? item.air_temp),
    dewPoint: toNumber(item.DEW_POINT_TEMP ?? item.dew_point ?? item.dewPoint),
    humidity: toNumber(item.RH ?? item.humidity ?? item.rel_humidity),
    windDirection: toNumber(item.WIND_DIRECTION ?? item.wind_direction),
    windSpeed: toNumber(item.WIND_SPEED ?? item.wind_speed),
    pressure: toNumber(item.MSLP ?? item.pressure ?? item.station_pressure),
    minTemperature: toNumber(item.MIN_TEMP ?? item.min_temp),
    maxTemperature: toNumber(item.MAX_TEMP ?? item.max_temp),
    latitude: toNumber(item.Latitude ?? item.latitude),
    longitude: toNumber(item.Longitude ?? item.longitude),
    weatherCode: item.WEATHER_CODE ?? item.weather_code ?? null,
    nebulosity: toNumber(item.NEBULOSITY ?? item.nebulosity),
    feelsLike: toNumber(item["Feel Like"] ?? item.feels_like)
  })).filter((station) => station.id || station.callSign || station.station);
}

function toNumber(value) {
  if (value === null || value === undefined || value === "" || value === "-") return null;
  const parsed = Number.parseFloat(String(value).replace(/[^0-9.+-]/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function toTimestamp(item) {
  const date = item.DATE ?? item.date;
  const time = item.TIME ?? item.time;
  if (date && time) {
    const parsed = new Date(`${date}T${time}+05:30`);
    if (!Number.isNaN(parsed.getTime())) return parsed.toISOString();
  }
  return item.observation_time ?? item.timestamp ?? new Date().toISOString();
}
