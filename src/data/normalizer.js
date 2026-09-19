export function normalizeAWSData(payload) {
  if (payload?.source === "WeatherAPI" || payload?.source === "OpenWeatherMap") {
    const data = payload.data;
    if (!data || !data.coord) return [];

    const observedEpoch = data.dt;
    const observedAt = new Date(observedEpoch * 1000).toISOString();
    const receivedAt = payload.fetchedAt || new Date().toISOString();
    const receivedEpoch = Math.floor(new Date(receivedAt).getTime() / 1000);

    const tempC = toNumber(data.main?.temp);
    const presHpa = toNumber(data.main?.pressure);
    const humPct = toNumber(data.main?.humidity);

    return [{
      id: data.name.toUpperCase().replace(/\s+/g, "_"),
      callSign: data.name,
      station: data.name,
      district: data.name,
      state: data.sys?.country || "IN",
      date: new Date(observedEpoch * 1000).toISOString().split("T")[0],
      time: new Date(observedEpoch * 1000).toISOString().split("T")[1].slice(0, 8),
      timestamp: observedAt,
      lastUpdatedEpoch: observedEpoch,
      // SIH26073 observation/receipt timestamps
      observedAt,
      observedEpoch,
      receivedAt,
      receivedEpoch,
      fetchedAt: receivedAt,
      fetchedAtEpoch: receivedEpoch,
      // SIH26073 core fields
      temperature: tempC,
      temperatureC: tempC,
      humidity: humPct,
      humidityPct: humPct,
      pressure: presHpa,
      pressureHpa: presHpa,
      // Contextual fields (not core anomaly features)
      dewPoint: null,
      windDirection: toNumber(data.wind?.deg),
      windSpeed: toNumber(data.wind?.speed ? data.wind.speed * 3.6 : 0), // m/s to km/h
      minTemperature: toNumber(data.main?.temp_min),
      maxTemperature: toNumber(data.main?.temp_max),
      latitude: toNumber(data.coord?.lat),
      longitude: toNumber(data.coord?.lon),
      weatherCode: data.weather?.[0]?.id || null,
      nebulosity: toNumber(data.clouds?.all),
      feelsLike: toNumber(data.main?.feels_like),
      provider: "OpenWeatherMap",
      source: "OpenWeatherMap",
      isSynthetic: false
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
    feelsLike: toNumber(item["Feel Like"] ?? item.feels_like),
    isSynthetic: false
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
