const API_ROOT = "/api/imd/aws";

async function request(url, signal) {
  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal
  });

  let payload = null;
  try { payload = await response.json(); } catch {}

  if (!response.ok) {
    throw new Error(payload?.message || payload?.error || `IMD API HTTP ${response.status}`);
  }

  return payload;
}

export async function getAllAWSData(signal) {
  return request(API_ROOT, signal);
}

export async function getAWSStation(stationId, signal) {
  if (!stationId) throw new Error("stationId is required");
  return request(`${API_ROOT}?station=${encodeURIComponent(stationId)}`, signal);
}
