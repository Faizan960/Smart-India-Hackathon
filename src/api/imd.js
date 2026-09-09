
// IMD API Interaction Layer
const ENV = {
  IMD_API_BASE_URL: 'https://api.imd.gov.in/api/v1/aws_data',
  IMD_API_MAPPING_URL: 'https://api.imd.gov.in/api/v1/aws_data_mapping'
};

export async function getAllAWSData() {
  try {
    const res = await fetch(ENV.IMD_API_BASE_URL, {
        method: 'GET',
        mode: 'cors'
    });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (error) {
    console.error("IMD API Fetch Error:", error);
    throw error;
  }
}

export async function getAWSStation(stationId) {
  try {
    const res = await fetch(`${ENV.IMD_API_BASE_URL}?id=${stationId}`, { mode: 'cors' });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (error) {
    console.error("IMD API Station Fetch Error:", error);
    throw error;
  }
}
