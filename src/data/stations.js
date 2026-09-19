/**
 * Canonical Station Registry — Single Source of Truth
 *
 * Every UI component, the store, map, polling engine, and overview KPIs
 * MUST derive station lists and counts from this array.
 *
 * These are monitored development locations using OpenWeatherMap as the
 * data provider. They are NOT labelled as actual IMD AWS stations.
 */
export const STATIONS = [
  {
    id: "DL-001",
    name: "New Delhi Safdarjung",
    locationQuery: "New Delhi",
    region: "Delhi",
    latitude: 28.5849,
    longitude: 77.2084
  },
  {
    id: "MH-042",
    name: "Mumbai Colaba",
    locationQuery: "Mumbai",
    region: "Maharashtra",
    latitude: 18.9067,
    longitude: 72.8147
  },
  {
    id: "KA-087",
    name: "Bengaluru GKVK",
    locationQuery: "Bengaluru",
    region: "Karnataka",
    latitude: 13.0784,
    longitude: 77.5913
  },
  {
    id: "TN-055",
    name: "Chennai Nungambakkam",
    locationQuery: "Chennai",
    region: "Tamil Nadu",
    latitude: 13.0674,
    longitude: 80.2376
  },
  {
    id: "MH-018",
    name: "Pune Shivajinagar",
    locationQuery: "Pune",
    region: "Maharashtra",
    latitude: 18.5314,
    longitude: 73.8446
  },
  {
    id: "RJ-044",
    name: "Jaipur Sanganer",
    locationQuery: "Jaipur",
    region: "Rajasthan",
    latitude: 26.8243,
    longitude: 75.8119
  },
  {
    id: "RJ-113",
    name: "Jodhpur CAZRI",
    locationQuery: "Jodhpur",
    region: "Rajasthan",
    latitude: 26.2570,
    longitude: 73.0031
  },
  {
    id: "KA-012",
    name: "Mangaluru",
    locationQuery: "Mangalore",
    region: "Karnataka",
    latitude: 12.9141,
    longitude: 74.8560
  },
  {
    id: "TN-012",
    name: "Madurai Airport",
    locationQuery: "Madurai",
    region: "Tamil Nadu",
    latitude: 9.8344,
    longitude: 78.0934
  },
  {
    id: "KL-021",
    name: "Kochi",
    locationQuery: "Kochi",
    region: "Kerala",
    latitude: 9.9312,
    longitude: 76.2673
  },
  {
    id: "KL-007",
    name: "Wayanad",
    locationQuery: "Wayanad",
    region: "Kerala",
    latitude: 11.6854,
    longitude: 76.1320
  },
  {
    id: "UT-019",
    name: "Dehradun Valley",
    locationQuery: "Dehradun",
    region: "Uttarakhand",
    latitude: 30.3165,
    longitude: 78.0322
  },
  {
    id: "HP-004",
    name: "Shimla Ridge",
    locationQuery: "Shimla",
    region: "Himachal Pradesh",
    latitude: 31.1048,
    longitude: 77.1734
  },
  {
    id: "WB-031",
    name: "Kolkata Alipore",
    locationQuery: "Kolkata",
    region: "West Bengal",
    latitude: 22.5326,
    longitude: 88.3283
  },
  {
    id: "GJ-015",
    name: "Ahmedabad",
    locationQuery: "Ahmedabad",
    region: "Gujarat",
    latitude: 23.0225,
    longitude: 72.5714
  },
  {
    id: "AP-022",
    name: "Hyderabad Begumpet",
    locationQuery: "Hyderabad",
    region: "Telangana",
    latitude: 17.4537,
    longitude: 78.4670
  },
  {
    id: "OR-008",
    name: "Bhubaneswar",
    locationQuery: "Bhubaneswar",
    region: "Odisha",
    latitude: 20.2961,
    longitude: 85.8245
  },
  {
    id: "AS-003",
    name: "Guwahati",
    locationQuery: "Guwahati",
    region: "Assam",
    latitude: 26.1445,
    longitude: 91.7362
  },
  {
    id: "PB-011",
    name: "Ludhiana",
    locationQuery: "Ludhiana",
    region: "Punjab",
    latitude: 30.9010,
    longitude: 75.8573
  },
  {
    id: "MP-019",
    name: "Bhopal",
    locationQuery: "Bhopal",
    region: "Madhya Pradesh",
    latitude: 23.2599,
    longitude: 77.4126
  }
];
