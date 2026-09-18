// ════════════════════════════════════════════════════════════
// SECURITY: HTML ESCAPING
// ════════════════════════════════════════════════════════════
// Crisis titles, source names, analysis text etc. originate from external
// feeds (NewsAPI, ACLED) or user-typed input and are rendered via innerHTML
// for layout convenience. Every such value MUST be passed through this
// before interpolation, or a malicious title/source string can inject
// script into every visitor's page (stored XSS).
const ESCAPE_MAP = { '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' };
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ESCAPE_MAP[ch]);
}

// ════════════════════════════════════════════════════════════
// DATA LAYER
// ════════════════════════════════════════════════════════════

const DOMAINS = {
  military:     { icon:'⚔️',  color:'#ff3b3b', name:'Military'      },
  economic:     { icon:'💹',  color:'#ffd93d', name:'Economic'      },
  political:    { icon:'🏛️',  color:'#4e9eff', name:'Political'     },
  environment:  { icon:'🌿',  color:'#3dffaa', name:'Environment'   },
  technology:   { icon:'💻',  color:'#b94eff', name:'Technology'    },
  information:  { icon:'📡',  color:'#ff8833', name:'Info Ops'      },
  cyber:        { icon:'🛡️',  color:'#00e5ff', name:'Cyber'         },
  supply_chain: { icon:'🔗',  color:'#ff6f00', name:'Supply Chain'  },
  climate:      { icon:'🌡️',  color:'#69f0ae', name:'Climate'       },
  health:       { icon:'⚕️',  color:'#f48fb1', name:'Health'        },
  space:        { icon:'🛰️',  color:'#ce93d8', name:'Space'         },
};

const TYPE_META = {
  conflict:      { name:'Conflict',      color:'#ff3b3b' },
  military:      { name:'Military',      color:'#ff4ea0' },
  diplomatic:    { name:'Diplomatic',    color:'#ff8833' },
  economic:      { name:'Economic',      color:'#ffd93d' },
  resource:      { name:'Resource',      color:'#ff6b35' },
  alliance:      { name:'Alliance',      color:'#4e9eff' },
  proxy:         { name:'Proxy',         color:'#b94eff' },
  technology:    { name:'Tech War',      color:'#3dffaa' },
  cyber:         { name:'Cyber Attack',  color:'#00e5ff' },
  infrastructure:{ name:'Infra Attack',  color:'#ff6f00' },
  migration:     { name:'Migration',     color:'#69f0ae' },
  trade_war:     { name:'Trade War',     color:'#ffe082' },
  bioweapon:     { name:'Bioweapon',     color:'#f48fb1' },
  orbital:       { name:'Orbital',       color:'#ce93d8' },
};

// Map crisis types to domains for filtering
function getDomainForType(type) {
  const typeToDomainsMap = {
    conflict:       'military',
    military:       'military',
    proxy:          'military',
    diplomatic:     'political',
    alliance:       'political',
    economic:       'economic',
    trade_war:      'economic',
    resource:       'environment',
    migration:      'climate',
    technology:     'technology',
    cyber:          'cyber',
    infrastructure: 'cyber',
    bioweapon:      'health',
    orbital:        'space',
  };
  return typeToDomainsMap[type] || 'information';
}

// Filter crises by year (2020-2026)
function filterByDateRange(crises, year) {
  const startDate = new Date(year, 0, 1);
  const endDate = new Date(year, 11, 31, 23, 59, 59);

  return crises.filter(c => {
    const crisisDate = new Date(c.date || c.date_start || c.date_updated);
    return !isNaN(crisisDate.getTime()) && crisisDate >= startDate && crisisDate <= endDate;
  });
}

let ACTORS = [
  { id:'US',  name:'USA',     color:'#4488ff', lat:38,   lon:-97  },
  { id:'CN',  name:'China',   color:'#ff4444', lat:35,   lon:105  },
  { id:'RU',  name:'Russia',  color:'#ff9933', lat:60,   lon:90   },
  { id:'EU',  name:'EU',      color:'#88ccff', lat:50,   lon:10   },
  { id:'IN',  name:'India',   color:'#ff7744', lat:20,   lon:77   },
  { id:'IR',  name:'Iran',    color:'#cc44ff', lat:32,   lon:53   },
  { id:'IL',  name:'Israel',  color:'#4488ff', lat:31.5, lon:35   },
  { id:'NK',  name:'N.Korea', color:'#ff4444', lat:39,   lon:127  },
];

let RELATIONSHIPS = [
  { a:'US',  b:'CN',  type:'conflict',   label:'Strategic Rivalry / Tech War'       },
  { a:'US',  b:'RU',  type:'conflict',   label:'Ukraine Proxy Conflict'              },
  { a:'CN',  b:'RU',  type:'alliance',   label:'No-Limits Partnership'               },
  { a:'US',  b:'EU',  type:'alliance',   label:'NATO / Transatlantic Alliance'       },
  { a:'US',  b:'IL',  type:'alliance',   label:'Defense Commitment'                  },
  { a:'IR',  b:'RU',  type:'alliance',   label:'Weapons & Energy Cooperation'        },
  { a:'CN',  b:'IR',  type:'economic',   label:'Oil & Infrastructure Investment'     },
  { a:'US',  b:'IN',  type:'alliance',   label:'Quad Partnership'                    },
  { a:'CN',  b:'IN',  type:'tension',    label:'Border Disputes / Rivalry'           },
  { a:'IR',  b:'IL',  type:'conflict',   label:'Direct Military Confrontation'       },
  { a:'NK',  b:'RU',  type:'alliance',   label:'Weapons Supply'                      },
  { a:'NK',  b:'CN',  type:'economic',   label:'Economic Lifeline'                   },
  { a:'US',  b:'NK',  type:'conflict',   label:'Nuclear Standoff'                    },
];

// CRISES will be loaded from backend API via loadRealData()
let CRISES = [];

// Global state
let zoom = 1, rotX = 0.25, rotY = 0;
let selected = null;
let drag = false, lastMX = 0, lastMY = 0;
let mx = 0, my = 0;
let currentYear = 2026, playDir = 1, playing = false;
let showTrade = false;
let highlightedCountry = null; // { name, feature }
let countryFilter = null;      // country name string — when set, pins + list filter to this country

// Pin fade animation state
const PIN_FADE_STEP = 0.06;             // opacity change per frame (~17 frames = 280ms)
let pinOpacities  = {};                 // crisisId → fade-in opacity (0→1 for new pins)
let fadingOutPins = [];                 // [{c, opacity}] — crises leaving the current year

// ISO 3166-1 numeric → country name (Natural Earth 110m IDs)
const ISO_NAMES = {
  4:'Afghanistan',8:'Albania',12:'Algeria',24:'Angola',32:'Argentina',36:'Australia',
  40:'Austria',50:'Bangladesh',56:'Belgium',68:'Bolivia',76:'Brazil',100:'Bulgaria',
  104:'Myanmar',116:'Cambodia',120:'Cameroon',124:'Canada',140:'Central African Rep.',
  152:'Chile',156:'China',170:'Colombia',180:'DR Congo',178:'Congo',188:'Costa Rica',
  191:'Croatia',192:'Cuba',203:'Czech Republic',208:'Denmark',218:'Ecuador',818:'Egypt',
  231:'Ethiopia',246:'Finland',250:'France',276:'Germany',288:'Ghana',300:'Greece',
  320:'Guatemala',332:'Haiti',340:'Honduras',356:'India',360:'Indonesia',364:'Iran',
  368:'Iraq',372:'Ireland',376:'Israel',380:'Italy',388:'Jamaica',392:'Japan',
  400:'Jordan',398:'Kazakhstan',404:'Kenya',410:'South Korea',408:'North Korea',
  422:'Lebanon',434:'Libya',484:'Mexico',504:'Morocco',508:'Mozambique',524:'Nepal',
  528:'Netherlands',540:'New Caledonia',554:'New Zealand',566:'Nigeria',578:'Norway',
  586:'Pakistan',591:'Panama',604:'Peru',608:'Philippines',616:'Poland',620:'Portugal',
  630:'Puerto Rico',634:'Qatar',642:'Romania',643:'Russia',646:'Rwanda',
  682:'Saudi Arabia',686:'Senegal',694:'Sierra Leone',706:'Somalia',710:'South Africa',
  724:'Spain',144:'Sri Lanka',729:'Sudan',752:'Sweden',756:'Switzerland',760:'Syria',
  158:'Taiwan',764:'Thailand',792:'Turkey',800:'Uganda',804:'Ukraine',784:'UAE',
  826:'United Kingdom',840:'United States',858:'Uruguay',860:'Uzbekistan',
  862:'Venezuela',704:'Vietnam',887:'Yemen',894:'Zambia',716:'Zimbabwe',
};

// Major global trade routes [label, lat1, lon1, lat2, lon2, volume(1-3)]
const TRADE_ROUTES = [
  // Trans-Pacific
  ['Shanghai–LA',    31.2, 121.5,  33.7,-118.2, 3],
  ['Tokyo–LA',       35.7, 139.7,  33.7,-118.2, 2],
  ['Singapore–LA',    1.4, 103.8,  33.7,-118.2, 2],
  // Asia–Europe (via Suez)
  ['Shanghai–Rotterdam', 31.2,121.5, 51.9,  4.5, 3],
  ['Singapore–Rotterdam', 1.4,103.8, 51.9,  4.5, 3],
  ['Mumbai–Suez',     19.1, 72.9,  30.0, 32.5, 2],
  ['Suez–Rotterdam',  30.0, 32.5,  51.9,  4.5, 3],
  // Indian Ocean
  ['Dubai–Mumbai',    25.2, 55.3,  19.1, 72.9, 2],
  ['Singapore–Mumbai', 1.4,103.8,  19.1, 72.9, 2],
  // North Atlantic
  ['NY–Rotterdam',    40.7,-74.0,  51.9,  4.5, 3],
  ['Houston–Rotterdam',29.8,-95.4, 51.9,  4.5, 2],
  // Cape Route (Africa)
  ['Shanghai–Cape Town',31.2,121.5,-33.9, 18.4, 1],
  ['Rotterdam–Cape Town',51.9,4.5, -33.9, 18.4, 1],
  // Americas
  ['NY–Panama',       40.7,-74.0,   9.0,-79.5, 2],
  ['LA–Panama',       33.7,-118.2,  9.0,-79.5, 2],
  // Key straits (short markers)
  ['Strait of Malacca', 1.4,103.8,  5.5, 95.3, 3],
  ['Bab el-Mandeb',  12.5, 43.5,  11.5, 43.5, 2],
  ['Strait of Hormuz',26.5, 56.5,  24.5, 58.5, 3],
];

// Infinite scroll state
let crisisDisplayLimit = 90;  // Show all available crises by default
let crisisDisplayOffset = 0;

// City-level coordinates mapping
const CITY_COORDS = {
  // NORTH AMERICA
  'United States': [
    {name: 'New York', lat: 40.7128, lon: -74.0060},
    {name: 'Los Angeles', lat: 34.0522, lon: -118.2437},
    {name: 'Washington DC', lat: 38.9072, lon: -77.0369},
    {name: 'Chicago', lat: 41.8781, lon: -87.6298},
    {name: 'Houston', lat: 29.7604, lon: -95.3698},
    {name: 'Dallas', lat: 32.7767, lon: -96.7970},
    {name: 'Miami', lat: 25.7617, lon: -80.1918},
    {name: 'Phoenix', lat: 33.4484, lon: -112.0742},
    {name: 'Philadelphia', lat: 39.9526, lon: -75.1652},
    {name: 'San Francisco', lat: 37.7749, lon: -122.4194},
    {name: 'Seattle', lat: 47.6062, lon: -122.3321},
    {name: 'Denver', lat: 39.7392, lon: -104.9903},
    {name: 'Atlanta', lat: 33.7490, lon: -84.3880},
    {name: 'Boston', lat: 42.3601, lon: -71.0589},
  ],
  'Canada': [
    {name: 'Toronto', lat: 43.6532, lon: -79.3832},
    {name: 'Vancouver', lat: 49.2827, lon: -123.1207},
    {name: 'Montreal', lat: 45.5017, lon: -73.5673},
  ],
  'Mexico': [
    {name: 'Mexico City', lat: 19.4326, lon: -99.1332},
    {name: 'Guadalajara', lat: 20.6596, lon: -103.2494},
  ],

  // SOUTH AMERICA
  'Brazil': [
    {name: 'São Paulo', lat: -23.5505, lon: -46.6333},
    {name: 'Rio de Janeiro', lat: -22.9068, lon: -43.1729},
    {name: 'Brasília', lat: -15.7942, lon: -47.8822},
  ],
  'Argentina': [
    {name: 'Buenos Aires', lat: -34.6037, lon: -58.3816},
    {name: 'Córdoba', lat: -31.4135, lon: -64.1811},
  ],
  'Colombia': [
    {name: 'Bogotá', lat: 4.7110, lon: -74.0721},
    {name: 'Medellín', lat: 6.2442, lon: -75.5812},
  ],
  'Peru': [
    {name: 'Lima', lat: -12.0464, lon: -77.0428},
  ],
  'Chile': [
    {name: 'Santiago', lat: -33.8688, lon: -51.2093},
  ],
  'Venezuela': [
    {name: 'Caracas', lat: 10.4806, lon: -66.9036},
  ],

  // EUROPE
  'United Kingdom': [
    {name: 'London', lat: 51.5074, lon: -0.1278},
    {name: 'Manchester', lat: 53.4808, lon: -2.2426},
    {name: 'Edinburgh', lat: 55.9533, lon: -3.1883},
  ],
  'France': [
    {name: 'Paris', lat: 48.8566, lon: 2.3522},
    {name: 'Marseille', lat: 43.2965, lon: 5.3698},
    {name: 'Lyon', lat: 45.7640, lon: 4.8357},
  ],
  'Germany': [
    {name: 'Berlin', lat: 52.5200, lon: 13.4050},
    {name: 'Munich', lat: 48.1351, lon: 11.5820},
    {name: 'Hamburg', lat: 53.5511, lon: 9.9937},
  ],
  'Italy': [
    {name: 'Rome', lat: 41.9028, lon: 12.4964},
    {name: 'Milan', lat: 45.4642, lon: 9.1900},
  ],
  'Spain': [
    {name: 'Madrid', lat: 40.4168, lon: -3.7038},
    {name: 'Barcelona', lat: 41.3851, lon: 2.1734},
  ],
  'Ukraine': [
    {name: 'Kyiv', lat: 50.4501, lon: 30.5234},
    {name: 'Kharkiv', lat: 50.0038, lon: 36.2304},
    {name: 'Odesa', lat: 46.4856, lon: 30.7326},
  ],
  'Poland': [
    {name: 'Warsaw', lat: 52.2297, lon: 21.0122},
    {name: 'Kraków', lat: 50.0647, lon: 19.9450},
  ],
  'Netherlands': [
    {name: 'Amsterdam', lat: 52.3676, lon: 4.9041},
  ],
  'Greece': [
    {name: 'Athens', lat: 37.9838, lon: 23.7275},
  ],

  // MIDDLE EAST & CENTRAL ASIA
  'Iran': [
    {name: 'Tehran', lat: 35.6892, lon: 51.3890},
    {name: 'Isfahan', lat: 32.6546, lon: 51.6680},
    {name: 'Tabriz', lat: 38.0808, lon: 46.2919},
    {name: 'Shiraz', lat: 29.6399, lon: 52.5347},
    {name: 'Qom', lat: 34.6413, lon: 50.8759},
    {name: 'Mashhad', lat: 36.2605, lon: 59.5007},
    {name: 'Ahvaz', lat: 31.3183, lon: 48.6706},
    {name: 'Rasht', lat: 37.2808, lon: 49.5832},
    {name: 'Yazd', lat: 31.8974, lon: 54.3569},
  ],
  'Iraq': [
    {name: 'Baghdad', lat: 33.3128, lon: 44.3615},
    {name: 'Basra', lat: 30.4958, lon: 47.8079},
  ],
  'Israel': [
    {name: 'Tel Aviv', lat: 32.0853, lon: 34.7818},
    {name: 'Jerusalem', lat: 31.7683, lon: 35.2137},
    {name: 'Haifa', lat: 32.8191, lon: 34.9937},
    {name: 'Beer Sheva', lat: 31.2461, lon: 34.7915},
    {name: 'Ashdod', lat: 31.8070, lon: 34.6463},
    {name: 'Petah Tikva', lat: 32.0864, lon: 34.8864},
  ],
  'Saudi Arabia': [
    {name: 'Riyadh', lat: 24.7136, lon: 46.6753},
    {name: 'Jeddah', lat: 21.5169, lon: 39.1925},
  ],
  'United Arab Emirates': [
    {name: 'Dubai', lat: 25.2048, lon: 55.2708},
    {name: 'Abu Dhabi', lat: 24.4539, lon: 54.3773},
  ],
  'Turkey': [
    {name: 'Istanbul', lat: 41.0082, lon: 28.9784},
    {name: 'Ankara', lat: 39.9334, lon: 32.8597},
  ],
  'Syria': [
    {name: 'Damascus', lat: 33.5138, lon: 36.2765},
    {name: 'Aleppo', lat: 36.2021, lon: 37.1343},
  ],
  'Jordan': [
    {name: 'Amman', lat: 31.9454, lon: 35.9284},
  ],
  'Lebanon': [
    {name: 'Beirut', lat: 33.8547, lon: 35.4758},
  ],
  'Pakistan': [
    {name: 'Islamabad', lat: 33.6844, lon: 73.0479},
    {name: 'Karachi', lat: 24.8607, lon: 67.0011},
  ],
  'Afghanistan': [
    {name: 'Kabul', lat: 34.5553, lon: 69.2075},
  ],
  'Kazakhstan': [
    {name: 'Almaty', lat: 43.2380, lon: 76.9502},
    {name: 'Astana', lat: 51.1694, lon: 71.4491},
  ],

  // ASIA
  'Russia': [
    {name: 'Moscow', lat: 55.7558, lon: 37.6173},
    {name: 'St. Petersburg', lat: 59.9311, lon: 30.3609},
    {name: 'Vladivostok', lat: 43.1056, lon: 131.8735},
    {name: 'Novosibirsk', lat: 55.0415, lon: 82.9346},
  ],
  'China': [
    {name: 'Beijing', lat: 39.9042, lon: 116.4074},
    {name: 'Shanghai', lat: 31.2304, lon: 121.4737},
    {name: 'Hong Kong', lat: 22.3193, lon: 114.1694},
    {name: 'Shenzhen', lat: 22.5431, lon: 114.0579},
    {name: 'Chongqing', lat: 29.4316, lon: 106.9123},
    {name: 'Xi\'an', lat: 34.3416, lon: 109.5149},
    {name: 'Wuhan', lat: 30.5928, lon: 114.3055},
    {name: 'Guangzhou', lat: 23.1291, lon: 113.2644},
    {name: 'Chengdu', lat: 30.5728, lon: 104.0668},
    {name: 'Hangzhou', lat: 30.2875, lon: 120.1551},
  ],
  'India': [
    {name: 'New Delhi', lat: 28.6139, lon: 77.2090},
    {name: 'Mumbai', lat: 19.0760, lon: 72.8777},
    {name: 'Bangalore', lat: 12.9716, lon: 77.5946},
    {name: 'Kolkata', lat: 22.5726, lon: 88.3639},
  ],
  'Japan': [
    {name: 'Tokyo', lat: 35.6762, lon: 139.6503},
    {name: 'Osaka', lat: 34.6937, lon: 135.5023},
  ],
  'South Korea': [
    {name: 'Seoul', lat: 37.5665, lon: 126.9780},
  ],
  'North Korea': [
    {name: 'Pyongyang', lat: 39.0193, lon: 125.7581},
  ],
  'Vietnam': [
    {name: 'Hanoi', lat: 21.0285, lon: 105.8542},
    {name: 'Ho Chi Minh City', lat: 10.7769, lon: 106.6869},
  ],
  'Thailand': [
    {name: 'Bangkok', lat: 13.7563, lon: 100.5018},
  ],
  'Philippines': [
    {name: 'Manila', lat: 14.5995, lon: 120.9842},
  ],
  'Indonesia': [
    {name: 'Jakarta', lat: -6.2088, lon: 106.8456},
  ],
  'Myanmar': [
    {name: 'Yangon', lat: 16.8661, lon: 96.1951},
    {name: 'Naypyidaw', lat: 19.7554, lon: 96.0794},
  ],
  'Malaysia': [
    {name: 'Kuala Lumpur', lat: 3.1390, lon: 101.6869},
  ],
  'Singapore': [
    {name: 'Singapore', lat: 1.3521, lon: 103.8198},
  ],

  // AFRICA
  'Egypt': [
    {name: 'Cairo', lat: 30.0444, lon: 31.2357},
    {name: 'Alexandria', lat: 31.2001, lon: 29.9187},
  ],
  'Nigeria': [
    {name: 'Lagos', lat: 6.5244, lon: 3.3792},
    {name: 'Abuja', lat: 9.0765, lon: 7.3986},
  ],
  'South Africa': [
    {name: 'Johannesburg', lat: -26.2023, lon: 28.0436},
    {name: 'Cape Town', lat: -33.9249, lon: 18.4241},
    {name: 'Pretoria', lat: -25.7461, lon: 28.2293},
  ],
  'Ethiopia': [
    {name: 'Addis Ababa', lat: 9.0320, lon: 38.7469},
  ],
  'Kenya': [
    {name: 'Nairobi', lat: -1.2864, lon: 36.8172},
  ],
  'Libya': [
    {name: 'Tripoli', lat: 32.8872, lon: 13.1913},
  ],
  'Sudan': [
    {name: 'Khartoum', lat: 15.5007, lon: 32.5599},
  ],
  'Morocco': [
    {name: 'Casablanca', lat: 33.5731, lon: -7.5898},
    {name: 'Rabat', lat: 34.0209, lon: -6.8416},
  ],
  'Tunisia': [
    {name: 'Tunis', lat: 36.8065, lon: 10.1686},
  ],
  'Algeria': [
    {name: 'Algiers', lat: 36.7538, lon: 3.0588},
  ],
  'Angola': [
    {name: 'Luanda', lat: -8.8383, lon: 13.2344},
  ],
  'Mozambique': [
    {name: 'Maputo', lat: -23.8637, lon: 35.3300},
  ],
  'Zimbabwe': [
    {name: 'Harare', lat: -17.8252, lon: 31.0335},
  ],

  // OCEANIA
  'Australia': [
    {name: 'Sydney', lat: -33.8688, lon: 151.2093},
    {name: 'Melbourne', lat: -37.8136, lon: 144.9631},
    {name: 'Brisbane', lat: -27.4698, lon: 153.0251},
  ],
  'New Zealand': [
    {name: 'Auckland', lat: -37.0882, lon: 174.8853},
    {name: 'Wellington', lat: -41.2865, lon: 174.7762},
  ],
};

function getRandomCityCoords(country) {
  // Normalize country names (handle various formats)
  const countryNormalized = {
    'Us': 'United States',
    'USA': 'United States',
    'UK': 'United Kingdom',
    'GB': 'United Kingdom',
    'KR': 'South Korea',
    'NK': 'North Korea',
    'UAE': 'United Arab Emirates',
    'SA': 'Saudi Arabia',
    'ROK': 'South Korea',
    'DPRK': 'North Korea',
    'PRC': 'China',
    'HK': 'Hong Kong',
  }[country] || country;

  let cities = CITY_COORDS[countryNormalized];

  // If country not found, try to pick a reasonable regional fallback
  if (!cities) {
    if (countryNormalized.includes('Europe') || countryNormalized === 'European Union') {
      cities = CITY_COORDS['Germany']; // Central Europe default
    } else if (countryNormalized.includes('Africa')) {
      cities = CITY_COORDS['Nigeria']; // Central Africa default
    } else if (countryNormalized.includes('Asia')) {
      cities = CITY_COORDS['India']; // South Asia default
    } else {
      cities = CITY_COORDS['United States']; // Global default
    }
  }

  if (!cities) return null;
  return cities[Math.floor(Math.random() * cities.length)];
}

// Alerts
const ALERTS = [
  { text: '🔴 CRITICAL: Iran-US Military Tensions', color: '#ff3b3b' },
  { text: '🟡 WARNING: Taiwan Strait Activity', color: '#ffd93d' },
  { text: '🟠 ALERT: Middle East Instability', color: '#ff8833' },
];

// Layer toggles
let showArcs  = false;
let showHeat  = false;
let showCasc  = false;
let flatMap   = false;
let cascadeActive = false;

// Severity filter (0 = all, 80 = critical only)
let minSeverityFilter = 0;

// Bookmarks persisted in localStorage — always coerce IDs to numbers
const bookmarks = new Set(
  (JSON.parse(localStorage.getItem('geointel_bookmarks') || '[]')).map(Number)
);

// Canvas setup
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

// ── High-DPI (retina) rendering ────────────────────────────────────────────
// A canvas's `width`/`height` are its backing-store resolution; without this,
// they get set to the CSS pixel size, so on any HiDPI display (most modern
// laptops/phones) the browser upscales a lower-res bitmap and everything —
// globe, borders, pins, text — renders soft. Fix: size the backing store to
// CSS-size * devicePixelRatio, then scale the context so all drawing code
// keeps working in CSS-pixel coordinates (R()/CX()/CY() below use
// clientWidth/clientHeight, not width/height, for exactly this reason).
function fitCanvasToDisplay(cvs, context) {
  const dpr  = window.devicePixelRatio || 1;
  const cssW = cvs.clientWidth  || cvs.offsetWidth;
  const cssH = cvs.clientHeight || cvs.offsetHeight;
  const pxW  = Math.round(cssW * dpr);
  const pxH  = Math.round(cssH * dpr);
  if (cvs.width !== pxW || cvs.height !== pxH) {
    cvs.width  = pxW;
    cvs.height = pxH;
  }
  // setTransform (not scale) so repeated calls don't compound the scale factor.
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { cssW, cssH };
}

fitCanvasToDisplay(canvas, ctx);

// Clamped to a minimum of 1px: on a narrow/short canvas (small window,
// mobile portrait layout, or a transient layout state where the pane hasn't
// reached its normal size yet) `min(width,height)/2 - 48` can go negative,
// and createRadialGradient() throws synchronously on a negative radius —
// which, since this runs inside drawGlobe() before requestAnimationFrame()
// reschedules the next frame, permanently kills the render loop rather
// than just drawing one bad frame.
function R()  { return Math.max(1, (Math.min(canvas.clientWidth, canvas.clientHeight) / 2 - 48) * zoom); }
function CX() { return canvas.clientWidth  / 2; }
function CY() { return canvas.clientHeight / 2; }

// Cache cos/sin(rotX) per rotation value instead of recomputing them for
// every single projected point — with a high-resolution world map this is
// called hundreds of thousands of times per frame, and rotX changes once
// per frame (or not at all while idle), so this turns 2 trig calls per
// point into a single float comparison for all but the first point.
let _rotXCache = NaN, _cosRotX = 1, _sinRotX = 0;
function project(lat, lon) {
  if (rotX !== _rotXCache) { _cosRotX = Math.cos(rotX); _sinRotX = Math.sin(rotX); _rotXCache = rotX; }
  const phi  = lat * Math.PI / 180;
  const lam  = lon * Math.PI / 180;
  const cp   = Math.cos(phi);
  const x    = cp  * Math.sin(lam + rotY);
  const y    = Math.sin(phi) * _cosRotX - cp * Math.cos(lam + rotY) * _sinRotX;
  const z    = Math.sin(phi) * _sinRotX + cp * Math.cos(lam + rotY) * _cosRotX;
  const r    = R();
  return { sx: CX() + r * x, sy: CY() - r * y, z };
}

// Draw filled/stroked geo ring. `targetCtx` defaults to the main canvas
// context but can be an offscreen one — see the high-detail land cache in
// drawGlobe(), which renders the (expensive, ~80k-point) 50m mesh into a
// cached bitmap rather than replaying this every frame.
function geoRing(ring, fill, targetCtx = ctx) {
  let started = false;
  for (let i = 0; i < ring.length; i++) {
    const [lo, la] = ring[i];
    const p = project(la, lo);
    // Frustum culling: skip back-facing coordinates (z < -0.1)
    if (p.z < -0.1) { if (started) { fill ? targetCtx.fill() : targetCtx.stroke(); started = false; } continue; }
    if (!started) { targetCtx.beginPath(); targetCtx.moveTo(p.sx, p.sy); started = true; }
    else targetCtx.lineTo(p.sx, p.sy);
  }
  if (started) { fill ? targetCtx.fill() : targetCtx.stroke(); }
}

// Hit-test: is screen point (x,y) inside the projected polygon of a TopoJSON feature?
function isPointInCountry(feature, x, y) {
  const geom = feature.geometry;
  if (!geom) return false;
  const rings = geom.type === 'Polygon'
    ? geom.coordinates
    : geom.coordinates.flatMap(p => p);
  ctx.beginPath();
  for (const ring of rings) {
    let first = true;
    for (const [lo, la] of ring) {
      const p = project(la, lo);
      if (p.z < -0.05) { first = true; continue; }
      if (first) { ctx.moveTo(p.sx, p.sy); first = false; }
      else ctx.lineTo(p.sx, p.sy);
    }
    ctx.closePath();
  }
  return ctx.isPointInPath(x, y);
}

// Estimate trade volume label from route volume tier
const TRADE_VOL_LABEL = ['', '~$200B/yr', '~$500B/yr', '~$1T+/yr'];

// Great-circle distance in km between two lat/lon points (haversine).
// Replaces a naive sqrt(dLat²+dLon²) "degree distance" that was labeled
// great-circle but wasn't one: it treated 1° of longitude as the same
// real-world distance as 1° of latitude everywhere, true only at the
// equator — longitude degrees shrink by cos(latitude) toward the poles,
// so the old formula understated how close two points actually are at
// high latitude (e.g. North Atlantic / Arctic shipping routes, or any
// crisis proximity check north of ~40°).
const EARTH_RADIUS_KM = 6371;
function geoDistKm(la1, lo1, la2, lo2) {
  const phi1 = la1 * Math.PI / 180, phi2 = la2 * Math.PI / 180;
  const dPhi = (la2 - la1) * Math.PI / 180;
  const dLambda = (lo2 - lo1) * Math.PI / 180;
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

// For each trade route, compute a risk level (0–3) based on nearby active crises
function routeRiskLevel(lat1, lon1, lat2, lon2) {
  // Sample along the *actual* great-circle path — the same SLERP used to
  // draw the arc (see drawArc/latLonToVec/slerpVec below) — rather than
  // naive lat/lon linear interpolation. That mattered a lot here: every
  // trans-Pacific route in TRADE_ROUTES (Shanghai-LA, Tokyo-LA,
  // Singapore-LA) crosses the antimeridian, where linearly "averaging"
  // longitude lands nowhere near the real path — e.g. Shanghai (121.5°E)
  // and LA (-118.2°) average to ~1.65°E, near Africa, while the real
  // route crosses the Pacific near 180°. Risk was being checked against
  // the wrong hemisphere entirely for those routes.
  const v1 = latLonToVec(lat1, lon1);
  const v2 = latLonToVec(lat2, lon2);
  const samples = [0, 0.25, 0.5, 0.75, 1].map(t => vecToLatLon(slerpVec(v1, v2, t)));
  let maxSev = 0;
  let nearby = 0;
  for (const c of CRISES) {
    for (const [sla, slo] of samples) {
      if (geoDistKm(c.lat || 0, c.lon || 0, sla, slo) < 1650) {  // ~15° at the equator
        nearby++;
        maxSev = Math.max(maxSev, c.severity || 0);
        break; // count each crisis once
      }
    }
  }
  if (maxSev > 80 || nearby >= 5) return 3; // critical
  if (maxSev > 60 || nearby >= 3) return 2; // elevated
  if (nearby >= 1)                return 1; // caution
  return 0;                                 // clear
}

const ROUTE_RISK_COLORS = ['#3dffaa', '#ffd93d', '#ff8833', '#ff3b3b'];
const ROUTE_RISK_LABELS = ['Clear', 'Caution', 'Elevated', 'Critical'];

// Stores screen-space midpoints for hover detection, updated each draw
let tradeRouteScreenPts = [];

// Draw all active trade routes, color-coded by disruption risk
function drawTradeRoutes() {
  tradeRouteScreenPts = [];
  TRADE_ROUTES.forEach(([label, lat1, lon1, lat2, lon2, vol], idx) => {
    const risk  = routeRiskLevel(lat1, lon1, lat2, lon2);
    const color = ROUTE_RISK_COLORS[risk];
    const alpha = 0.3 + vol * 0.1 + (risk > 0 ? 0.15 : 0);
    const width = 0.7 + vol * 0.4 + (risk * 0.3);
    drawArc(lat1, lon1, lat2, lon2, color, width, alpha);

    // Store midpoint screen coords for hover detection
    const midLat = (lat1 + lat2) / 2, midLon = (lon1 + lon2) / 2;
    const mp = project(midLat, midLon);
    if (mp.z > 0) tradeRouteScreenPts.push({ idx, label, vol, risk, sx: mp.sx, sy: mp.sy });
  });
}

function drawGeoFeature(geom, fill, targetCtx = ctx) {
  if (!geom) return;
  if (geom.type === 'Polygon')      geom.coordinates.forEach(r => geoRing(r, fill, targetCtx));
  else if (geom.type === 'MultiPolygon') geom.coordinates.forEach(p => p.forEach(r => geoRing(r, fill, targetCtx)));
}

function drawGeoMesh(geom, targetCtx = ctx) {
  if (!geom || geom.type !== 'MultiLineString') return;
  geom.coordinates.forEach(line => {
    let started = false;
    for (const [lo, la] of line) {
      const p = project(la, lo);
      if (p.z < 0) { if (started) { targetCtx.stroke(); started = false; } continue; }
      if (!started) { targetCtx.beginPath(); targetCtx.moveTo(p.sx, p.sy); started = true; }
      else targetCtx.lineTo(p.sx, p.sy);
    }
    if (started) targetCtx.stroke();
  });
}

// Convert lat/lon to 3D unit vector
function latLonToVec(lat, lon) {
  const phi = lat * Math.PI / 180;
  const lam = lon * Math.PI / 180;
  return [Math.cos(phi) * Math.cos(lam), Math.cos(phi) * Math.sin(lam), Math.sin(phi)];
}

// Spherical linear interpolation (SLERP) for great-circle arc
function slerpVec(v1, v2, t) {
  const dot = Math.max(-1, Math.min(1, v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]));
  const omega = Math.acos(dot);
  if (Math.abs(omega) < 1e-6) return v1;
  const s = Math.sin(omega);
  const s1 = Math.sin((1 - t) * omega) / s;
  const s2 = Math.sin(t * omega) / s;
  return [s1*v1[0]+s2*v2[0], s1*v1[1]+s2*v2[1], s1*v1[2]+s2*v2[2]];
}

// Convert 3D unit vector back to lat/lon
function vecToLatLon(v) {
  return [Math.asin(v[2]) * 180 / Math.PI, Math.atan2(v[1], v[0]) * 180 / Math.PI];
}

// Draw great-circle arc between two lat/lon points
function drawArc(lat1, lon1, lat2, lon2, color, width = 1.2, alpha = 0.5) {
  const steps = 60;
  const v1 = latLonToVec(lat1, lon1);
  const v2 = latLonToVec(lat2, lon2);
  const pts = [];
  for (let i = 0; i <= steps; i++) {
    const [la, lo] = vecToLatLon(slerpVec(v1, v2, i / steps));
    pts.push(project(la, lo));
  }

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;

  let started = false;
  for (const p of pts) {
    if (p.z < 0) { if (started) { ctx.stroke(); started = false; } continue; }
    if (!started) { ctx.beginPath(); ctx.moveTo(p.sx, p.sy); started = true; }
    else ctx.lineTo(p.sx, p.sy);
  }
  if (started) ctx.stroke();
  ctx.restore();
}

// Pulse animation state
let pulse = 0;

// Canvas size optimization - track previous dimensions to avoid redundant resizing
let lastCanvasWidth = 0, lastCanvasHeight = 0;

// ── Adaptive level-of-detail for the world map ──────────────────────────────
// countries-50m.json (~80k boundary points) looks dramatically better than
// the old 110m file, but re-projecting every point every frame at that
// resolution is too expensive to do continuously while the globe is
// spinning or being dragged. So: keep the light 110m mesh as the "moving"
// mesh (used while there's been recent rotation/pan/zoom input) and swap to
// the full 50m mesh once things have been still for SETTLE_DELAY_MS — the
// user gets full detail on the still frame they're actually looking at,
// without the heavier mesh ever needing to be re-projected while in motion.
// (10m — ~477k points — was tried first, but the one-time redraw on settle
// measured ~4.9s, a hard freeze; 50m measures ~0.7s, which is far more
// tolerable for a one-time-per-settle cost.)
let worldTopoLow = null, worldTopoHigh = null;
let topoFeaturesLow = null, topoMeshLow = null;
let topoFeaturesHigh = null, topoMeshHigh = null;
const SETTLE_DELAY_MS = 220;
let lastMotionAt = 0;
function markMotion() { lastMotionAt = performance.now(); }
function isSettled() { return (performance.now() - lastMotionAt) > SETTLE_DELAY_MS; }

// Build (once) and return whichever resolution's {features, mesh} is right
// for the current motion state. Cheap to call every frame — the expensive
// topojson.feature()/mesh() conversions only ever run once per mesh.
function getActiveTopo() {
  if (!topoFeaturesLow && worldTopoLow) {
    topoFeaturesLow = topojson.feature(worldTopoLow, worldTopoLow.objects.countries).features;
    topoMeshLow     = topojson.mesh(worldTopoLow, worldTopoLow.objects.countries, (a, b) => a !== b);
  }
  if (topoFeaturesHigh && isSettled()) {
    return { features: topoFeaturesHigh, mesh: topoMeshHigh };
  }
  return { features: topoFeaturesLow, mesh: topoMeshLow };
}

// ════════════════════════════════════════════════════════════
// FLAT MAP (equirectangular 2D projection with pan + zoom)
// ════════════════════════════════════════════════════════════
const flatCanvas = document.getElementById('flatMapCanvas');
const fctx = flatCanvas.getContext('2d');

// Pan/zoom state for flat map
let fZoom = 1, fPanX = 0, fPanY = 0;
let fDrag = false, fLastX = 0, fLastY = 0;

function flatProject(lat, lon) {
  const W = flatCanvas.clientWidth;
  const H = flatCanvas.clientHeight;
  const baseX = (lon + 180) / 360 * W;
  const baseY = (90 - lat) / 180 * H;
  return {
    x: (baseX - W / 2) * fZoom + W / 2 + fPanX,
    y: (baseY - H / 2) * fZoom + H / 2 + fPanY,
  };
}

function flatUnprojectClick(screenX, screenY) {
  const W = flatCanvas.clientWidth, H = flatCanvas.clientHeight;
  const baseX = (screenX - W / 2 - fPanX) / fZoom + W / 2;
  const baseY = (screenY - H / 2 - fPanY) / fZoom + H / 2;
  return { lat: 90 - baseY / H * 180, lon: baseX / W * 360 - 180 };
}

function drawFlatMap() {
  const W = flatCanvas.clientWidth, H = flatCanvas.clientHeight;
  if (!W || !H) return;
  fitCanvasToDisplay(flatCanvas, fctx);
  fctx.clearRect(0, 0, W, H);

  // Background
  fctx.fillStyle = '#07090f';
  fctx.fillRect(0, 0, W, H);
  const ocean = fctx.createLinearGradient(0, 0, 0, H);
  ocean.addColorStop(0, '#071420'); ocean.addColorStop(1, '#050d18');
  fctx.fillStyle = ocean; fctx.fillRect(0, 0, W, H);

  fctx.save();
  // Apply pan/zoom transform around center
  fctx.translate(W / 2 + fPanX, H / 2 + fPanY);
  fctx.scale(fZoom, fZoom);
  fctx.translate(-W / 2, -H / 2);

  // Grid lines
  fctx.strokeStyle = 'rgba(0,212,255,0.05)';
  fctx.lineWidth = 0.5 / fZoom;
  for (let lat = -90; lat <= 90; lat += 30) {
    const y = (90 - lat) / 180 * H;
    fctx.beginPath(); fctx.moveTo(0, y); fctx.lineTo(W, y); fctx.stroke();
  }
  for (let lon = -180; lon <= 180; lon += 30) {
    const x = (lon + 180) / 360 * W;
    fctx.beginPath(); fctx.moveTo(x, 0); fctx.lineTo(x, H); fctx.stroke();
  }

  // Countries
  if (worldTopoLow) {
    const { features } = getActiveTopo();
    features.forEach(f => {
      const isHl = highlightedCountry && highlightedCountry.feature === f;
      fctx.fillStyle   = isHl ? 'rgba(0,212,255,0.25)' : 'rgba(26,60,40,0.85)';
      fctx.strokeStyle = isHl ? 'rgba(0,212,255,0.8)'  : 'rgba(255,255,255,0.15)';
      fctx.lineWidth   = (isHl ? 1.5 : 0.4) / fZoom;
      const geom = f.geometry; if (!geom) return;
      const polys = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates;
      polys.forEach(poly => poly.forEach(ring => {
        fctx.beginPath();
        ring.forEach(([lo, la], i) => {
          const px = (lo + 180) / 360 * W;
          const py = (90 - la) / 180 * H;
          i === 0 ? fctx.moveTo(px, py) : fctx.lineTo(px, py);
        });
        fctx.closePath(); fctx.fill(); fctx.stroke();
      }));
    });
  }

  // Crisis pins — same filters as drawPins() so pin counts match
  const pool = CRISES.filter(c => {
    if (minSeverityFilter > 0 && (c.severity || 0) < minSeverityFilter) return false;
    if (countryFilter && c.country !== countryFilter) return false;
    if (!activeTypes.has(c.type)) return false;
    if (activeDomains.size > 0 && !activeDomains.has(getDomainForType(c.type))) return false;
    const d = new Date(c.date_start || c.date);
    return !isNaN(d) && d.getFullYear() <= currentYear;
  });
  pool.forEach(c => {
    if (c.lat == null || c.lon == null) return;
    const px = (c.lon + 180) / 360 * W;
    const py = (90 - c.lat) / 180 * H;
    const col = TYPE_META[c.type]?.color || '#fff';
    const isSel = c.id === selected?.id;
    const r2 = (isSel ? 7 : 4.5) / fZoom;
    fctx.save();
    fctx.shadowColor = col; fctx.shadowBlur = isSel ? 12 : 5;
    fctx.fillStyle = col;
    fctx.beginPath(); fctx.arc(px, py, r2, 0, Math.PI * 2); fctx.fill();
    fctx.strokeStyle = 'rgba(255,255,255,0.7)';
    fctx.lineWidth = 1 / fZoom; fctx.stroke();
    fctx.restore();
    // Store screen coords (accounting for transform) for click detection
    c._screenX = (px - W / 2) * fZoom + W / 2 + fPanX;
    c._screenY = (py - H / 2) * fZoom + H / 2 + fPanY;
  });

  fctx.restore(); // end transform

  // Lat/lon labels (screen space — not affected by transform)
  fctx.fillStyle = 'rgba(0,212,255,0.25)';
  fctx.font = '9px Segoe UI'; fctx.textAlign = 'left';
  fctx.fillText(`Zoom: ${fZoom.toFixed(1)}×  Drag to pan  Scroll to zoom`, 8, H - 8);
}

// Flat map mouse events
flatCanvas.addEventListener('wheel', e => {
  if (!flatMap) return;
  e.preventDefault();
  markMotion();
  const rect = flatCanvas.getBoundingClientRect();
  const mx2 = e.clientX - rect.left, my2 = e.clientY - rect.top;
  const scaleFactor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
  // Zoom toward cursor
  fPanX = mx2 + (fPanX - mx2) * scaleFactor;
  fPanY = my2 + (fPanY - my2) * scaleFactor;
  fZoom = Math.max(1, Math.min(12, fZoom * scaleFactor));
  if (fZoom === 1) { fPanX = 0; fPanY = 0; } // reset pan at min zoom
  drawFlatMap();
}, { passive: false });

flatCanvas.addEventListener('mousedown', e => {
  if (!flatMap) return;
  fDrag = true; fLastX = e.clientX; fLastY = e.clientY;
  flatCanvas.style.cursor = 'grabbing';
});
document.addEventListener('mouseup', () => {
  fDrag = false;
  if (flatMap) flatCanvas.style.cursor = 'grab';
});
flatCanvas.addEventListener('mousemove', e => {
  if (!flatMap || !fDrag) return;
  fPanX += e.clientX - fLastX;
  fPanY += e.clientY - fLastY;
  fLastX = e.clientX; fLastY = e.clientY;
  markMotion();
  drawFlatMap();
});

// Touch support for flat map
flatCanvas.addEventListener('touchstart', e => {
  if (!flatMap || e.touches.length !== 1) return;
  fDrag = true; fLastX = e.touches[0].clientX; fLastY = e.touches[0].clientY;
}, { passive: true });
flatCanvas.addEventListener('touchend', () => { fDrag = false; });
flatCanvas.addEventListener('touchmove', e => {
  if (!flatMap || !fDrag || e.touches.length !== 1) return;
  e.preventDefault();
  fPanX += e.touches[0].clientX - fLastX;
  fPanY += e.touches[0].clientY - fLastY;
  fLastX = e.touches[0].clientX; fLastY = e.touches[0].clientY;
  markMotion();
  drawFlatMap();
}, { passive: false });

// ── Terrain relief shading ───────────────────────────────────────────────
// Real elevation data (NASA-derived grayscale equirectangular bump map),
// loaded once and kept as raw pixel data so sampling it per-globe-pixel is
// just an array index, not a draw call. Only ever applied inside the
// high-detail cached bitmap (see applyTerrainShading below) — like the
// 50m country mesh, per-pixel raycasting the whole globe disc is too
// expensive to redo every frame, so it only runs once per settle.
let elevationPixels = null, elevationW = 0, elevationH = 0;
(function loadElevationTexture() {
  const img = new Image();
  img.onload = () => {
    const off = document.createElement('canvas');
    off.width = img.width;
    off.height = img.height;
    const offCtx = off.getContext('2d');
    offCtx.drawImage(img, 0, 0);
    elevationPixels = offCtx.getImageData(0, 0, img.width, img.height).data;
    elevationW = img.width;
    elevationH = img.height;
  };
  img.onerror = () => console.warn('Terrain elevation texture failed to load — globe will render without relief shading.');
  img.src = 'earth-elevation.jpg';
})();

// Inverse of project(): given a point on the unit sphere in screen-facing
// coordinates (nx, ny, nz — z toward the viewer), recover [lat, lon] in
// degrees. Used to sample the equirectangular elevation texture per pixel.
// Derived by inverting project()'s rotation order: project() first builds
// the standard spherical vector (cos(phi)cos(u), cos(phi)sin(u), sin(phi))
// with u = lon + rotY, then rotates the (z, that-x) pair by rotX to get
// (y, z); this undoes both steps in reverse.
function unprojectToLatLon(nx, ny, nz, cosRotX, sinRotX) {
  const s = ny * cosRotX + nz * sinRotX;       // sin(phi)
  const a = -ny * sinRotX + nz * cosRotX;      // cos(phi) * cos(u)
  const phi = Math.asin(Math.max(-1, Math.min(1, s)));
  const u = Math.atan2(nx, a);
  const lam = u - rotY;
  const lat = phi * 180 / Math.PI;
  let lon = lam * 180 / Math.PI;
  lon = ((lon + 180) % 360 + 360) % 360 - 180; // normalize to [-180, 180]
  return [lat, lon];
}

// Bilinear-sample the elevation texture at (lon, lat) instead of a nearest-
// neighbor lookup — at typical globe-zoom levels each source texel covers
// several screen pixels, so nearest-neighbor produced visibly blocky
// terrain edges. Blends the 4 surrounding texels; wraps horizontally
// (longitude is circular) and clamps vertically (no wrap at the poles).
function sampleElevationBilinear(lon, lat) {
  const fx = (lon + 180) / 360 * elevationW - 0.5;
  const fy = (90 - lat) / 180 * elevationH - 0.5;
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const tx = fx - x0, ty = fy - y0;
  const wrapX = x => ((x % elevationW) + elevationW) % elevationW;
  const clampY = y => Math.min(elevationH - 1, Math.max(0, y));
  const x0w = wrapX(x0), x1w = wrapX(x0 + 1);
  const y0c = clampY(y0), y1c = clampY(y0 + 1);
  const p00 = elevationPixels[(y0c * elevationW + x0w) * 4];
  const p10 = elevationPixels[(y0c * elevationW + x1w) * 4];
  const p01 = elevationPixels[(y1c * elevationW + x0w) * 4];
  const p11 = elevationPixels[(y1c * elevationW + x1w) * 4];
  const top = p00 + (p10 - p00) * tx;
  const bottom = p01 + (p11 - p01) * tx;
  return top + (bottom - top) * ty;
}

// Darkens valleys / lightens peaks on the already-filled land pixels of an
// offscreen bitmap, by inverse-projecting each land pixel back to lat/lon
// and sampling the elevation texture there. Only touches pixels the land
// fill already made opaque (alpha > 0) — ocean and space are left alone,
// so the existing ocean gradient (drawn separately, underneath) shows
// through unaffected.
function applyTerrainShading(offCtx, cx, cy, r) {
  if (!elevationPixels) return; // texture still loading — skip gracefully
  const w = offCtx.canvas.width, h = offCtx.canvas.height;
  const minX = Math.max(0, Math.floor(cx - r)), maxX = Math.min(w, Math.ceil(cx + r));
  const minY = Math.max(0, Math.floor(cy - r)), maxY = Math.min(h, Math.ceil(cy + r));
  if (maxX <= minX || maxY <= minY) return;

  const imgData = offCtx.getImageData(minX, minY, maxX - minX, maxY - minY);
  const px = imgData.data;
  const boxW = maxX - minX;
  const cosRotX = Math.cos(rotX), sinRotX = Math.sin(rotX);
  const rSq = r * r;

  for (let py = minY; py < maxY; py++) {
    const ddy = py - cy;
    for (let pxi = minX; pxi < maxX; pxi++) {
      const idx = ((py - minY) * boxW + (pxi - minX)) * 4;
      if (px[idx + 3] === 0) continue; // not land
      const ddx = pxi - cx;
      const distSq = ddx * ddx + ddy * ddy;
      if (distSq > rSq) continue;
      const nx = ddx / r, ny = -ddy / r;
      const nzSq = 1 - nx * nx - ny * ny;
      if (nzSq < 0) continue;
      const nz = Math.sqrt(nzSq);

      const [lat, lon] = unprojectToLatLon(nx, ny, nz, cosRotX, sinRotX);
      const elev = sampleElevationBilinear(lon, lat);

      // Shade around a neutral midpoint so typical lowland terrain stays
      // close to the original land color, high peaks brighten it, and
      // ocean-floor-depth-style low values darken it.
      const factor = 1 + (elev - 55) / 255 * 0.85;
      px[idx]     = Math.min(255, Math.max(0, px[idx]     * factor));
      px[idx + 1] = Math.min(255, Math.max(0, px[idx + 1] * factor));
      px[idx + 2] = Math.min(255, Math.max(0, px[idx + 2] * factor));
    }
  }
  offCtx.putImageData(imgData, minX, minY);
}

// Cheap, low-resolution terrain preview shown WHILE the globe is actively
// moving. Full-detail shading only ever runs once settled (~230ms — far
// too slow for every frame), but showing nothing at all while dragging
// made the terrain feel like it was disappearing every time the globe
// moved, which read as more jarring than the same live/settled split
// already used for country-boundary detail (that swap is subtle; flat
// color vs. visible relief is not). Downscales sharply — renders at
// roughly 1/14th linear resolution, so the per-pixel shading pass costs a
// few ms instead of hundreds — then scales the blurred result back up.
// Soft, but keeps a continuous sense of relief instead of flattening out.
// Reused every frame instead of allocating a new canvas each time — a
// fresh document.createElement('canvas') per frame was a measurable chunk
// of this overlay's cost (GC pressure from constant small-canvas churn).
const _liveTerrainCanvas = document.createElement('canvas');
const _liveTerrainCtx = _liveTerrainCanvas.getContext('2d');
let _liveTerrainRefreshDue = true;

function drawLiveTerrainOverlay(cx, cy, r) {
  if (!elevationPixels || showHeat) return;
  // Fixed target size, NOT r/zoom-scaled: R() scales with zoom, so a
  // "downscale by a constant ratio" box grows right along with it — at
  // zoom 4 that was already a 180x180 box (16x the pixel count of zoom 1),
  // eating most of the frame budget it was supposed to protect. A fixed
  // box bounds the per-frame cost of this pass regardless of zoom; it's a
  // blurred preview by design, so more blur relative to screen size at
  // high zoom is an acceptable tradeoff for staying cheap.
  //
  // (Tried re-rendering the low-res land mesh straight onto the small
  // canvas via a scale transform instead of copying pixels back from the
  // main canvas, hoping to dodge a GPU readback sync — measured worse:
  // re-projecting ~8k mesh points a second time cost as much as the
  // entire rest of the live frame. The drawImage-based downscale below
  // wins in practice, so keeping it.)
  const boxSize = 80;

  const needsResize = _liveTerrainCanvas.width !== boxSize || _liveTerrainCanvas.height !== boxSize;
  if (needsResize) {
    _liveTerrainCanvas.width = boxSize;
    _liveTerrainCanvas.height = boxSize;
  }

  // Refresh the downscaled source + shading only every other frame — one
  // frame (~16ms) of staleness is imperceptible on a preview that's
  // already blurred to 80x80px, and this halves the cost of the only two
  // non-trivial steps here (the cross-canvas readback and the per-pixel
  // shading loop) for the whole time the globe is being dragged. Still
  // blits the (possibly-reused) result below every frame, so there's no
  // visible skip/flicker — only the underlying detail updates less often.
  _liveTerrainRefreshDue = needsResize || !_liveTerrainRefreshDue;
  if (_liveTerrainRefreshDue) {
    if (!needsResize) _liveTerrainCtx.clearRect(0, 0, boxSize, boxSize);
    // canvas's own pixel buffer is DPR-scaled (device pixels), but cx/cy/r
    // are in the CSS-pixel space every other coordinate here uses —
    // convert when reading it back, since drawImage's source rect is
    // always in the source's native pixel space.
    const dpr = window.devicePixelRatio || 1;
    _liveTerrainCtx.drawImage(
      canvas,
      (cx - r) * dpr, (cy - r) * dpr, 2 * r * dpr, 2 * r * dpr,
      0, 0, boxSize, boxSize
    );
    applyTerrainShading(_liveTerrainCtx, boxSize / 2, boxSize / 2, boxSize / 2);
  }

  ctx.save();
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.clip();
  // The 80px source has to stretch up to 2r screen pixels — at typical
  // zoom that's a 5-20x upscale, and canvas's default 'low'-quality
  // resampling renders that as visible blocky patches rather than the
  // soft blur this preview is supposed to be. 'high' quality plus an
  // explicit blur (scaled to the upscale factor, so higher zoom — a
  // bigger stretch — gets proportionally more softening) fixes that.
  const upscale = (2 * r) / boxSize;
  ctx.imageSmoothingQuality = 'high';
  ctx.filter = `blur(${Math.min(10, Math.max(2, upscale * 0.35))}px)`;
  ctx.drawImage(_liveTerrainCanvas, cx - r, cy - r, 2 * r, 2 * r);
  ctx.filter = 'none';
  ctx.restore();
}

// Renders land fill + highlighted-country glow + borders for one frame,
// against whichever context it's given. Pulled out of drawGlobe() so it can
// target either the live main canvas (cheap low-res mesh, every frame) or
// an offscreen canvas (expensive high-res mesh, built once and cached —
// see the high-detail cache in drawGlobe()).
function renderLandAndBorders(targetCtx, features, borders, cx, cy, r) {
  renderLandFill(targetCtx, features, cx, cy, r);
  renderBorders(targetCtx, borders);
}

// Land fill + highlighted-country glow only (no borders) — split out so the
// high-detail cache can slot the expensive per-pixel terrain shading pass
// in between the fill and the borders, keeping border strokes crisp on top
// of the raster relief shading rather than getting shaded themselves.
function renderLandFill(targetCtx, features, cx, cy, r) {
  if (showHeat) {
    features.forEach(f => {
      targetCtx.fillStyle = '#1a4a2e';
      drawGeoFeature(f.geometry, true, targetCtx);
    });
    ACTORS.forEach(actor => {
      const p = project(actor.lat, actor.lon);
      if (p.z > 0) {
        // This is meant to be a *power* heatmap, not just an actor-location
        // marker — so the glow needs to actually scale with power. It
        // previously used a fixed radius/intensity for every actor
        // regardless of their military/economic/political/tech scores,
        // making a superpower and a minor actor look identical.
        const power = (
          (actor.military_power ?? 50) +
          (actor.economic_power ?? 50) +
          (actor.political_influence ?? 50) +
          (actor.technological_capability ?? 50)
        ) / 400; // 0–1
        const glowR = r * (0.14 + power * 0.34);
        const innerAlphaHex = Math.round(40 + power * 170).toString(16).padStart(2, '0');
        const grd = targetCtx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, glowR);
        grd.addColorStop(0, actor.color + innerAlphaHex);
        grd.addColorStop(1, 'transparent');
        targetCtx.fillStyle = grd;
        targetCtx.fillRect(0, 0, canvas.clientWidth, canvas.clientHeight);
      }
    });
  } else {
    // Normal land
    targetCtx.fillStyle = 'rgba(26,60,40,0.85)';
    features.forEach(f => drawGeoFeature(f.geometry, true, targetCtx));
  }

  // Highlighted country glow
  if (highlightedCountry) {
    targetCtx.save();
    targetCtx.fillStyle = 'rgba(0,212,255,0.18)';
    targetCtx.shadowColor = '#00d4ff';
    targetCtx.shadowBlur = 18;
    drawGeoFeature(highlightedCountry.feature.geometry, true, targetCtx);
    targetCtx.restore();
    targetCtx.save();
    targetCtx.strokeStyle = 'rgba(0,212,255,0.85)';
    targetCtx.lineWidth = 1.5;
    targetCtx.shadowColor = '#00d4ff';
    targetCtx.shadowBlur = 10;
    drawGeoFeature(highlightedCountry.feature.geometry, false, targetCtx);
    targetCtx.restore();
  }
}

function renderBorders(targetCtx, borders) {
  targetCtx.strokeStyle = 'rgba(255,255,255,0.18)';
  targetCtx.lineWidth = 0.5;
  drawGeoMesh(borders, targetCtx);
}

// High-detail (50m) land layer is too expensive to re-project and
// redraw every single frame (~80k points vs ~8k for the 110m mesh) — but
// once the globe is settled, rotX/rotY/zoom aren't changing, so the exact
// same bitmap would be produced every frame anyway. Render it once into an
// offscreen canvas, cache it keyed on everything that could change its
// appearance, and just blit the cached bitmap on subsequent frames until
// something in the key changes (rotation resumes, zoom changes, a country
// gets highlighted, heatmap mode toggles, or the canvas is resized).
let highDetailCache = null, highDetailCacheKey = null;

function getHighDetailLandBitmap(features, borders, cx, cy, r) {
  const key = [
    rotX, rotY, zoom, canvas.clientWidth, canvas.clientHeight,
    showHeat, highlightedCountry?.feature?.id ?? null,
    !!elevationPixels, // texture loads async — rebuild once it's ready so terrain doesn't stay missing from a bitmap cached before it arrived
  ].join('|');

  if (highDetailCache && highDetailCacheKey === key) return highDetailCache;

  const off = document.createElement('canvas');
  off.width  = canvas.clientWidth;
  off.height = canvas.clientHeight;
  const offCtx = off.getContext('2d');
  offCtx.save();
  offCtx.beginPath(); offCtx.arc(cx, cy, r, 0, Math.PI * 2); offCtx.clip();
  renderLandFill(offCtx, features, cx, cy, r);
  offCtx.restore();

  // Terrain relief shading — only in the cached high-detail tier (see
  // applyTerrainShading's comment); runs on the raw pixels after the land
  // fill but before borders, so border strokes stay crisp on top.
  if (!showHeat) applyTerrainShading(offCtx, cx, cy, r);

  offCtx.save();
  offCtx.beginPath(); offCtx.arc(cx, cy, r, 0, Math.PI * 2); offCtx.clip();
  renderBorders(offCtx, borders);
  offCtx.restore();

  highDetailCache = off;
  highDetailCacheKey = key;
  return off;
}

function drawGlobe() {
  // Flat map mode — skip 3D globe entirely
  if (flatMap) { drawFlatMap(); return; }

  // Only resize canvas if dimensions actually changed (avoid expensive layout recalc on every frame)
  const newWidth = canvas.clientWidth;
  const newHeight = canvas.clientHeight;
  if (newWidth !== lastCanvasWidth || newHeight !== lastCanvasHeight) {
    fitCanvasToDisplay(canvas, ctx);
    lastCanvasWidth = newWidth;
    lastCanvasHeight = newHeight;
  }

  // Guard against the canvas being measured before layout has settled
  // (clientWidth/clientHeight still 0 on the very first frame in some
  // load-timing races) — R() would go negative and createRadialGradient()
  // throws on a negative r0, which — since this runs synchronously inside
  // the very first loop() call, before requestAnimationFrame(loop) is
  // reached — would permanently stop the render loop from ever starting.
  // Skipping this one frame is enough: the next requestAnimationFrame tick
  // re-measures and self-heals once the canvas has a real size.
  if (canvas.clientWidth <= 0 || canvas.clientHeight <= 0) return;

  pulse = (pulse + 0.03) % (Math.PI * 2);

  const r  = R(), cx = CX(), cy = CY();

  // Space bg
  ctx.fillStyle = '#07090f';
  ctx.fillRect(0, 0, canvas.clientWidth, canvas.clientHeight);

  // Atmosphere halo
  const atm = ctx.createRadialGradient(cx, cy, r * 0.92, cx, cy, r * 1.18);
  atm.addColorStop(0, 'rgba(78,158,255,0.07)');
  atm.addColorStop(1, 'rgba(78,158,255,0)');
  ctx.fillStyle = atm;
  ctx.beginPath(); ctx.arc(cx, cy, r * 1.18, 0, Math.PI * 2); ctx.fill();

  // Ocean
  const oc = ctx.createRadialGradient(cx - r*.25, cy - r*.25, r*.05, cx, cy, r);
  oc.addColorStop(0, '#0f4068');
  oc.addColorStop(1, '#061d38');
  ctx.fillStyle = oc;
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();

  if (worldTopoLow) {
    // Settled + high-res ready → blit a cached bitmap (built once per
    // settle, see getHighDetailLandBitmap) instead of re-projecting ~80k
    // points every frame. Otherwise (still moving, or high-res not loaded
    // yet) render live against the light low-res mesh.
    if (topoFeaturesHigh && isSettled()) {
      const bitmap = getHighDetailLandBitmap(topoFeaturesHigh, topoMeshHigh, cx, cy, r);
      ctx.drawImage(bitmap, 0, 0);
    } else {
      const { features, mesh: borders } = getActiveTopo();
      ctx.save();
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.clip();
      renderLandAndBorders(ctx, features, borders, cx, cy, r);
      ctx.restore();
      drawLiveTerrainOverlay(cx, cy, r);
    }
  }

  // Trade routes
  if (showTrade) drawTradeRoutes();

  // Relationship arcs
  if (showArcs) {
    const arcColors = { conflict:'#ff3b3b', alliance:'#3dffaa', tension:'#ffd93d', economic:'#4e9eff', proxy:'#b94eff' };
    const actorMap = {};
    ACTORS.forEach(a => { actorMap[a.id] = a; });

    // Draw arcs first (under nodes) — thickness and opacity scale with strength
    RELATIONSHIPS.forEach(rel => {
      const a = actorMap[rel.a], b = actorMap[rel.b];
      if (!a || !b) return;
      const col = arcColors[rel.type] || '#888';
      // Only draw if at least one endpoint is on the visible hemisphere
      const pa = project(a.lat, a.lon), pb = project(b.lat, b.lon);
      if (pa.z > 0 || pb.z > 0) {
        const s = (rel.strength || 50) / 100;          // 0 → 1
        const lineW = 0.6 + s * 2.4;                   // 0.6px (weak) → 3px (strong)
        const alpha = 0.18 + s * 0.52;                  // 0.18 (weak) → 0.7 (strong)
        drawArc(a.lat, a.lon, b.lat, b.lon, col, lineW, alpha);
      }
    });

    // Draw actor nodes on top of arcs
    ACTORS.forEach(actor => {
      const p = project(actor.lat, actor.lon);
      if (p.z <= 0) { actor._screenX = null; actor._screenY = null; return; }
      // Store screen position for click detection
      actor._screenX = p.sx;
      actor._screenY = p.sy;
      const nr = 5 + zoom * 0.5;

      // Outer glow ring
      ctx.save();
      ctx.globalAlpha = 0.25;
      ctx.fillStyle = actor.color;
      ctx.shadowColor = actor.color;
      ctx.shadowBlur = 14;
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, nr + 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      // Solid node dot
      ctx.save();
      ctx.globalAlpha = 1;
      ctx.fillStyle = actor.color;
      ctx.shadowColor = actor.color;
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, nr, 0, Math.PI * 2);
      ctx.fill();

      // White center dot
      ctx.fillStyle = 'rgba(255,255,255,0.9)';
      ctx.shadowBlur = 0;
      ctx.beginPath();
      ctx.arc(p.sx, p.sy, nr * 0.4, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      // Actor label
      ctx.save();
      ctx.globalAlpha = 0.95;
      ctx.font = `bold ${Math.max(9, 10 + zoom * 0.3)}px "Segoe UI", sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillStyle = '#fff';
      ctx.shadowColor = 'rgba(0,0,0,0.8)';
      ctx.shadowBlur = 5;
      ctx.fillText(actor.id, p.sx, p.sy - nr - 5);
      ctx.restore();
    });
  }

  // Cascade rings — pulse count driven by number of cascade steps (1-3),
  // color shifts from yellow (low prob) → orange → red (high prob)
  if (showCasc && selected) {
    const pSel = project(selected.lat, selected.lon);
    if (pSel.z > 0) {
      const steps = selected.cascade?.steps || [];

      // Arcs from the crisis origin to each step's *actual* affected
      // actors — the backend's cascade analysis already resolves real
      // actor locations (step.actors → ACTORS lat/lon), but the rings
      // below are purely decorative concentric circles that pulse at the
      // origin regardless of which direction or how far the cascade
      // actually reaches. Draw the real geography instead of discarding it.
      if (steps.length > 0) {
        const actorById = {};
        ACTORS.forEach(a => { actorById[a.id] = a; });
        steps.forEach((step, i) => {
          const prob = step.probability ?? 0.3;
          const color = prob >= 0.65 ? '#ff3c3c' : prob >= 0.4 ? '#ffa532' : '#ffd23c';
          const breathe = 0.7 + Math.sin(pulse + i * 0.8) * 0.3;
          const alpha = (0.3 + prob * 0.45) * breathe;
          (step.actors || []).forEach(actorId => {
            const actor = actorById[actorId];
            if (!actor || actor.lat == null || actor.lon == null) return;
            drawArc(selected.lat, selected.lon, actor.lat, actor.lon, color, 1 + prob * 2, alpha);
          });
        });
      }

      const ringCount = steps.length > 0 ? Math.min(steps.length, 3) : 2;
      for (let ring = 1; ring <= ringCount; ring++) {
        const step = steps[ring - 1];
        const prob  = step?.probability ?? (0.6 - ring * 0.15);
        const color = prob >= 0.65 ? '255,60,60' : prob >= 0.4 ? '255,165,50' : '255,210,50';
        const phasedPulse = (pulse + ring * 1.1) % (Math.PI * 2);
        const rScale = (ring / (ringCount + 1)) * 0.55 + Math.sin(phasedPulse) * 0.04;
        const alpha  = (0.55 - ring * 0.12) * (0.7 + Math.sin(phasedPulse) * 0.3);
        ctx.strokeStyle = `rgba(${color},${alpha.toFixed(2)})`;
        ctx.lineWidth = Math.max(0.5, 2 - ring * 0.45);
        ctx.beginPath();
        ctx.arc(pSel.sx, pSel.sy, r * rScale, 0, Math.PI * 2);
        ctx.stroke();
      }
      // Core dot
      ctx.fillStyle = 'rgba(255,80,80,0.35)';
      ctx.beginPath();
      ctx.arc(pSel.sx, pSel.sy, 6 + Math.sin(pulse) * 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Globe rim
  ctx.strokeStyle = 'rgba(78,158,255,0.25)';
  ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();

  // Draw smooth heatmap overlay then pins on top
  drawHeatmapOverlay();
  drawPins();
}

function drawPins() {
  // ── Zoom-scaled display cap ──────────────────────────────────────────────────
  // At zoom=1 (default) show crisisDisplayLimit pins.
  // Zoom in (>1) → more pins; zoom out (<1) → fewer pins to reduce clutter.
  // Cap raised from 250 → 600: zoom goes up to 10x, and at that scale the
  // globe has far more screen real estate per pin, so the old cap was
  // throttling pin count well before zoom itself would have.
  const maxDisplayLimit = Math.min(
    Math.round(crisisDisplayLimit * Math.max(0.4, zoom)),   // zoom=1 → full limit
    600                                                       // hard cap
  );

  // ── Year filter ──────────────────────────────────────────────────────────────
  const pool_all = filterByDateRange(CRISES, currentYear);
  // Cumulative view: show all crises that started on or before end of currentYear
  let pool = CRISES.filter(c => {
    const d = new Date(c.date || c.date_start || c.date_updated);
    return !isNaN(d) && d.getFullYear() <= currentYear;
  });
  if (pool.length === 0) pool = pool_all.length > 0 ? pool_all : [];

  // ── Type / domain / location-confidence / severity filter ────────────────────
  pool = pool.filter(c =>
    activeTypes.has(c.type) &&
    (activeDomains.size === 0 || activeDomains.has(getDomainForType(c.type))) &&
    (c.location_confidence ?? 60) >= 60 &&
    (!countryFilter || c.country === countryFilter) &&
    (minSeverityFilter === 0 || (c.severity || 0) >= minSeverityFilter)
  );

  // ── Project every candidate, then keep only the front-facing hemisphere ───────
  // z > 0  →  facing the viewer  (visible)
  // z ≤ 0  →  behind the sphere  (hidden)
  //
  // THE KEY INSIGHT: we must project ALL candidates before filtering by z.
  // Slicing *before* projection discards candidates that might be front-facing,
  // so we can end up with fewer visible pins than maxDisplayLimit.
  //
  // After filtering z > 0 we sort ascending (back-edge → centre) so that the
  // painter's algorithm draws edge pins first and centre pins last (on top).
  // We then take the LAST maxDisplayLimit entries — i.e. the most-centred pins —
  // so the display limit always cuts from the invisible edge, never from the centre.

  let visible = pool
    .map(c => ({
      c,
      lat: c.lat || 0,
      lon: c.lon || 0,
      p: project(c.lat || 0, c.lon || 0),
      city: c.country
    }))
    .filter(({p}) => p.z > 0)            // hide pins behind the sphere
    .sort((a, b) => a.p.z - b.p.z)      // ascending z: edge (small z) → centre (large z)
    .slice(-maxDisplayLimit);            // keep the LAST N = highest-z = most centred pins
                                         // (if fewer than N are visible, all are kept)

  // Group by rounded lat/lon (0.1° buckets, ~11km) — catches events placed at the exact same coords
  const eventsByCoord = {};
  visible.forEach(item => {
    const key = `${(item.lat).toFixed(1)},${(item.lon).toFixed(1)}`;
    if (!eventsByCoord[key]) eventsByCoord[key] = [];
    eventsByCoord[key].push(item);
  });

  // Circular spread: arrange stacked pins in a ring around the real point
  const connectorLines = [];
  visible = visible.map(({c, p, city, lat, lon}) => {
    const key = `${lat.toFixed(1)},${lon.toFixed(1)}`;
    const group     = eventsByCoord[key];
    const idx       = group.findIndex(g => g.c.id === c.id);
    const total     = group.length;

    let sx = p.sx, sy = p.sy;

    if (total > 1) {
      // Ring radius: 20 px base + 4 px per extra pin, capped at 55 px
      const ringR  = Math.min(55, 20 + (total - 1) * 4);
      const angle  = (idx / total) * Math.PI * 2 - Math.PI / 2; // start at top
      sx = p.sx + Math.cos(angle) * ringR;
      sy = p.sy + Math.sin(angle) * ringR;
      connectorLines.push({ x1: p.sx, y1: p.sy, x2: sx, y2: sy, confidence: c.location_confidence ?? 75 });
    }

    return { c, p: {...p, sx, sy}, city, _alreadySpread: total > 1 };
  });

  // Draw connector lines first (behind pins)
  connectorLines.forEach(({x1, y1, x2, y2, confidence}) => {
    const alpha = 0.15 + (confidence / 100) * 0.3;  // Brighter = more confidence
    ctx.strokeStyle = `rgba(255,255,255,${alpha})`;
    ctx.lineWidth = 0.8;
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.setLineDash([]);
  });

  // ── CLUSTERING — merge nearby pins when zoomed out ───────────────────────────
  // Pins already pulled apart into a ring above (_alreadySpread — exact/
  // near-duplicate coordinates) are exempt: they were deliberately made
  // individually visible, and re-merging them into an anonymous "N" blob
  // here defeated that entirely.
  //
  // The cluster radius itself shrinks as you zoom in (instead of a fixed
  // 38px that only ever got fully switched off past a hard zoom>=1.4
  // cutoff), so decluttering fades out smoothly — the more zoomed in you
  // are, the more individual pins show individually, right up to zoom 10
  // where clustering is effectively off. That also directly means more
  // pins become visible the further in you zoom, not just a step change.
  const CLUSTER_DIST = 38 / Math.max(1, zoom);
  if (CLUSTER_DIST > 4) { // below this it's not doing anything meaningful
    const assigned = new Set();
    const clusters = [];
    visible.forEach((item, i) => {
      if (assigned.has(i)) return;
      if (item._alreadySpread) { assigned.add(i); clusters.push([item]); return; }
      const group = [item];
      assigned.add(i);
      visible.forEach((other, j) => {
        if (assigned.has(j) || other._alreadySpread) return;
        const d = Math.hypot(item.p.sx - other.p.sx, item.p.sy - other.p.sy);
        if (d < CLUSTER_DIST) { group.push(other); assigned.add(j); }
      });
      clusters.push(group);
    });

    clusters.forEach(group => {
      if (group.length === 1) return; // singles drawn normally below
      // Centroid
      const cx2 = group.reduce((s, g) => s + g.p.sx, 0) / group.length;
      const cy2 = group.reduce((s, g) => s + g.p.sy, 0) / group.length;
      const maxSev = Math.max(...group.map(g => g.c.severity || 0));
      const col = maxSev > 80 ? '#ff3b3b' : maxSev > 60 ? '#ff8833' : '#ffd93d';
      const cr = 14 + Math.min(group.length, 20) * 0.6;

      ctx.save();
      // Outer glow
      ctx.shadowColor = col; ctx.shadowBlur = 14;
      ctx.fillStyle = col + '33';
      ctx.beginPath(); ctx.arc(cx2, cy2, cr + 5, 0, Math.PI*2); ctx.fill();
      // Solid circle
      ctx.shadowBlur = 0;
      ctx.fillStyle = col + 'cc';
      ctx.strokeStyle = 'rgba(255,255,255,0.8)'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(cx2, cy2, cr, 0, Math.PI*2);
      ctx.fill(); ctx.stroke();
      // Count label
      ctx.fillStyle = '#fff';
      ctx.font = `bold ${cr > 18 ? 12 : 10}px "Segoe UI", sans-serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(group.length, cx2, cy2);
      ctx.restore();

      // Store centroid for click detection — clicking expands (zooms in)
      group.forEach(g => { g._cluster = { cx: cx2, cy: cy2, count: group.length }; });
    });

    // Remove clustered items from visible so we don't double-draw them
    visible = visible.filter(item => !item._cluster);
  }

  // Find the single closest pin to the cursor (only that one gets a tooltip)
  let closestDist = Infinity, closestPin = null;
  visible.forEach(({c, p}) => {
    const d = Math.hypot(mx - p.sx, my - p.sy);
    if (d < closestDist) { closestDist = d; closestPin = c; }
  });
  const hoverPin = closestDist < 18 ? closestPin : null;

  // Draw pins (with fade-in opacity for newly appeared crises)
  visible.forEach(({c, p}) => {
    const sx = p.sx, sy = p.sy;
    c._screenX = sx;
    c._screenY = sy;

    const fadeOpacity = pinOpacities[c.id] ?? 1;
    const isHovered = c === hoverPin;
    const isActive  = c.id === selected?.id;
    const col       = TYPE_META[c.type]?.color || '#fff';
    // Scale gently with zoom (matches the existing actor-node convention,
    // `nr = 5 + zoom * 0.5`) instead of a fixed screen size at every zoom
    // level: zoomed out, a fixed-size pin can visually blot out an entire
    // small country; zoomed in, the same fixed size under-represents how
    // precisely the crisis's point is actually known. Clamped so it never
    // gets tiny (min zoom) or oversized (max zoom).
    const baseR     = Math.max(5, Math.min(11, 7 + (zoom - 1) * 1.2));
    const r2        = isHovered || isActive ? baseR + 3 : baseR;

    ctx.save();
    ctx.globalAlpha = fadeOpacity;
    ctx.shadowColor = col;
    ctx.shadowBlur  = isActive ? 22 : isHovered ? 14 : 8;
    ctx.fillStyle   = col;
    ctx.beginPath(); ctx.arc(sx, sy, r2, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur  = 0;

    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.lineWidth   = 1.5;
    ctx.stroke();

    const pr = r2 + 4 + Math.sin(pulse) * 3;
    ctx.strokeStyle = col + '66';
    ctx.lineWidth   = 0.8;
    ctx.beginPath(); ctx.arc(sx, sy, pr, 0, Math.PI * 2); ctx.stroke();

    if (isHovered || isActive) {
      ctx.font = 'bold 10px Segoe UI';
      const tw = ctx.measureText(c.title).width + 14;
      const tx = Math.max(4, Math.min(sx - tw / 2, canvas.clientWidth - tw - 4));
      const ty = sy - r2 - 18;
      ctx.fillStyle = 'rgba(7,9,15,0.95)';
      ctx.fillRect(tx - 1, ty - 13, tw + 2, 17);
      ctx.strokeStyle = col + '88';
      ctx.lineWidth = 0.8;
      ctx.strokeRect(tx - 1, ty - 13, tw + 2, 17);
      ctx.fillStyle = col;
      ctx.textAlign = 'center';
      ctx.fillText(c.title, tx + tw / 2, ty - 1);
      ctx.textAlign = 'left';
    }
    ctx.restore();
  });

  // Draw fading-out pins (from the previous year, exiting the scene)
  fadingOutPins.forEach(({ c, opacity }) => {
    const p = project(c.lat || 0, c.lon || 0);
    if (p.z <= 0) return;
    const col = TYPE_META[c.type]?.color || '#fff';
    ctx.save();
    ctx.globalAlpha = opacity * 0.8;
    ctx.shadowColor = col;
    ctx.shadowBlur  = 6;
    ctx.fillStyle   = col;
    ctx.beginPath(); ctx.arc(p.sx, p.sy, 6, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  });
}

function drawHeatmapOverlay() {
  const cx = CX(), cy = CY(), r = R();

  // Fade heatmap as user zooms in so pins stay readable
  // zoom 0.5 → alpha 0.35, zoom 1.5 → alpha 0.2, zoom 2.5+ → alpha 0.04
  const baseAlpha = Math.max(0.04, 0.35 - (zoom - 0.5) * 0.155);

  // Gather visible, filtered crises — same location filter as drawPins()
  const filteredCrises = filterByDateRange(CRISES, currentYear).filter(c => {
    return activeTypes.has(c.type) &&
      (activeDomains.size === 0 || activeDomains.has(getDomainForType(c.type))) &&
      (c.location_confidence ?? 70) >= 75;
  });

  if (filteredCrises.length === 0) return;

  // Off-screen canvas, sized in CSS pixels (not the DPR-scaled backing-store
  // size) — it's a soft blurred glow layer, doesn't need retina crispness,
  // and this keeps its coordinate space matching project()'s CSS-pixel
  // output without needing its own devicePixelRatio transform.
  const off = document.createElement('canvas');
  off.width  = canvas.clientWidth;
  off.height = canvas.clientHeight;
  const offCtx = off.getContext('2d');

  // Blur radius scales with the globe radius so it looks consistent at any window size
  const blurPx = Math.round(r * 0.18);
  offCtx.filter = `blur(${blurPx}px)`;

  // Draw each crisis as a soft glowing dot on the off-screen canvas.
  // Severity drives colour: blue (low) → yellow (medium) → red (high).
  filteredCrises.forEach(crisis => {
    const p = project(crisis.lat, crisis.lon);
    if (p.z < 0.04) return;  // Back-facing, skip

    const severity  = (crisis.severity || 50) / 100;  // 0-1
    const hue       = Math.round(240 - severity * 240); // 240=blue, 120=green, 60=yellow, 0=red
    const dotRadius = r * 0.09 + severity * r * 0.06;  // larger dot for higher severity

    const grad = offCtx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, dotRadius);
    grad.addColorStop(0,   `hsla(${hue}, 100%, 65%, 0.9)`);
    grad.addColorStop(0.4, `hsla(${hue}, 100%, 55%, 0.5)`);
    grad.addColorStop(1,   `hsla(${hue}, 100%, 45%, 0)`);

    offCtx.fillStyle = grad;
    offCtx.beginPath();
    offCtx.arc(p.sx, p.sy, dotRadius, 0, Math.PI * 2);
    offCtx.fill();
  });

  // Clip the heatmap to the globe circle, then composite at chosen alpha
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.clip();
  ctx.globalAlpha = baseAlpha;
  ctx.drawImage(off, 0, 0);
  ctx.globalAlpha = 1;
  ctx.restore();
}

// ════════════════════════════════════════════════════════════
// NETWORK GRAPH
// ════════════════════════════════════════════════════════════

function drawNetwork() {
  const nc = document.getElementById('netCanvas');
  const nw = nc.clientWidth; nc.width = nw;
  const nh = parseInt(nc.getAttribute('height')) || 180; nc.height = nh;
  const nx2 = nc.getContext('2d');

  nx2.fillStyle = '#0a0d1a';
  nx2.fillRect(0, 0, nw, nh);

  const actorPos = {};
  const count = ACTORS.length;
  const cx = nw / 2, cy = nh / 2;
  const rx = nw * 0.4, ry = nh * 0.4;

  ACTORS.forEach((a, i) => {
    const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
    actorPos[a.id] = {
      x: cx + rx * Math.cos(angle),
      y: cy + ry * Math.sin(angle),
    };
  });

  const relColors = { conflict:'#ff3b3b', alliance:'#3dffaa', tension:'#ffd93d', economic:'#4e9eff', proxy:'#b94eff' };

  // Edges
  RELATIONSHIPS.forEach(rel => {
    const pa = actorPos[rel.a], pb = actorPos[rel.b];
    if (!pa || !pb) return;
    nx2.strokeStyle = (relColors[rel.type] || '#888') + '88';
    nx2.lineWidth = 1;
    nx2.beginPath();
    nx2.moveTo(pa.x, pa.y);
    // Bezier through center
    nx2.quadraticCurveTo(cx, cy, pb.x, pb.y);
    nx2.stroke();
  });

  // Nodes
  ACTORS.forEach(a => {
    const pos = actorPos[a.id];
    const isSelected = selected?.stakeholders?.includes(a.id);

    nx2.fillStyle = a.color + (isSelected ? 'ff' : '99');
    nx2.shadowColor = a.color;
    nx2.shadowBlur = isSelected ? 10 : 4;
    nx2.beginPath();
    nx2.arc(pos.x, pos.y, isSelected ? 7 : 5, 0, Math.PI * 2);
    nx2.fill();
    nx2.shadowBlur = 0;

    nx2.fillStyle = isSelected ? '#fff' : '#8899bb';
    nx2.font = `bold ${isSelected ? 9 : 8}px Segoe UI`;
    nx2.textAlign = 'center';
    nx2.fillText(a.name, pos.x, pos.y - 10);
  });
}

// ════════════════════════════════════════════════════════════
// UI: SELECTION & PANELS
// ════════════════════════════════════════════════════════════

function selectCrisis(crisis) {
  selected = crisis;
  document.getElementById('colRight').classList.add('open');
  updateAllPanels();
  updateEventsList();
  drawNetwork();
}

function updateAllPanels() {
  if (!selected) return;
  const c = selected;
  const tm = TYPE_META[c.type] || { color:'#888', name:'Unknown' };

  // ── Overview ──
  document.getElementById('emptyState').style.display = 'none';
  const ov = document.getElementById('overviewContent');
  ov.style.display = 'flex';

  const badge = document.getElementById('ov-type-badge');
  badge.textContent = tm.name;
  badge.style.background = tm.color + '33';
  badge.style.color = tm.color;
  badge.style.border = `1px solid ${tm.color}55`;

  const confEl = document.getElementById('ov-conf');
  const confColor = c.confidence > 80 ? '#3dffaa' : c.confidence > 60 ? '#ffd93d' : '#ff8833';
  confEl.textContent = `${c.confidence}% confidence`;
  confEl.style.background = confColor + '18';
  confEl.style.borderColor = confColor + '44';
  confEl.style.color = confColor;

  document.getElementById('ov-title').textContent = c.title;
  // Sync bookmark star
  const bBtn = document.getElementById('ov-bookmark-btn');
  if (bBtn) bBtn.classList.toggle('on', bookmarks.has(c.id));
  document.getElementById('ov-date').textContent  = c.date;

  const sevColor = c.severity > 80 ? '#ff3b3b' : c.severity > 60 ? '#ff8833' : '#ffd93d';
  document.getElementById('ov-sev-bar').style.width = c.severity + '%';
  document.getElementById('ov-sev-bar').style.background = sevColor;
  document.getElementById('ov-sev-num').textContent = c.severity;
  document.getElementById('ov-sev-num').style.color = sevColor;

  // Sparkline — drawn from escalation history if available, otherwise skip
  const sparkCanvas = document.getElementById('overviewSparkline');
  if (sparkCanvas && c.escalation?.history?.length > 1) {
    sparkCanvas.style.display = 'block';
    drawSparkline(sparkCanvas, c.escalation.history, sevColor);
  } else if (sparkCanvas) {
    sparkCanvas.style.display = 'none';
  }

  const stEl = document.getElementById('ov-stakeholders');
  const ACTOR_CLASS = { US:'us', CN:'cn', RU:'ru', EU:'eu' };
  stEl.innerHTML = c.stakeholders.map(s => {
    const cls = ACTOR_CLASS[s] || 'x';
    const actorName = ACTORS.find(a => a.id === s)?.name || s;
    return `<span class="tag ${cls}">${escapeHtml(actorName)}</span>`;
  }).join('');

  document.getElementById('ov-analysis').textContent = c.analysis;
  document.getElementById('ov-impact').textContent   = c.impact;

  // Display image from briefing if available, otherwise fetch from Wikipedia
  const imgWrap      = document.getElementById('ov-image-wrap');
  const imgEl        = document.getElementById('ov-image');
  const imgCaption   = document.getElementById('ov-image-caption');
  imgWrap.style.display = 'none';

  // Use image from briefing response if it exists, otherwise try Wikipedia fallback
  const displayImage = (img) => {
    if (img) {
      imgEl.src = img.src;
      imgEl.alt = img.caption;
      imgCaption.textContent = img.caption;
      imgWrap.style.display = 'block';
    }
  };

  if (c.briefing?.image) {
    displayImage(c.briefing.image);
  } else {
    fetchWikiImage(c).then(displayImage);
  }

  if (c.analogy) {
    const aEl = document.getElementById('ov-analogy');
    aEl.innerHTML = `<div class="analogy-match">${escapeHtml(c.analogy.match)} <span class="analogy-pct">${c.analogy.pct}% match</span></div><div class="analogy-desc">${escapeHtml(c.analogy.desc)}</div>`;
  }

  // ── Forecast ──
  document.getElementById('forecastEmpty').style.display = 'none';
  const fc = document.getElementById('forecastContent');
  fc.style.display = 'flex';
  fc.innerHTML = c.forecasts.map(f => `
    <div class="forecast-item">
      <div class="forecast-q">${escapeHtml(f.q)}</div>
      <div class="prob-bars">
        <div class="prob-row">
          <span class="prob-lbl">Unlikely</span>
          <div class="prob-track"><div class="prob-fill" style="width:${f.low}%;background:#3dffaa"></div></div>
          <span class="prob-pct" style="color:#3dffaa">${f.low}%</span>
        </div>
        <div class="prob-row">
          <span class="prob-lbl">Possible</span>
          <div class="prob-track"><div class="prob-fill" style="width:${f.mid}%;background:#ffd93d"></div></div>
          <span class="prob-pct" style="color:#ffd93d">${f.mid}%</span>
        </div>
        <div class="prob-row">
          <span class="prob-lbl">Likely</span>
          <div class="prob-track"><div class="prob-fill" style="width:${f.high}%;background:#ff3b3b"></div></div>
          <span class="prob-pct" style="color:#ff3b3b">${f.high}%</span>
        </div>
      </div>
    </div>
  `).join('');

  // ── Domains ──
  document.getElementById('domainsEmpty').style.display = 'none';
  const dc = document.getElementById('domainsContent');
  dc.style.display = 'flex';
  dc.innerHTML = Object.entries(c.domains).map(([key, val]) => {
    const d = DOMAINS[key];
    const domColor = val > 75 ? '#ff3b3b' : val > 50 ? '#ff8833' : '#ffd93d';
    return `
      <div class="domain-row">
        <span class="domain-icon">${d.icon}</span>
        <span class="domain-name">${d.name}</span>
        <div class="domain-bar-track"><div class="domain-bar-fill" style="width:${val}%;background:${domColor}"></div></div>
        <span class="domain-score" style="color:${domColor}">${val}</span>
      </div>
    `;
  }).join('');

  // ── Cascade ──
  const cc = document.getElementById('causalChain');
  cc.innerHTML = (c.causal || []).map((step, i) => `
    <div class="causal-step">
      <span class="causal-num">${i + 1}</span>
      <span class="causal-txt">${escapeHtml(step)}</span>
    </div>
  `).join('');
}

// ════════════════════════════════════════════════════════════
// UI: FILTERS
// ════════════════════════════════════════════════════════════

let activeDomains = new Set(Object.keys(DOMAINS));
let activeTypes   = new Set(Object.keys(TYPE_META));

function buildChips() {
  const dc = document.getElementById('domainChips');
  Object.entries(DOMAINS).forEach(([key, d]) => {
    const chip = document.createElement('div');
    chip.className = 'chip on';
    chip.style.color = d.color;
    chip.style.borderColor = d.color + '66';
    chip.style.background  = d.color + '18';
    chip.innerHTML = `${d.icon} ${d.name}`;
    chip.addEventListener('click', () => {
      activeDomains.has(key) ? activeDomains.delete(key) : activeDomains.add(key);
      chip.classList.toggle('on');
      updateEventsList();
    });
    dc.appendChild(chip);
  });

  const tc = document.getElementById('typeChips');
  Object.entries(TYPE_META).forEach(([key, t]) => {
    const chip = document.createElement('div');
    chip.className = 'chip on';
    chip.style.color = t.color;
    chip.style.borderColor = t.color + '66';
    chip.style.background  = t.color + '18';
    chip.textContent = t.name;
    chip.addEventListener('click', () => {
      activeTypes.has(key) ? activeTypes.delete(key) : activeTypes.add(key);
      chip.classList.toggle('on');
      updateEventsList();
    });
    tc.appendChild(chip);
  });
}

function updateEventsList() {
  const q    = document.getElementById('searchInput').value.toLowerCase();
  const list = document.getElementById('eventsList');
  list.innerHTML = '';

  // Get crises for the current year
  const crisisesInYear = filterByDateRange(CRISES, currentYear);

  const filtered = crisisesInYear
    .filter(c => {
      const typeMatch = activeTypes.has(c.type);
      const domainMatch = activeDomains.size === 0 || activeDomains.has(getDomainForType(c.type));
      const countryMatch = !countryFilter || c.country === countryFilter;
      return typeMatch && domainMatch && countryMatch;
    })
    .filter(c => c.title.toLowerCase().includes(q) || c.country.toLowerCase().includes(q));

  document.getElementById('crisisCount').textContent = `${filtered.length} active`;
  updateAlertBadge();

  filtered.forEach(crisis => {
    const el  = document.createElement('div');
    el.className = 'evt-item' + (crisis.id === selected?.id ? ' sel' : '');
    el.dataset.id = crisis.id;
    const tm = TYPE_META[crisis.type] || {};
    const sevCol = crisis.severity > 80 ? '#ff3b3b' : crisis.severity > 60 ? '#ff8833' : '#ffd93d';
    el.style.display = 'flex'; el.style.alignItems = 'flex-start'; el.style.gap = '6px';
    el.innerHTML = `
      <div style="flex:1;min-width:0;">
      <div class="evt-name">${escapeHtml(crisis.title)}</div>
      <div class="evt-sub">
        <span class="sev-badge" style="background:${sevCol}22;color:${sevCol};border:1px solid ${sevCol}55">${crisis.severity}</span>
        <span style="color:${tm.color || '#888'}">${tm.name || ''}</span>
        · ${escapeHtml(crisis.country)}
      </div>
      </div>
      <button class="bookmark-btn ${bookmarks.has(Number(crisis.id)) ? 'on' : ''}" data-bid="${crisis.id}" title="Bookmark">★</button>
    `;
    el.querySelector('.bookmark-btn').addEventListener('click', e => {
      e.stopPropagation();
      toggleBookmark(crisis);
      e.currentTarget.classList.toggle('on', bookmarks.has(crisis.id));
    });
    el.addEventListener('click', () => selectCrisis(crisis));
    list.appendChild(el);
  });
}

function buildAlerts() {
  const al = document.getElementById('alertsList');
  ALERTS.forEach(a => {
    const el = document.createElement('div');
    el.className = 'alert-strip';
    el.style.borderColor = a.color + '44';
    el.style.background  = a.color + '11';
    el.style.color       = a.color;
    el.textContent       = a.text;
    al.appendChild(el);
  });
}

function buildNewsFeed() {
  // Build news feed from events with low location confidence (diplomatic statements, announcements)
  const list = document.getElementById('newsfeedList');
  const empty = document.getElementById('newsfeedEmpty');
  list.innerHTML = '';

  // Filter events with low location_confidence (< 50) or no precise location
  const noLocationEvents = CRISES.filter(c => (c.location_confidence || 70) < 50);

  if (noLocationEvents.length === 0) {
    list.style.display = 'none';
    empty.style.display = 'flex';
    return;
  }

  empty.style.display = 'none';
  list.style.display = 'flex';

  // Sort by date, newest first
  noLocationEvents.sort((a, b) => new Date(b.date || b.date_start) - new Date(a.date || a.date_start));

  noLocationEvents.forEach(event => {
    const item = document.createElement('div');
    item.style.cssText = `
      padding: 6px; border: 1px solid rgba(255,255,255,.1);
      border-radius: 3px; background: rgba(255,255,255,.03);
      cursor: pointer; transition: background .2s;
      font-size: 9px;
    `;
    item.onmouseover = () => item.style.background = 'rgba(78,158,255,.1)';
    item.onmouseout = () => item.style.background = 'rgba(255,255,255,.03)';

    const title = document.createElement('div');
    title.style.cssText = 'font-weight: 600; color: #e0eaff; margin-bottom: 2px;';
    title.textContent = event.title;

    const meta = document.createElement('div');
    meta.style.color = 'var(--dim)';
    meta.style.fontSize = '8px';
    const date = new Date(event.date || event.date_start).toLocaleDateString();
    meta.textContent = `📌 ${event.country} • ${date}`;

    item.appendChild(title);
    item.appendChild(meta);
    item.onclick = () => selectCrisis(event);
    list.appendChild(item);
  });
}

// ════════════════════════════════════════════════════════════
// TABS
// ════════════════════════════════════════════════════════════

// Activate a div-based "tab" from either Enter or Space, matching native
// <button>/role="tab"> keyboard behavior (these are plain divs, so the
// browser doesn't do this for free).
function makeKeyboardActivatable(el) {
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      el.click();
    }
  });
}

// Right sidebar tabs
document.querySelectorAll('.tab[data-tab]').forEach(tab => {
  makeKeyboardActivatable(tab);
  tab.addEventListener('click', () => {
    const id = tab.dataset.tab;
    document.querySelectorAll('.tab[data-tab]').forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    tab.setAttribute('aria-selected', 'true');
    document.getElementById('tab-' + id).classList.add('active');

    // Update panels when switching tabs
    if (id === 'network') drawNetwork();
    if (id === 'reliability' && selected) updateReliabilityPanel(selected.reliability);
    if (id === 'escalation' && selected) updateEscalationPanel(selected.escalation);
    if (id === 'economic' && selected) updateEconomicPanel(selected.economic);
    if (id === 'briefing' && selected) updateBriefingPanel(selected.briefing);
  });
});

// Left sidebar tabs
document.querySelectorAll('.tab[data-left-tab]').forEach(tab => {
  makeKeyboardActivatable(tab);
  tab.addEventListener('click', () => {
    const id = tab.dataset.leftTab;
    document.querySelectorAll('.tab[data-left-tab]').forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
    document.querySelectorAll('.left-tab-content').forEach(t => {
      t.style.display = 'none';
      t.classList.remove('active');
    });
    tab.classList.add('active');
    tab.setAttribute('aria-selected', 'true');
    const content = document.querySelector(`.left-tab-content[data-left-tab="${id}"]`);
    if (content) {
      content.style.display = 'flex';
      content.classList.add('active');
    }
    if (id === 'watchlist') updateWatchlist();
  });
});

// ════════════════════════════════════════════════════════════
// GLOBE CONTROLS
// ════════════════════════════════════════════════════════════

// ── Rotation inertia ─────────────────────────────────────────────────────
// Drag/swipe velocity is tracked (as an exponential moving average, so one
// jittery pointer sample doesn't dominate) and, on release, keeps spinning
// the globe and decaying smoothly rather than stopping dead — the
// "fluid movement" a physically-spun globe has and a direct 1:1 mouse
// mapping doesn't.
let rotVelX = 0, rotVelY = 0;
const INERTIA_FRICTION = 0.94;   // per-frame velocity decay while gliding
const INERTIA_EPSILON  = 0.0002; // below this, treat velocity as fully stopped

// If the pointer stops moving but the button/touch is still held down, no
// further mousemove/touchmove events fire at all — so without this, the
// velocity EMA just sits frozen at whatever it was from the last actual
// movement, and releasing after a deliberate pause still launches the
// glide from that stale, possibly-large value ("drag, stop, let go, and
// it keeps spinning"). Zero it out once the pointer's been still for a
// bit while still dragging, so only a real flick right up to release
// carries any velocity into the glide.
const DRAG_STALL_MS = 60;
let lastDragMoveAt = 0;

function decayStaleDragVelocity() {
  if (!drag) return;
  if (performance.now() - lastDragMoveAt > DRAG_STALL_MS) {
    rotVelX = 0; rotVelY = 0;
  }
}

function applyInertia() {
  if (drag || flatMap) return; // user is actively driving rotation, or globe isn't shown
  if (Math.abs(rotVelX) < INERTIA_EPSILON && Math.abs(rotVelY) < INERTIA_EPSILON) return;
  rotY += rotVelY;
  rotX  = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, rotX + rotVelX));
  rotVelX *= INERTIA_FRICTION;
  rotVelY *= INERTIA_FRICTION;
  if (Math.abs(rotVelX) < INERTIA_EPSILON) rotVelX = 0;
  if (Math.abs(rotVelY) < INERTIA_EPSILON) rotVelY = 0;
  markMotion();
}

// Total raw pixel movement since the pointer went down — lets the 'click'
// handler tell a genuine click from a drag-release. Native 'click' fires
// on mouseup whenever mousedown also targeted this element, no matter how
// far the pointer moved in between, so without this, releasing a drag
// over a country/pin/actor selects it as if it had been clicked directly.
let dragDistance = 0;
const CLICK_DRAG_THRESHOLD = 5; // px — below this, treat it as a click even with tiny jitter

canvas.addEventListener('mousedown', e => {
  drag = true; rotVelX = 0; rotVelY = 0;
  dragDistance = 0;
  lastMX = e.clientX; lastMY = e.clientY;
  lastDragMoveAt = performance.now();
  markMotion();
});
document.addEventListener('mouseup',  () => drag = false);

// Touch events for globe rotation on mobile
canvas.addEventListener('touchstart', e => {
  if (e.touches.length === 1) {
    drag = true; rotVelX = 0; rotVelY = 0;
    dragDistance = 0;
    lastMX = e.touches[0].clientX;
    lastMY = e.touches[0].clientY;
    lastDragMoveAt = performance.now();
    markMotion();
  }
}, { passive: true });
canvas.addEventListener('touchend', () => { drag = false; }, { passive: true });
canvas.addEventListener('touchmove', e => {
  if (!drag || e.touches.length !== 1) return;
  e.preventDefault();
  // Divide by zoom: the globe's projected radius R() scales with zoom, so
  // a fixed radians-per-pixel constant makes the same finger movement spin
  // the globe much faster (in apparent surface speed) at high zoom, since
  // the same angular change sweeps a proportionally larger radius. Scaling
  // inversely with zoom keeps a pixel of drag feeling like the same amount
  // of globe at any zoom level.
  const dX = (e.touches[0].clientX - lastMX) * 0.007 / zoom;
  const dY = (e.touches[0].clientY - lastMY) * 0.004 / zoom;
  dragDistance += Math.hypot(e.touches[0].clientX - lastMX, e.touches[0].clientY - lastMY);
  rotY += dX;
  rotX  = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, rotX + dY));
  rotVelY = rotVelY * 0.7 + dX * 0.3;
  rotVelX = rotVelX * 0.7 + dY * 0.3;
  lastMX = e.touches[0].clientX;
  lastMY = e.touches[0].clientY;
  lastDragMoveAt = performance.now();
  markMotion();
}, { passive: false });
document.addEventListener('mousemove', e => {
  const rect = canvas.getBoundingClientRect();
  mx = e.clientX - rect.left;
  my = e.clientY - rect.top;
  if (drag) {
    // See the matching comment in touchmove: divide by zoom so drag speed
    // (in apparent globe-surface terms) stays consistent regardless of
    // zoom, instead of spinning faster the more zoomed in you are.
    const dX = (e.clientX - lastMX) * 0.007 / zoom;
    const dY = (e.clientY - lastMY) * 0.004 / zoom;
    dragDistance += Math.hypot(e.clientX - lastMX, e.clientY - lastMY);
    rotY += dX;
    rotX  = Math.max(-Math.PI/2, Math.min(Math.PI/2, rotX + dY));
    // Smoothed (EMA) velocity estimate — becomes the post-release glide speed.
    rotVelY = rotVelY * 0.7 + dX * 0.3;
    rotVelX = rotVelX * 0.7 + dY * 0.3;
    lastMX = e.clientX; lastMY = e.clientY;
    lastDragMoveAt = performance.now();
    markMotion();
  }
  canvas.style.cursor = drag ? 'grabbing' : 'grab';

  // Trade route hover tooltip
  if (showTrade && tradeRouteScreenPts.length > 0) {
    const tip = document.getElementById('tradeTooltip');
    let closest = null, closestD = Infinity;
    for (const pt of tradeRouteScreenPts) {
      const d = Math.hypot(mx - pt.sx, my - pt.sy);
      if (d < closestD) { closestD = d; closest = pt; }
    }
    if (closest && closestD < 40) {
      const route = TRADE_ROUTES[closest.idx];
      const riskColor = ROUTE_RISK_COLORS[closest.risk];
      const riskLabel = ROUTE_RISK_LABELS[closest.risk];
      // Find nearby threatening crises
      const [, lat1, lon1, lat2, lon2] = route;
      // Same great-circle sampling as routeRiskLevel() — see its comment
      // for why naive lat/lon-linear midpoints are wrong for these routes.
      const rv1 = latLonToVec(lat1, lon1), rv2 = latLonToVec(lat2, lon2);
      const routeSamples = [0, 0.5, 1].map(t => vecToLatLon(slerpVec(rv1, rv2, t)));
      const threats = CRISES
        .filter(c => routeSamples.some(([sl,so]) => geoDistKm(c.lat||0, c.lon||0, sl, so) < 1650))  // ~15° at the equator
        .sort((a, b) => b.severity - a.severity)
        .slice(0, 3);
      const threatHtml = threats.length
        ? threats.map(c => `<div style="color:${c.severity>80?'#ff3b3b':c.severity>60?'#ff8833':'#ffd93d'};margin-top:3px">⚠ ${escapeHtml(c.title)} (${escapeHtml(c.country)})</div>`).join('')
        : '<div style="color:var(--dim);margin-top:3px">No active threats nearby</div>';
      tip.innerHTML = `
        <div style="font-weight:700;color:#ffd93d;margin-bottom:4px">${closest.label}</div>
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
          <span style="color:${riskColor};font-weight:700">${riskLabel}</span>
          <span style="color:var(--dim)">·</span>
          <span style="color:var(--dim)">${TRADE_VOL_LABEL[closest.vol]}</span>
        </div>
        <div style="font-size:9px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin-top:4px">Nearby threats</div>
        ${threatHtml}
      `;
      // Position near cursor, keep within viewport
      const gx = e.clientX - rect.left, gy = e.clientY - rect.top;
      tip.style.left = Math.min(gx + 14, rect.width - 250) + 'px';
      tip.style.top  = Math.max(gy - 20, 4) + 'px';
      tip.style.display = 'block';
    } else {
      document.getElementById('tradeTooltip').style.display = 'none';
    }
  } else {
    document.getElementById('tradeTooltip').style.display = 'none';
  }
});
canvas.addEventListener('wheel', e => {
  e.preventDefault();
  markMotion();
  const rect = canvas.getBoundingClientRect();
  const cmx  = e.clientX - rect.left;
  const cmy  = e.clientY - rect.top;

  const oldZoom = zoom;
  const factor  = e.deltaY < 0 ? 1.1 : 1 / 1.1;
  zoom = Math.max(0.5, Math.min(10, zoom * factor));
  if (zoom === oldZoom) return;

  // Zoom toward cursor: work out the globe-space normalised coords of the
  // cursor under the OLD zoom, then nudge rotation so that same point stays
  // under the cursor after the zoom change.
  const cx = CX(), cy = CY();
  const oldR = Math.max(1, (Math.min(canvas.clientWidth, canvas.clientHeight) / 2 - 48) * oldZoom);
  const nx = (cmx - cx) / oldR;   // globe-space x  (-1 … 1)
  const ny = -(cmy - cy) / oldR;  // globe-space y  (-1 … 1)

  // Only adjust rotation when cursor is inside the globe disc
  if (nx * nx + ny * ny < 0.92) {
    // The point was at screen offset (nx*oldR, -ny*oldR) and will now be at
    // (nx*newR, -ny*newR).  Compensate with a rotation so it stays at cursor.
    const zf   = zoom / oldZoom;
    const dRotY = nx * (1 - 1 / zf) * 0.85;
    const dRotX = ny * (1 - 1 / zf) * 0.55;
    rotY -= dRotY;
    rotX  = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, rotX + dRotX));
  }
}, { passive: false });
// Flat map click handler
flatCanvas.addEventListener('click', e => {
  if (!flatMap) return;
  const rect = flatCanvas.getBoundingClientRect();
  const ex = e.clientX - rect.left, ey = e.clientY - rect.top;
  for (const crisis of CRISES) {
    if (!crisis._screenX) continue;
    if (Math.hypot(ex - crisis._screenX, ey - crisis._screenY) < 10) {
      selectCrisis(crisis); return;
    }
  }
});

canvas.addEventListener('click', e => {
  // Native 'click' fires on mouseup regardless of how far the pointer
  // moved since mousedown, so releasing a drag-to-rotate gesture would
  // otherwise select whatever pin/actor/country happens to be under the
  // cursor at the release point. Only treat it as a real click — and run
  // any of the hit-testing below — if the pointer barely moved.
  if (dragDistance > CLICK_DRAG_THRESHOLD) return;

  const rect = canvas.getBoundingClientRect();
  const emx = e.clientX - rect.left, emy = e.clientY - rect.top;

  // Use the stored screen positions from the last frame's drawPins()
  for (const crisis of CRISES) {
    if (!activeTypes.has(crisis.type)) continue;
    const p = project(crisis.lat, crisis.lon);
    if (p.z > 0.04) {
      // Check distance to the stored screen position (which includes offset)
      const sx = crisis._screenX !== undefined ? crisis._screenX : p.sx;
      const sy = crisis._screenY !== undefined ? crisis._screenY : p.sy;
      if (Math.hypot(emx - sx, emy - sy) < 14) {
        selectCrisis(crisis);
        return;
      }
    }
  }

  // Check actor node clicks (only when arcs are shown)
  if (showArcs) {
    for (const actor of ACTORS) {
      if (actor._screenX == null) continue;
      if (Math.hypot(emx - actor._screenX, emy - actor._screenY) < 16) {
        openActorRelPanel(actor);
        return;
      }
    }
  }

  // Country filter: find which country was clicked. Always hit-test against
  // the low-res features — plenty precise for "which country" and always
  // available regardless of the LOD swap's settle state.
  if (worldTopoLow && topoFeaturesLow) {
    let found = null;
    for (const f of topoFeaturesLow) {
      if (isPointInCountry(f, emx, emy)) { found = f; break; }
    }
    const tip = document.getElementById('countryTooltip');
    if (found) {
      const name = ISO_NAMES[parseInt(found.id)] || `Country #${found.id}`;
      if (highlightedCountry?.feature === found) {
        // Second click on same country → clear filter
        highlightedCountry = null;
        countryFilter = null;
        tip.style.display = 'none';
      } else {
        highlightedCountry = { name, feature: found };
        countryFilter = name;
        // Count crises in this country
        const cnt = CRISES.filter(c => c.country === name).length;
        tip.innerHTML = `🔍 <strong>${name}</strong> &nbsp;·&nbsp; ${cnt} event${cnt !== 1 ? 's' : ''} &nbsp;<span style="color:var(--dim);font-weight:400;font-size:9px">click again to clear</span>`;
        tip.style.display = 'block';
      }
    } else {
      // Click on ocean → clear filter
      highlightedCountry = null;
      countryFilter = null;
      tip.style.display = 'none';
    }
    updateEventsList();
    drawGlobe();
  }
});

document.getElementById('resetBtn').addEventListener('click', () => { rotX = 0.25; rotY = 0; zoom = 1; });
document.getElementById('arcBtn').addEventListener('click', function() {
  showArcs = !showArcs;
  this.classList.toggle('active', showArcs);
  document.getElementById('arcLegend').style.display = showArcs ? 'block' : 'none';
});
document.getElementById('heatBtn').addEventListener('click', function() {
  showHeat = !showHeat;
  this.classList.toggle('active', showHeat);
});
document.getElementById('cascBtn').addEventListener('click', function() {
  showCasc = !showCasc;
  this.classList.toggle('active', showCasc);
});
document.getElementById('tradeBtn').addEventListener('click', function() {
  showTrade = !showTrade;
  this.classList.toggle('active', showTrade);
});

// Flat map toggle
document.getElementById('flatBtn').addEventListener('click', function() {
  flatMap = !flatMap;
  this.classList.toggle('active', flatMap);
  canvas.style.display = flatMap ? 'none' : 'block';
  flatCanvas.classList.toggle('visible', flatMap);
  if (flatMap) {
    fZoom = 1; fPanX = 0; fPanY = 0; // reset view
    flatCanvas.style.cursor = 'grab';
    drawFlatMap();
  } else {
    flatCanvas.style.cursor = '';
  }
});

// Fullscreen toggle
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen();
  }
}
document.getElementById('fullBtn').addEventListener('click', toggleFullscreen);
document.addEventListener('fullscreenchange', () => {
  const btn = document.getElementById('fullBtn');
  if (btn) btn.classList.toggle('active', !!document.fullscreenElement);
  btn.title = document.fullscreenElement ? 'Exit Fullscreen [F]' : 'Fullscreen [F]';
});

// Alert badge — count critical crises and wire up click-to-filter
function updateAlertBadge() {
  const critical = CRISES.filter(c => (c.severity || 0) >= 80);
  const badge = document.getElementById('alertBadge');
  if (!badge) return;
  if (critical.length > 0) {
    badge.textContent = critical.length;
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }
}
document.getElementById('alertBadge').addEventListener('click', () => {
  minSeverityFilter = minSeverityFilter === 80 ? 0 : 80;
  const badge = document.getElementById('alertBadge');
  badge.style.background = minSeverityFilter === 80 ? '#fff' : '#ff3b3b';
  badge.style.color      = minSeverityFilter === 80 ? '#ff3b3b' : '#fff';
  badge.title = minSeverityFilter === 80 ? 'Showing critical only — click to clear' : 'Critical crises — click to filter';
  updateEventsList(); drawGlobe();
});

// Share — deep link
document.getElementById('shareBtn').addEventListener('click', () => {
  if (!selected) return;
  const url = new URL(window.location.href);
  url.searchParams.set('crisis', selected.id);
  navigator.clipboard.writeText(url.toString()).then(() => {
    const btn = document.getElementById('shareBtn');
    btn.textContent = '✓';
    btn.style.color = '#3dffaa';
    setTimeout(() => { btn.textContent = '🔗'; btn.style.color = 'var(--accent)'; }, 1800);
  });
});

// Toast notification
function showToast(html, duration = 4500) {
  const t = document.getElementById('toast');
  t.innerHTML = html + ' <button id="toast-dismiss" title="Dismiss">✕</button>';
  t.classList.add('visible');
  clearTimeout(t._tid);
  t._tid = setTimeout(() => t.classList.remove('visible'), duration);
  document.getElementById('toast-dismiss').addEventListener('click', () => {
    t.classList.remove('visible');
    clearTimeout(t._tid);
  });
}

// Deep link — auto-select crisis from URL on load
// If the crisis is in the current 30-day window, select it directly.
// If it's historical (outside window), fetch it from the backend and open as a
// "Shared Briefing" — so every share link works regardless of when the event occurred.
async function applyDeepLink() {
  const id = parseInt(new URLSearchParams(window.location.search).get('crisis'));
  if (!id) return;

  // Fast path: crisis is already in the current window
  let crisis = CRISES.find(c => c.id === id);
  if (crisis) {
    selectCrisis(crisis);
    if (crisis.lat != null && crisis.lon != null) flyToLatLon(crisis.lat, crisis.lon);
    showToast(`🔗 <strong>Shared Briefing</strong>&ensp;·&ensp;${escapeHtml(crisis.title)}`, 4500);
    return;
  }

  // Historical crisis — fetch it from the backend
  const raw = await GeoIntelAPI.getCrisisDetail(id);
  if (!raw) {
    showToast(`⚠️ Shared crisis not found`, 3500);
    return;
  }

  // Transform to frontend format (same mapping as loadRealData)
  crisis = {
    id: raw.id,
    type: raw.type,
    title: raw.title,
    country: raw.country,
    lat: raw.lat,
    lon: raw.lon,
    severity: raw.severity,
    confidence: raw.confidence,
    location_confidence: raw.location_confidence,
    date: raw.date || 'Historical',
    date_start: raw.date,
    analysis: raw.analysis || '',
    impact: raw.impact || '',
    stakeholders: Array.isArray(raw.stakeholders) ? raw.stakeholders : [],
    domains: raw.domains || { military:50, economic:50, political:50, environment:50, technology:50, information:50 },
    forecasts: [], cascade: [], causal: [], analogy: null,
    _shared: true,
  };

  selectCrisis(crisis);
  if (crisis.lat != null && crisis.lon != null) flyToLatLon(crisis.lat, crisis.lon);

  const yr = raw.date ? new Date(raw.date).getFullYear() : null;
  const yearLabel = yr && !isNaN(yr) ? `<span style="opacity:.55;font-size:11px">&ensp;${yr}</span>` : '';
  showToast(`🔗 <strong>Shared Briefing</strong>&ensp;·&ensp;${escapeHtml(crisis.title)}${yearLabel}`, 6000);
}

// Bookmarks
function toggleBookmark(crisis) {
  const id = Number(crisis.id);
  if (bookmarks.has(id)) {
    bookmarks.delete(id);
  } else {
    bookmarks.add(id);
  }
  localStorage.setItem('geointel_bookmarks', JSON.stringify([...bookmarks]));
  updateWatchlist();
  updateEventsList(); // refresh stars in crisis list
  // Sync star in overview panel if this is the selected crisis
  if (selected && Number(selected.id) === Number(crisis.id)) {
    const btn = document.getElementById('ov-bookmark-btn');
    if (btn) btn.classList.toggle('on', bookmarks.has(crisis.id));
  }
}

function updateWatchlist() {
  const list = document.getElementById('watchlistItems');
  const countEl = document.getElementById('watchlistCount');
  if (!list) return;
  list.innerHTML = '';
  const saved = CRISES.filter(c => bookmarks.has(Number(c.id)));
  if (countEl) countEl.textContent = `${saved.length} saved`;
  if (saved.length === 0) {
    list.innerHTML = '<div class="watchlist-empty"><div class="wi">★</div><div>Star crises to add them<br>to your watchlist</div></div>';
    return;
  }
  saved.forEach(crisis => {
    const tm = TYPE_META[crisis.type] || {};
    const sevCol = crisis.severity > 80 ? '#ff3b3b' : crisis.severity > 60 ? '#ff8833' : '#ffd93d';
    const el = document.createElement('div');
    el.className = 'evt-item' + (crisis.id === selected?.id ? ' sel' : '');
    el.style.cssText = 'display:flex;align-items:flex-start;gap:6px;';
    el.innerHTML = `
      <div style="flex:1;min-width:0;">
        <div class="evt-name">${escapeHtml(crisis.title)}</div>
        <div class="evt-sub">
          <span class="sev-badge" style="background:${sevCol}22;color:${sevCol};border:1px solid ${sevCol}55">${crisis.severity}</span>
          <span style="color:${tm.color||'#888'}">${tm.name||''}</span>
          · ${escapeHtml(crisis.country)}
        </div>
      </div>
      <button class="bookmark-btn on" data-bid="${crisis.id}" title="Remove">★</button>
    `;
    el.querySelector('.bookmark-btn').addEventListener('click', e => {
      e.stopPropagation(); toggleBookmark(crisis);
    });
    el.addEventListener('click', () => selectCrisis(crisis));
    list.appendChild(el);
  });
}

document.getElementById('clearWatchlist').addEventListener('click', () => {
  bookmarks.clear();
  localStorage.setItem('geointel_bookmarks', JSON.stringify([]));
  updateWatchlist();
  updateEventsList();
});

document.getElementById('ov-bookmark-btn').addEventListener('click', () => {
  if (selected) toggleBookmark(selected);
});

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  // Don't fire when typing in an input
  if (['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)) return;
  switch (e.key.toLowerCase()) {
    case 'f': toggleFullscreen(); break;
    case 'h': document.getElementById('heatBtn').click(); break;
    case 'r': document.getElementById('arcBtn').click(); break;
    case 'm': document.getElementById('flatBtn').click(); break;
    case '/':
      e.preventDefault();
      document.getElementById('searchInput').focus();
      break;
    case 'escape':
      document.getElementById('panelClose').click();
      document.getElementById('searchInput').blur();
      break;
  }
});

document.getElementById('simBtn').addEventListener('click', async function() {
  if (!selected) { this.textContent = '⚠️ Select a crisis first'; return; }

  cascadeActive = !cascadeActive;
  showCasc = cascadeActive;
  document.getElementById('cascBtn').classList.toggle('active', cascadeActive);
  this.classList.toggle('active', cascadeActive);

  const res = document.getElementById('cascadeResults');

  if (cascadeActive) {
    this.textContent = '⏳ Simulating…';
    this.disabled = true;
    res.style.display = 'flex';
    res.innerHTML = '<div style="padding:12px;color:var(--text3);font-size:12px;text-align:center">Running cascade analysis…</div>';

    try {
      // Use API_BASE from frontend-api.js (handles localhost vs production)
      const API_BASE = window.GEOINTEL_API_BASE ||
        (window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api');
      const response = await fetch(`${API_BASE}/crises/${selected.id}/cascade?depth=2&threshold=40`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const d = await response.json();
      selected.cascade = d;

      // ── Probability colour helper ─────────────────────
      const probColor = p => p >= 0.7 ? '#ff4d4d' : p >= 0.45 ? '#ffb347' : p >= 0.25 ? '#ffd93d' : '#3dffaa';
      const probBar   = p => `<div style="height:3px;border-radius:2px;background:rgba(255,255,255,0.08);margin-top:4px">
          <div style="height:3px;border-radius:2px;width:${(p*100).toFixed(0)}%;background:${probColor(p)};transition:width .6s ease"></div></div>`;

      if (d.steps && d.steps.length > 0) {
        const overallProb = d.total_cascade_probability;
        const summaryHtml = `
          <div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.15);border-radius:8px;padding:10px 12px;margin-bottom:10px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
              <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--text3)">Cascade Forecast</span>
              <span style="font-size:11px;font-weight:700;color:${probColor(overallProb)}">${(overallProb*100).toFixed(0)}% overall risk</span>
            </div>
            <div style="display:flex;gap:14px;font-size:11px;color:var(--text2)">
              <span>⚡ ${d.total_steps} propagation hop${d.total_steps !== 1 ? 's' : ''}</span>
              <span>⏱ ${d.estimated_timeline}</span>
            </div>
            ${probBar(overallProb)}
          </div>`;

        const stepsHtml = d.steps.map((step, i) => {
          const names = escapeHtml((step.affected_actor_names || step.actors || []).join(', '));
          const p = step.probability;
          const color = probColor(p);
          return `
            <div style="padding:9px 11px;background:rgba(255,255,255,0.025);border-left:2px solid ${color}40;border-radius:6px;animation:slideInUp .25s ${i*0.08}s both">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
                <span style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:${color};background:${color}18;padding:2px 6px;border-radius:3px">Hop ${step.hop}</span>
                <span style="font-size:11px;font-weight:600;color:var(--text)">${names}</span>
              </div>
              <div style="font-size:10.5px;color:var(--text2);line-height:1.4">${escapeHtml(step.mechanism)}</div>
              <div style="display:flex;align-items:center;gap:10px;margin-top:4px;font-size:10px;color:var(--text3)">
                <span style="color:${color};font-weight:600">${(p*100).toFixed(0)}% probability</span>
                <span>+${step.escalation_increase} severity</span>
              </div>
              ${probBar(p)}
            </div>`;
        }).join('');

        res.innerHTML = summaryHtml + stepsHtml;
      } else {
        res.innerHTML = `<div style="padding:14px 12px;text-align:center;color:var(--text3);font-size:12px">
          <div style="font-size:22px;margin-bottom:6px">🟢</div>
          No significant cascade escalation predicted for this crisis at current threshold.
        </div>`;
      }

      this.textContent = '⏹ Stop Simulation';
      this.disabled = false;
    } catch (error) {
      console.error('Cascade simulation error:', error);
      this.textContent = '⚡ Simulate Escalation';
      this.disabled = false;
      res.innerHTML = `<div style="padding:12px;color:#ff8888;font-size:11px">⚠️ ${escapeHtml(error.message)}</div>`;
      cascadeActive = false;
      document.getElementById('cascBtn').classList.remove('active');
    }
  } else {
    res.style.display = 'none';
    this.textContent = '⚡ Simulate Escalation';
  }
});

// Timeline
const timeSlider = document.getElementById('timeSlider');
const yearLabel  = document.getElementById('yearLabel');
timeSlider.addEventListener('input', () => {
  currentYear = 2020 + Math.round(parseInt(timeSlider.value) / 100 * 6);
  yearLabel.textContent = currentYear;

  const eventsInYear = filterByDateRange(CRISES, currentYear);
  const timeCount = document.querySelector('.timeline-count');
  if (timeCount) timeCount.textContent = `${eventsInYear.length} events`;

  updateTimelineActivity();
  updateEventsList();
  drawGlobe();
});

document.getElementById('playBtn').addEventListener('click', function() {
  playing = !playing;
  this.textContent = playing ? '⏸' : '▶';
  if (playing) animateTimeline();
});

const DOMAIN_GRAD_COLORS = {
  military:    '#ff3b3b',
  economic:    '#ffd93d',
  political:   '#4e9eff',
  environment: '#3dffaa',
  technology:  '#b94eff',
  cyber:       '#00e5ff',
  health:      '#f48fb1',
  information: '#ff8833',
  climate:     '#69f0ae',
  space:       '#ce93d8',
};

function buildDomainGradient(year) {
  const crises = filterByDateRange(CRISES, year);
  if (!crises.length) return 'rgba(0,212,255,0.2)';

  // Count by domain
  const domainCounts = {};
  crises.forEach(c => {
    const d = getDomainForType(c.type);
    domainCounts[d] = (domainCounts[d] || 0) + 1;
  });

  // Sort by count descending, keep top 4
  const sorted = Object.entries(domainCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);
  const total = sorted.reduce((s, [, n]) => s + n, 0);

  // Build gradient stops (bottom→top)
  let pos = 0;
  const stops = sorted.map(([domain, count]) => {
    const pct = Math.round((count / total) * 100);
    const color = DOMAIN_GRAD_COLORS[domain] || '#888';
    const stop = `${color}99 ${pos}% ${pos + pct}%`;
    pos += pct;
    return stop;
  });
  if (pos < 100) stops[stops.length - 1] = stops[stops.length - 1].replace(/\d+%$/, '100%');
  return `linear-gradient(to top, ${stops.join(', ')})`;
}

function updateTimelineActivity() {
  const years = [2020,2021,2022,2023,2024,2025,2026];
  const counts = years.map(y => filterByDateRange(CRISES, y).length);
  const maxCount = Math.max(...counts, 1);

  years.forEach((year, i) => {
    const bar   = document.getElementById(`tbar-${year}`);
    const delta = document.getElementById(`tdelta-${year}`);
    if (!bar) return;

    const pct = Math.max(8, Math.round((counts[i] / maxCount) * 100));
    bar.style.height     = pct + '%';
    bar.style.background = buildDomainGradient(year);
    bar.classList.toggle('active', year === currentYear);

    // Year-over-year delta
    if (delta) {
      if (i === 0) {
        delta.textContent = '';
        delta.className = 'ta-delta neu';
      } else {
        const diff = counts[i] - counts[i - 1];
        if (diff === 0) {
          delta.textContent = '━';
          delta.className = 'ta-delta neu';
        } else {
          delta.textContent = (diff > 0 ? '+' : '') + diff;
          delta.className = 'ta-delta ' + (diff > 0 ? 'pos' : 'neg');
        }
      }
    }

    // Hover tooltip: top crisis + domain breakdown
    const wrap = bar.closest('.ta-wrap');
    if (wrap) {
      wrap.onmouseenter = () => {
        const yearCrises = filterByDateRange(CRISES, year).sort((a, b) => b.severity - a.severity);
        const top = yearCrises[0];
        const domainCounts = {};
        yearCrises.forEach(c => {
          const d = getDomainForType(c.type);
          domainCounts[d] = (domainCounts[d] || 0) + 1;
        });
        const domainStr = Object.entries(domainCounts)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([d, n]) => `${d}: ${n}`)
          .join(' · ');
        const tipText = top
          ? `${year}: ${counts[i]} events\nTop: ${top.title} (sev ${top.severity})\n${domainStr}`
          : `${year}: no recorded events`;
        wrap.title = tipText;
      };
    }
  });
}

// Trigger fade-in/fade-out on year transition
function triggerPinTransition(prevYear, newYear) {
  const prevIds = new Set(filterByDateRange(CRISES, prevYear).map(c => c.id));
  const newCrises = filterByDateRange(CRISES, newYear);
  const newIds = new Set(newCrises.map(c => c.id));

  // New pins fade in
  newCrises.forEach(c => {
    if (!prevIds.has(c.id)) pinOpacities[c.id] = 0;
  });

  // Departing pins fade out (only if they have a valid projected position)
  CRISES.filter(c => prevIds.has(c.id) && !newIds.has(c.id)).forEach(c => {
    if (!fadingOutPins.find(p => p.c.id === c.id)) {
      fadingOutPins.push({ c, opacity: pinOpacities[c.id] ?? 1 });
    }
    delete pinOpacities[c.id];
  });
}

function advancePinOpacities() {
  // Advance fade-in opacities toward 1
  for (const id in pinOpacities) {
    pinOpacities[id] = Math.min(1, pinOpacities[id] + PIN_FADE_STEP);
    if (pinOpacities[id] >= 1) delete pinOpacities[id]; // fully visible — no longer needs tracking
  }
  // Advance fade-out opacities toward 0
  fadingOutPins = fadingOutPins
    .map(p => ({ ...p, opacity: p.opacity - PIN_FADE_STEP }))
    .filter(p => p.opacity > 0);
}

function animateTimeline() {
  if (!playing) return;
  // Step 1 slider unit per tick at 30ms — full sweep in ~3s, ~500ms per year
  let v = parseInt(timeSlider.value) + playDir;
  if (v >= 100) { v = 100; playDir = -1; }
  if (v <= 0)   { v = 0;   playDir =  1; }
  timeSlider.value = v;
  const newYear = 2020 + Math.round(v / 100 * 6);
  if (newYear !== currentYear) {
    triggerPinTransition(currentYear, newYear);
    currentYear = newYear;
    yearLabel.textContent = currentYear;
    const eventsInYear = filterByDateRange(CRISES, currentYear);
    const timeCount = document.querySelector('.timeline-count');
    if (timeCount) timeCount.textContent = `${eventsInYear.length} events`;
    updateTimelineActivity();
    updateEventsList();
  }
  advancePinOpacities();
  drawGlobe();
  setTimeout(animateTimeline, 30);
}

// Search — autocomplete dropdown handled by initSearch() IIFE further below

// Infinite scroll - load more crises when scrolling down
setTimeout(() => {
  const eventsList = document.getElementById('eventsList');
  if (eventsList) {
    eventsList.addEventListener('scroll', (e) => {
      // Check if user scrolled near bottom
      const scrollPos = eventsList.scrollTop + eventsList.clientHeight;
      const scrollHeight = eventsList.scrollHeight;
      const threshold = 50; // pixels from bottom

      if (scrollHeight - scrollPos < threshold && scrollHeight > 0) {
        // User scrolled near bottom - load more crises
        const oldLimit = crisisDisplayLimit;
        crisisDisplayLimit = Math.min(crisisDisplayLimit + 25, CRISES.length);
        updateEventsList();
        drawGlobe();
      }
    });
  }
}, 100);

// Sidebar toggle
const colLeft = document.getElementById('colLeft');
const sidebarToggle = document.getElementById('sidebarToggle');
sidebarToggle.addEventListener('click', () => {
  colLeft.classList.toggle('collapsed');
  sidebarToggle.textContent = colLeft.classList.contains('collapsed') ? '▶' : '◀';
});

// Right panel open/close
const colRight = document.getElementById('colRight');
document.getElementById('panelClose').addEventListener('click', () => {
  colRight.classList.remove('open');
});

// ════════════════════════════════════════════════════════════
// ANIMATION LOOP
// ════════════════════════════════════════════════════════════

function loop() {
  decayStaleDragVelocity();
  applyInertia();
  drawGlobe();
  requestAnimationFrame(loop);
}

// ════════════════════════════════════════════════════════════
// DATA FILTERING
// ════════════════════════════════════════════════════════════

function filterRecentEvents(crises, hoursOld = 72) {
  const cutoffTime = new Date(Date.now() - hoursOld * 60 * 60 * 1000);
  return crises.filter(c => {
    try {
      const crisisDate = new Date(c.date || c.date_start);
      return crisisDate > cutoffTime;
    } catch (e) {
      // If date parsing fails, include the event (assume it's recent)
      return true;
    }
  });
}

// ════════════════════════════════════════════════════════════
// DATA LOADING FROM BACKEND
// ════════════════════════════════════════════════════════════

async function loadRealData() {
  try {
    // Check if backend is available
    const healthCheck = await GeoIntelAPI.healthCheck();
    if (!healthCheck.status || healthCheck.status !== 'ok') {
      throw new Error('Backend health check failed');
    }

    // Clear any previously shown "backend unavailable" banner now that it's reachable again
    document.getElementById('backendUnavailableAlert')?.remove();

    // Parallel load: crises, actors, relationships fetch concurrently after health check
    const [crisisResult, actorResult, relResult] = await Promise.all([
      GeoIntelAPI.getCrises({ days: 365, min_severity: 0 }),
      GeoIntelAPI.getActors(),
      GeoIntelAPI.getRelationships(),
    ]);

    // Process crises
    if (crisisResult.error) {
      throw new Error(`Failed to load crises: ${crisisResult.error}`);
    }
    if (crisisResult.crises && Array.isArray(crisisResult.crises)) {
      let transformedCrises = crisisResult.crises.map(c => ({
        id: c.id,
        type: c.type,
        title: c.title,
        country: c.country,
        lat: c.lat,
        lon: c.lon,
        severity: c.severity,
        confidence: c.confidence,
        location_confidence: c.location_confidence,
        date: c.date || 'Recent',
        date_start: c.date,
        analysis: c.analysis || '',
        impact: c.impact || '',
        stakeholders: Array.isArray(c.stakeholders) ? c.stakeholders : [],
        domains: c.domains || { military: 50, economic: 50, political: 50, environment: 50, technology: 50, information: 50 },
        forecasts: [],
        cascade: [],
        causal: [],
        analogy: null,
      }));
      CRISES = filterRecentEvents(transformedCrises, 720);
      setTimeout(applyDeepLink, 50);
    }

    // Process actors
    if (!actorResult.error && actorResult.actors) {
      ACTORS = actorResult.actors.map(a => ({
        id: a.id,
        name: a.name,
        color: a.color,
        lat: a.lat,
        lon: a.lon,
        military_power: a.military || 50,
        economic_power: a.economic || 50,
        political_influence: a.political || 50,
        technological_capability: a.technology || 50,
        is_nuclear: a.is_nuclear || false,
      }));
    }

    // Process relationships — include strength & stability for arc styling
    if (!relResult.error && relResult.relationships) {
      RELATIONSHIPS = relResult.relationships.map(r => ({
        a: r.a,
        b: r.b,
        type: r.type,
        label: r.label || '',
        strength: r.strength || 50,
        stability: r.stability || 50,
      }));
    }

    return true;
  } catch (error) {
    console.error('Backend connection failed:', error.message);
    const isLocalDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    // Avoid stacking duplicate banners on repeated failures (e.g. hourly auto-refresh)
    let alertEl = document.getElementById('backendUnavailableAlert');
    if (!alertEl) {
      alertEl = document.createElement('div');
      alertEl.id = 'backendUnavailableAlert';
      alertEl.setAttribute('role', 'alert');
      alertEl.setAttribute('aria-live', 'assertive');
      alertEl.style.cssText = 'position:fixed;top:10px;right:10px;background:#ff3b3b33;border:1px solid #ff3b3b66;color:#ff8888;padding:10px 15px;border-radius:6px;z-index:1000;font-size:12px;max-width:300px;';
      document.body.appendChild(alertEl);
    }
    const message = isLocalDev
      ? `Run <code style="background:#000;padding:2px 5px;border-radius:3px;">python app.py</code> from the backend/ directory to enable real data.`
      : `Intelligence data could not be loaded. Please refresh the page or try again shortly.`;
    const title = isLocalDev ? '⚠️ Backend Unavailable' : '⚠️ Service Unavailable';
    alertEl.innerHTML = `
      <button onclick="this.parentElement.remove()" style="position:absolute;top:4px;right:6px;background:none;border:none;color:#ff8888;cursor:pointer;font-size:13px;line-height:1;padding:2px 4px;" aria-label="Dismiss">✕</button>
      <strong style="display:block;padding-right:14px;">${title}</strong>${message}`;
    return false;
  }
}

// ════════════════════════════════════════════════════════════
// WEBSOCKET REAL-TIME EVENTS
// ════════════════════════════════════════════════════════════

let socket = null;

function connectToEventStream() {
  try {
    // Connect to WebSocket event stream
    const WS_BASE = window.location.hostname === 'localhost' ? 'http://localhost:5000' : window.location.origin;
    socket = io(WS_BASE, {
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: 5
    });

    socket.on('connect', () => {
      socket.emit('subscribe', { watch_list: 'all' });
    });

    socket.on('new_crisis', (data) => {
      const crisis = data.crisis;
      showBreakingAlert(crisis);
      const idx = CRISES.findIndex(c => c.id === crisis.id);
      if (idx >= 0) CRISES[idx] = crisis;
      else CRISES.unshift(crisis);
      updateEventsList();
      drawGlobe();
    });

    socket.on('error', (err) => console.warn('Socket error:', err));
  } catch (e) {
    console.warn('WebSocket unavailable:', e);
  }
}

function showBreakingAlert(crisis) {
  const alert = document.getElementById('breakingAlert');
  document.getElementById('alertTitle').textContent = crisis.title;
  document.getElementById('alertLoc').textContent = crisis.country;
  alert.style.display = 'block';
  alert.classList.remove('dismissing');
  setTimeout(() => { alert.classList.add('dismissing'); setTimeout(() => { alert.style.display = 'none'; }, 300); }, 8000);
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator(), gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 800;
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.5);
  } catch (e) {}
}

async function loadReliabilityData(id) { try { const r = await fetch(`${(window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api')}/crises/${id}/reliability`); return r.ok ? await r.json() : null; } catch (e) { return null; } }
async function loadEscalationData(id) { try { const r = await fetch(`${(window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api')}/crises/${id}/escalation`); return r.ok ? await r.json() : null; } catch (e) { return null; } }

// ── Alert email subscriptions ─────────────────────────────────────────────────
async function submitAlertSubscription() {
  const name   = document.getElementById('alertSubName').value.trim();
  const email  = document.getElementById('alertSubEmail').value.trim();
  const region = document.getElementById('alertSubRegion').value.trim() ||
                 (window._selectedCrisis?.country) || 'all';
  const msg    = document.getElementById('alertSubMsg');

  if (!email || !email.includes('@')) {
    msg.textContent = '⚠️ Please enter a valid email.';
    msg.style.color = '#f59e0b';
    msg.style.display = 'block';
    return;
  }

  try {
    const res = await fetch((window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api') + '/alerts/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name || 'Subscriber', email, regions: [region] }),
    });
    const data = await res.json();
    if (res.ok) {
      msg.textContent = `✅ Subscribed! You'll receive alerts for: ${region}`;
      msg.style.color = '#22c55e';
      document.getElementById('alertSubEmail').value = '';
      document.getElementById('alertSubName').value = '';
    } else {
      msg.textContent = `⚠️ ${data.error || 'Subscription failed.'}`;
      msg.style.color = '#f59e0b';
    }
  } catch (e) {
    msg.textContent = '⚠️ Could not connect to server.';
    msg.style.color = '#f59e0b';
  }
  msg.style.display = 'block';
}

// Pre-fill region when a crisis is selected
function prefillAlertRegion(country) {
  const field = document.getElementById('alertSubRegion');
  if (field && country) field.value = country;
}
async function loadEconomicData(id) { try { const r = await fetch(`${(window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api')}/crises/${id}/economic`); return r.ok ? await r.json() : null; } catch (e) { return null; } }
async function loadBriefing(id) { try { const r = await fetch(`${(window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api')}/crises/${id}/briefing`); return r.ok ? await r.json() : null; } catch (e) { return null; } }

// Fallback: Fetch a representative image from Wikipedia if briefing didn't include one
async function fetchWikiImage(crisis) {
  const terms = [crisis.country, crisis.title.split(' ')[0]];
  for (const term of terms) {
    try {
      const url = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(term)}`;
      const r = await fetch(url, { headers: { 'Accept': 'application/json' }, signal: AbortSignal.timeout(3000) });
      if (!r.ok) continue;
      const data = await r.json();
      if (data.thumbnail?.source) {
        const src = data.thumbnail.source.replace(/\/\d+px-/, '/480px-');
        return { src, caption: data.description || data.title || term };
      }
    } catch (e) { /* try next term */ }
  }
  return null;
}

// Render markdown-style ## headings and bullet lists inside a div
function renderMarkdown(el, text) {
  // Escape first: `text` is AI-generated/backend briefing content, not trusted markup.
  const html = escapeHtml(text)
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^\*\s+(.+)$/gm, '<li>$1</li>')
    .replace(/^-\s+(.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/gs, match => `<ul>${match}</ul>`)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '\n');
  el.innerHTML = html;
}

// Shared helper: when a panel's data failed to load (as opposed to nothing
// being selected yet), swap the "empty" placeholder to a distinct message so
// the user isn't told to "select a crisis" when they already have one open.
function showPanelUnavailable(emptyEl, message) {
  if (!emptyEl) return;
  if (!emptyEl.dataset.defaultHtml) emptyEl.dataset.defaultHtml = emptyEl.innerHTML;
  emptyEl.innerHTML = `<div class="empty-icon">⚠️</div><div>${message}</div>`;
  emptyEl.style.display = 'flex';
}

function resetPanelEmpty(emptyEl) {
  if (!emptyEl) return;
  if (emptyEl.dataset.defaultHtml) emptyEl.innerHTML = emptyEl.dataset.defaultHtml;
}

function updateReliabilityPanel(rel) {
  const content = document.getElementById('reliabilityContent');
  const empty = document.getElementById('reliabilityEmpty');

  if (!rel) {
    if (content) content.style.display = 'none';
    if (selected) {
      showPanelUnavailable(empty, 'Source reliability data<br>could not be loaded');
    } else {
      resetPanelEmpty(empty);
      if (empty) empty.style.display = 'flex';
    }
    return;
  }
  resetPanelEmpty(empty);

  if (empty) empty.style.display = 'none';
  if (content) content.style.display = 'flex';

  const statusMap = {
    'verified': '🟢 Verified by 3+ sources',
    'corroborated': '🟡 Corroborated by 2+ sources',
    'reported': '🟠 Reported by 1 source',
    'unverified': '🔴 Unverified',
    'unknown': '❓ No source data yet'
  };

  const statusEl = document.getElementById('rel-status');
  if (statusEl) {
    statusEl.textContent = statusMap[rel.reliability] || rel.reliability;
    statusEl.className = `source-badge ${rel.reliability}`;
  }

  const scoreBar = document.getElementById('rel-score-bar');
  if (scoreBar) {
    scoreBar.style.width = (rel.score || 0) + '%';
    scoreBar.style.background = rel.score >= 80 ? '#3dffaa' : rel.score >= 60 ? '#ffd93d' : rel.score > 0 ? '#ff8833' : '#666';
  }

  const scoreNum = document.getElementById('rel-score-num');
  if (scoreNum) scoreNum.textContent = (rel.score || 0) + '/100';

  const sourcesEl = document.getElementById('rel-sources');
  if (sourcesEl) {
    if (rel.sources && rel.sources.length > 0) {
      sourcesEl.innerHTML = rel.sources.map(s => `<span class="source-badge ${rel.reliability}">${escapeHtml(s)}</span>`).join('');
    } else {
      sourcesEl.innerHTML = '<span style="color:#888;font-size:10px;font-style:italic;">Sources will appear as news articles are aggregated</span>';
    }
  }
}

function updateEscalationPanel(esc) {
  const content = document.getElementById('escalationContent');
  const empty = document.getElementById('escalationEmpty');

  if (!esc || !esc.trend) {
    if (content) content.style.display = 'none';
    if (selected) {
      showPanelUnavailable(empty, 'Escalation trajectory data<br>could not be loaded');
    } else {
      resetPanelEmpty(empty);
      if (empty) empty.style.display = 'flex';
    }
    return;
  }

  resetPanelEmpty(empty);
  if (empty) empty.style.display = 'none';
  if (content) content.style.display = 'flex';

  const trendMap = {
    'escalating': '📈 ESCALATING',
    'de-escalating': '📉 DE-ESCALATING',
    'stable': '➡️ STABLE',
    'new': '✨ NEW'
  };

  const trendEl = document.getElementById('esc-trend');
  if (trendEl) {
    trendEl.textContent = trendMap[esc.trend] || esc.trend;
    trendEl.className = 'trend-' + esc.trend.replace(' ', '-');
  }

  const warningEl = document.getElementById('esc-warning');
  if (warningEl) {
    if (esc.warning) {
      warningEl.style.display = 'block';
      warningEl.textContent = esc.warning;
    } else {
      warningEl.style.display = 'none';
    }
  }

  const changeColor = esc.severity_change > 0 ? '#ff3b3b' : esc.severity_change < 0 ? '#3dffaa' : '#ffd93d';
  const changeEl = document.getElementById('esc-change');
  if (changeEl) {
    changeEl.textContent = (esc.severity_change > 0 ? '+' : '') + (esc.severity_change || 0) + ' pts';
    changeEl.style.color = changeColor;
  }

  const velocityEl = document.getElementById('esc-velocity');
  if (velocityEl) {
    velocityEl.textContent = (esc.velocity > 0 ? '+' : '') + (esc.velocity || 0) + ' pts/day';
    velocityEl.style.color = esc.velocity > 0 ? '#ff3b3b' : esc.velocity < 0 ? '#3dffaa' : '#ffd93d';
  }

  if (esc.history && esc.history.length > 0) {
    const chartCanvas = document.getElementById('escalationChart');
    if (chartCanvas) drawEscalationChart(chartCanvas, esc.history);
  }
}

function rollingAvg(arr, window) {
  return arr.map((_, i) => {
    const start = Math.max(0, i - Math.floor(window / 2));
    const end   = Math.min(arr.length, start + window);
    const slice = arr.slice(start, end);
    return slice.reduce((s, v) => s + v, 0) / slice.length;
  });
}

function drawSparkline(canvas, history, color) {
  const w = canvas.clientWidth || 200;
  canvas.width = w;
  const h = canvas.height = 44;
  const c = canvas.getContext('2d');
  c.clearRect(0, 0, w, h);

  const PAD = { l: 28, r: 8, t: 6, b: 14 };
  const cw = w - PAD.l - PAD.r, ch = h - PAD.t - PAD.b;

  const sevs = history.map(p => p.severity);
  const avg  = rollingAvg(sevs, Math.max(3, Math.round(sevs.length / 4)));
  const lo   = Math.min(...sevs) - 2;
  const hi   = Math.max(...sevs) + 2;
  const range = hi - lo || 1;

  const sx = i => PAD.l + (i / (sevs.length - 1 || 1)) * cw;
  const sy = v => PAD.t + ch - ((v - lo) / range) * ch;

  // Y-axis labels (min / max)
  c.font = '8px Segoe UI';
  c.fillStyle = 'rgba(143,163,192,0.7)';
  c.textAlign = 'right';
  c.fillText(Math.round(hi), PAD.l - 3, PAD.t + 4);
  c.fillText(Math.round(lo), PAD.l - 3, PAD.t + ch + 1);

  // Raw data — faint background line
  c.beginPath();
  sevs.forEach((v, i) => i === 0 ? c.moveTo(sx(i), sy(v)) : c.lineTo(sx(i), sy(v)));
  c.strokeStyle = color + '30';
  c.lineWidth = 1;
  c.stroke();

  // Fill under rolling average
  const grad = c.createLinearGradient(0, PAD.t, 0, PAD.t + ch);
  grad.addColorStop(0, color + '40');
  grad.addColorStop(1, color + '00');
  c.beginPath();
  avg.forEach((v, i) => i === 0 ? c.moveTo(sx(i), sy(v)) : c.lineTo(sx(i), sy(v)));
  c.lineTo(sx(avg.length - 1), PAD.t + ch);
  c.lineTo(sx(0), PAD.t + ch);
  c.closePath();
  c.fillStyle = grad;
  c.fill();

  // Rolling average — main bright line
  c.beginPath();
  avg.forEach((v, i) => i === 0 ? c.moveTo(sx(i), sy(v)) : c.lineTo(sx(i), sy(v)));
  c.strokeStyle = color;
  c.lineWidth = 2;
  c.stroke();

  // Endpoint dot + current value label
  const last = avg.length - 1;
  c.beginPath();
  c.arc(sx(last), sy(avg[last]), 3, 0, Math.PI * 2);
  c.fillStyle = color;
  c.fill();

  // Trend arrow below chart
  const trend = avg[last] > avg[0] + 1 ? '▲' : avg[last] < avg[0] - 1 ? '▼' : '━';
  const trendColor = avg[last] > avg[0] + 1 ? '#ff3b3b' : avg[last] < avg[0] - 1 ? '#3dffaa' : '#ffd93d';
  c.font = 'bold 8px Segoe UI';
  c.fillStyle = trendColor;
  c.textAlign = 'left';
  c.fillText(`${trend} 30-day avg`, PAD.l, h - 2);
}

function drawEscalationChart(canvas, history) {
  if (!canvas || !history || history.length === 0) return;

  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;

  // Clear
  ctx.fillStyle = '#0a0d1a';
  ctx.fillRect(0, 0, w, h);

  // Draw background grid
  ctx.strokeStyle = 'rgba(78,158,255,0.1)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = (h / 4) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  // Draw line chart
  const severities = history.map(h => h.severity);
  const maxSev = Math.max(...severities, 100);
  const minSev = Math.min(...severities, 0);
  const range = maxSev - minSev || 1;

  ctx.strokeStyle = '#4e9eff';
  ctx.lineWidth = 2;
  ctx.beginPath();

  history.forEach((point, i) => {
    const x = (i / (history.length - 1 || 1)) * (w - 10) + 5;
    const y = h - 10 - ((point.severity - minSev) / range) * (h - 20);

    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Draw points
  ctx.fillStyle = '#4e9eff';
  history.forEach((point, i) => {
    const x = (i / (history.length - 1 || 1)) * (w - 10) + 5;
    const y = h - 10 - ((point.severity - minSev) / range) * (h - 20);
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
  });

  // Draw border
  ctx.strokeStyle = 'rgba(78,158,255,0.3)';
  ctx.lineWidth = 1;
  ctx.strokeRect(0, 0, w, h);
}

function updateEconomicPanel(eco) {
  const c = document.getElementById('economicContent'), e = document.getElementById('economicEmpty');
  if (!eco) {
    c.style.display='none';
    if (selected) {
      showPanelUnavailable(e, 'Economic impact data<br>could not be loaded');
    } else {
      resetPanelEmpty(e);
      e.style.display='flex';
    }
    return;
  }
  resetPanelEmpty(e);
  e.style.display='none'; c.style.display='flex';
  const col = eco.impact_severity==='severe'?'#ff3b3b':eco.impact_severity==='significant'?'#ff8833':eco.impact_severity==='moderate'?'#ffd93d':'#3dffaa';
  const se = document.getElementById('econ-severity');
  se.textContent = eco.impact_severity.toUpperCase();
  se.style.color = col;
  document.getElementById('econ-sectors').innerHTML = eco.estimated_impact.industry_sectors_affected.map(s=>`<span class="sector-tag">${escapeHtml(s)}</span>`).join('');
  const est = eco.estimated_impact;
  document.getElementById('econ-estimates').innerHTML = `<div>Trade: ~${est.trade_disruption_percent}%</div><div>Volatility: ~${est.market_volatility_percent}%</div>`;
}

function updateBriefingPanel(br) {
  const c = document.getElementById('briefingContent'), e = document.getElementById('briefingEmpty');
  const loadingEl = document.getElementById('briefing-loading');
  const textEl    = document.getElementById('briefing-text');
  const imgWrap   = document.getElementById('briefing-image-wrap');
  const imgEl     = document.getElementById('briefing-image');

  if (!br) {
    c.style.display = 'none';
    loadingEl.style.display = 'none'; textEl.style.display = 'none';
    imgWrap.style.display = 'none';
    if (selected) {
      showPanelUnavailable(e, 'AI briefing unavailable for this crisis<br>(check ANTHROPIC_API_KEY on the backend, or try again shortly)');
    } else {
      resetPanelEmpty(e);
      e.style.display = 'flex';
    }
    return;
  }
  resetPanelEmpty(e);
  e.style.display = 'none'; c.style.display = 'flex';
  loadingEl.style.display = 'none'; textEl.style.display = 'block';

  // Display image from briefing response if available
  if (br.image) {
    imgEl.src = br.image.src;
    imgEl.alt = br.image.caption;
    imgWrap.style.display = 'block';
  } else {
    imgWrap.style.display = 'none';
  }

  // Render markdown-formatted briefing text
  renderMarkdown(textEl, br.briefing);
}

// Enhanced selectCrisis with all new data
const originalSelectCrisis = selectCrisis;
selectCrisis = async function(crisis) {
  selected = crisis;
  window._selectedCrisis = crisis; // For alert subscription pre-fill
  prefillAlertRegion(crisis.country);
  document.getElementById('colRight').classList.add('open');

  if (!crisis.forecasts || crisis.forecasts.length === 0) {
    try {
      const fr = await GeoIntelAPI.getForecasts(crisis.id);
      if (!fr.error && fr.forecasts) {
        crisis.forecasts = fr.forecasts.map(f => ({ q:f.q, low:f.low, mid:f.mid, high:f.high }));
      }
    } catch (e) {}
  }

  if (!crisis.news) {
    try {
      const nr = await GeoIntelAPI.getNews({ crisis_id: crisis.id, days: 30, limit: 5 });
      if (!nr.error && nr.articles) { crisis.news = nr.articles; }
    } catch (e) {}
  }

  if (!crisis.reliability) { crisis.reliability = await loadReliabilityData(crisis.id); }
  if (!crisis.escalation) { crisis.escalation = await loadEscalationData(crisis.id); }
  if (!crisis.economic) { crisis.economic = await loadEconomicData(crisis.id); }
  if (!crisis.briefing) {
    document.getElementById('briefing-loading').style.display = 'block';
    crisis.briefing = await loadBriefing(crisis.id);
  }

  updateAllPanels();
  updateReliabilityPanel(crisis.reliability);
  updateEscalationPanel(crisis.escalation);
  updateEconomicPanel(crisis.economic);
  updateBriefingPanel(crisis.briefing);
  updateEventsList();
  drawNetwork();
};

// ════════════════════════════════════════════════════════════
// INIT
// ════════════════════════════════════════════════════════════

async function initApp() {
  buildChips();
  buildAlerts();

  // Connect to real-time event stream
  connectToEventStream();

  // Load data from backend, with graceful fallback
  const backendAvailable = await loadRealData();

  // If no backend data loaded, ensure we have empty arrays rather than undefined
  if (!CRISES || CRISES.length === 0) {
    CRISES = [];
    ACTORS = [];
    RELATIONSHIPS = [];
  }

  updateEventsList();
  buildNewsFeed();
  drawNetwork();
  updateTimelineActivity();
  updateAlertBadge();
  updateWatchlist();

  // Low-res loads first and is what the globe renders with immediately —
  // small/fast, and it's also the mesh used while actively
  // dragging/zooming (see getActiveTopo()). The high-res file is ~7x
  // larger; it loads independently and, once parsed, has its
  // feature/mesh conversion (expensive at ~80k points) done via
  // requestIdleCallback so it doesn't compete with initial page
  // interactivity. It only ever gets *used* once the globe has been still
  // for SETTLE_DELAY_MS, so there's no rush for it to be ready.
  fetch('countries-110m.json')
    .then(r => r.json())
    .then(data => {
      worldTopoLow = data;
      // Build the low-res feature/mesh cache eagerly rather than lazily on
      // first draw — country-click hit-testing needs topoFeaturesLow and
      // shouldn't depend on the globe having rendered a live (non-cached)
      // frame first, which won't happen at all if the high-detail cache is
      // already warm by the time the first frame runs.
      getActiveTopo();
    })
    .catch(err => console.error('Map data error (low-res):', err));

  fetch('countries-50m.json')
    .then(r => r.json())
    .then(data => {
      worldTopoHigh = data;
      const buildHighResCache = () => {
        topoFeaturesHigh = topojson.feature(worldTopoHigh, worldTopoHigh.objects.countries).features;
        topoMeshHigh     = topojson.mesh(worldTopoHigh, worldTopoHigh.objects.countries, (a, b) => a !== b);
      };
      window.requestIdleCallback ? window.requestIdleCallback(buildHighResCache) : setTimeout(buildHighResCache, 0);
    })
    .catch(err => console.error('Map data error (high-res):', err));
}

// Auto-refresh data every hour
setInterval(async () => {
  await loadRealData();
  updateEventsList();
  buildNewsFeed();
  drawNetwork();
}, 3600000); // 1 hour in milliseconds

// Admin users who bypass subscription check
const ADMIN_EMAILS = ['collins.nick999@gmail.com'];

// Auth gate: check Supabase session + subscription (unless admin), then launch app
async function authThenInit() {
  const SUPABASE_URL = 'https://kmjpucafsjxottrparyg.supabase.co';
  const SUPABASE_KEY = 'sb_publishable_GImhVRL2C1xn3EQqejFyBA_K1TOkBTx';
  const REDIRECT_URL = 'https://asix.live/projects/geointel';
  const PROJECT_SLUG = 'geointel';

  const cookieStorage = {
    getItem(key) {
      const name = key + '=';
      for (let c of document.cookie.split(';')) {
        c = c.trim();
        if (c.startsWith(name)) return decodeURIComponent(c.slice(name.length));
      }
      return null;
    },
    setItem(key, value) {
      const maxAge = 60 * 60 * 24 * 365;
      const domain = window.location.hostname.includes('localhost') ? '' : '; domain=.asix.live';
      document.cookie = `${key}=${encodeURIComponent(value)}; max-age=${maxAge}; path=/${domain}; samesite=Lax`;
    },
    removeItem(key) {
      document.cookie = `${key}=; max-age=0; path=/`;
    }
  };

  const sb = supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, storage: cookieStorage }
  });

  // Read hash tokens
  const hash = window.location.hash;
  if (hash) {
    const params = new URLSearchParams(hash.slice(1));
    const access_token = params.get('access_token');
    const refresh_token = params.get('refresh_token');
    if (access_token && refresh_token) {
      await sb.auth.setSession({ access_token, refresh_token });
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }

  // LOCALHOST BYPASS: Skip authentication for local development
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    document.getElementById('auth-gate').style.display = 'none';
    await initApp();
    loop();
    return;
  }

  const { data: { session } } = await sb.auth.getSession();
  if (!session) { window.location.href = REDIRECT_URL; return; }

  // Admin bypass: skip subscription check for admins
  if (!ADMIN_EMAILS.includes(session.user.email)) {
    const { data: sub } = await sb
      .from('subscriptions')
      .select('status, projects!inner(slug)')
      .eq('user_id', session.user.id)
      .eq('projects.slug', PROJECT_SLUG)
      .eq('status', 'active')
      .maybeSingle();

    if (!sub) { window.location.href = REDIRECT_URL; return; }
  }

  document.getElementById('auth-gate').style.display = 'none';
  await initApp();
  loop();
}

authThenInit().catch(err => {
  console.error('Auth error:', err);
  document.getElementById('auth-gate').style.display = 'none';
  initApp().then(loop).catch(() => loop());
});

// ════════════════════════════════════════════════════════════
// RELATIONSHIP PANEL  (actor node click → explain relationships)
// ════════════════════════════════════════════════════════════

const ARC_COLORS = { conflict:'#ff3b3b', alliance:'#3dffaa', tension:'#ffd93d', economic:'#4e9eff', proxy:'#b94eff' };

// Simple markdown → HTML for AI analysis output
function renderMd(text) {
  // Escape first: `text` is AI-generated analysis, not trusted markup.
  return escapeHtml(text)
    .replace(/^## (.+)$/gm, '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--accent);margin:12px 0 4px;">$1</div>')
    .replace(/^- (.+)$/gm, '<div style="display:flex;gap:6px;margin:3px 0;"><span style="color:var(--accent);flex-shrink:0;">•</span><span>$1</span></div>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '<br>')
    .replace(/\n/g, ' ');
}

function openActorRelPanel(actor) {
  const panel  = document.getElementById('relPanel');
  const title  = document.getElementById('relPanelTitle');
  const list   = document.getElementById('relPanelList');
  const anaDiv = document.getElementById('relPanelAnalysis');

  title.textContent = `${actor.name || actor.id} — Relationships`;
  list.innerHTML = '';
  anaDiv.style.display = 'none';

  // Find all relationships for this actor
  const rels = RELATIONSHIPS.filter(r => r.a === actor.id || r.b === actor.id);
  const actorMap = {};
  ACTORS.forEach(a => { actorMap[a.id] = a; });

  if (rels.length === 0) {
    list.innerHTML = '<div style="color:var(--dim);font-size:10px;">No tracked relationships found.</div>';
  } else {
    rels.forEach(rel => {
      const otherId   = rel.a === actor.id ? rel.b : rel.a;
      const otherName = actorMap[otherId]?.name || otherId;
      const col       = ARC_COLORS[rel.type] || '#888';
      const row = document.createElement('div');
      row.style.cssText = `display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;cursor:pointer;background:rgba(255,255,255,.02);border:1px solid transparent;transition:all .2s;`;
      row.innerHTML = `
        <span style="width:10px;height:10px;border-radius:50%;background:${col};box-shadow:0 0 8px ${col}88;flex-shrink:0;"></span>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:700;color:#e8f4ff;font-size:11px;">${escapeHtml(otherName)}</div>
          <div style="font-size:10px;color:${col};margin-top:1px;">${escapeHtml(rel.type.charAt(0).toUpperCase()+rel.type.slice(1))} ${rel.label ? '· '+escapeHtml(rel.label) : ''}</div>
        </div>
        <span style="font-size:9px;color:var(--dim);">Analyze →</span>
      `;
      row.addEventListener('mouseover', () => { row.style.background='rgba(0,212,255,.07)'; row.style.borderColor='rgba(0,212,255,.2)'; });
      row.addEventListener('mouseout',  () => { row.style.background='rgba(255,255,255,.02)'; row.style.borderColor='transparent'; });
      // Pass actor IDs so backend can match the DB, with display names as fallback
      row.addEventListener('click', () => analyzeRelPair(actor.id, otherId, rel));
      list.appendChild(row);
    });
  }

  panel.style.display = 'block';
}

function closeRelPanel() {
  document.getElementById('relPanel').style.display = 'none';
}

async function analyzeRelPair(nameA, nameB, relHint) {
  const anaDiv   = document.getElementById('relPanelAnalysis');
  const anaHdr   = document.getElementById('relPanelAnalysisHeader');
  const anaText  = document.getElementById('relPanelAnalysisText');

  // Resolve display names from ACTORS if we have IDs
  const actorMap = {};
  ACTORS.forEach(a => { actorMap[a.id] = a; });
  const displayA = actorMap[nameA]?.name || nameA;
  const displayB = actorMap[nameB]?.name || nameB;
  anaHdr.textContent  = `${displayA}  ↔  ${displayB}`;
  anaText.innerHTML   = '<span style="color:var(--dim);">⟳ Generating analysis…</span>';
  anaDiv.style.display = 'block';
  anaDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    const res  = await fetch((window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api') + '/relationships/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ country_a: nameA, country_b: nameB })
    });
    const data = await res.json();
    if (data.error) {
      anaText.textContent = `Error: ${data.error}`;
    } else {
      anaText.innerHTML = renderMd(data.analysis || '');
    }
  } catch (e) {
    anaText.textContent = 'Could not reach backend. Is the server running?';
  }
}

// ════════════════════════════════════════════════════════════
// RELATIONSHIP LOOKUP (left sidebar tab)
// ════════════════════════════════════════════════════════════

async function runRelationshipLookup() {
  const nameA  = (document.getElementById('lookupA').value || '').trim();
  const nameB  = (document.getElementById('lookupB').value || '').trim();
  const result = document.getElementById('lookupResult');
  const btn    = document.getElementById('lookupBtn');

  if (!nameA || !nameB) {
    result.style.display = 'flex';
    result.innerHTML = '<div style="color:var(--red);font-size:10px;">Please enter both country names.</div>';
    return;
  }

  btn.textContent = '⟳ Analyzing…';
  btn.disabled = true;
  result.style.display = 'flex';
  result.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;color:var(--dim);font-size:11px;">
      <span style="animation:spinner .8s linear infinite;display:inline-block;">⟳</span>
      Querying intelligence database…
    </div>`;

  try {
    const res  = await fetch((window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api') + '/relationships/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ country_a: nameA, country_b: nameB })
    });
    const data = await res.json();

    if (data.error) {
      result.innerHTML = `<div style="color:var(--red);font-size:10px;">Error: ${escapeHtml(data.error)}</div>`;
      return;
    }

    const col   = ARC_COLORS[data.type] || '#8fa3c0';
    const badge = data.type
      ? `<span style="background:${col}22;color:${col};border:1px solid ${col}55;border-radius:6px;padding:3px 9px;font-size:10px;font-weight:700;">${escapeHtml(data.type.toUpperCase())}</span>`
      : '';
    const strBar = data.strength != null
      ? `<div style="margin-top:6px;">
           <div style="font-size:9px;color:var(--dim);margin-bottom:3px;">STRENGTH</div>
           <div style="background:rgba(255,255,255,.06);border-radius:4px;height:5px;width:100%;">
             <div style="background:${col};height:5px;border-radius:4px;width:${data.strength}%;box-shadow:0 0 6px ${col}88;"></div>
           </div>
         </div>` : '';

    result.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;">
        <div style="font-size:12px;font-weight:700;color:#e8f4ff;">${escapeHtml(nameA)} ↔ ${escapeHtml(nameB)}</div>
        ${badge}
      </div>
      ${data.label ? `<div style="font-size:10px;color:var(--text2);">${escapeHtml(data.label)}</div>` : ''}
      ${strBar}
      ${!data.known ? '<div style="font-size:9px;color:var(--yellow);padding:5px 8px;background:rgba(255,208,26,.06);border-radius:6px;">⚠ No tracked relationship — analysis based on open-source knowledge</div>' : ''}
      <div style="padding-top:8px;border-top:1px solid var(--border);">
        <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--dim);margin-bottom:6px;">AI Analysis</div>
        <div style="font-size:11px;color:var(--text2);line-height:1.7;">${renderMd(data.analysis || '')}</div>
      </div>
    `;
  } catch (e) {
    result.innerHTML = '<div style="color:var(--red);font-size:10px;">Could not reach backend. Is the server running?</div>';
  } finally {
    btn.textContent = '⚡ Analyze Relationship';
    btn.disabled = false;
  }
}

// Allow Enter key to trigger lookup from either input
['lookupA','lookupB'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') runRelationshipLookup(); });
});

// ════════════════════════════════════════════════════════════
// SEARCH: AUTOCOMPLETE DROPDOWN + GLOBE FLY-TO
// ════════════════════════════════════════════════════════════

function flyToLatLon(lat, lon) {
  const targetX = lat * Math.PI / 180;
  const targetY = -lon * Math.PI / 180;
  const startX = rotX, startY = rotY;
  const startTime = performance.now();
  const duration  = 820;

  // Wrap rotY difference to shortest arc
  let dY = targetY - startY;
  while (dY >  Math.PI) dY -= 2 * Math.PI;
  while (dY < -Math.PI) dY += 2 * Math.PI;

  function ease(t) { return t < 0.5 ? 2*t*t : -1+(4-2*t)*t; }

  function step(now) {
    const t = Math.min((now - startTime) / duration, 1);
    const e = ease(t);
    rotX = startX + (targetX - startX) * e;
    rotY = startY + dY * e;
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

(function initSearch() {
  const input    = document.getElementById('searchInput');
  const dropdown = document.getElementById('searchDropdown');
  let focusIdx   = -1;

  function closeDropdown() {
    dropdown.classList.remove('open');
    dropdown.innerHTML = '';
    focusIdx = -1;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
  }

  function showDropdown(query) {
    const q = query.trim().toLowerCase();
    // Still update the events list for the sidebar
    updateEventsList();

    if (!q) { closeDropdown(); return; }

    // Search across ALL crises (not just current year) for the dropdown
    const results = CRISES
      .filter(c =>
        c.title.toLowerCase().includes(q) ||
        c.country.toLowerCase().includes(q) ||
        (c.type || '').toLowerCase().includes(q)
      )
      .sort((a, b) => {
        // Exact title-start match first, then severity desc
        const aStart = a.title.toLowerCase().startsWith(q) ? 0 : 1;
        const bStart = b.title.toLowerCase().startsWith(q) ? 0 : 1;
        return aStart - bStart || b.severity - a.severity;
      })
      .slice(0, 8);

    if (!results.length) {
      dropdown.innerHTML = `<div class="search-no-results">No crises found for "${escapeHtml(query)}"</div>`;
      dropdown.classList.add('open');
      return;
    }

    dropdown.innerHTML = '';
    results.forEach((crisis, i) => {
      const tm      = TYPE_META[crisis.type] || { color: '#888', name: 'Unknown' };
      const sevCol  = crisis.severity > 80 ? '#ff3b3b' : crisis.severity > 60 ? '#ff8833' : '#ffd93d';
      const year    = new Date(crisis.date_start || crisis.date).getFullYear() || '';
      const row     = document.createElement('div');
      row.className = 'search-result';
      row.id = `search-result-${i}`;
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', 'false');
      row.innerHTML = `
        <span class="sr-dot" style="background:${tm.color};color:${tm.color}"></span>
        <div class="sr-text">
          <div class="sr-title">${escapeHtml(crisis.title)}</div>
          <div class="sr-sub">${escapeHtml(crisis.country)}${year ? ' · ' + year : ''} · ${tm.name}</div>
        </div>
        <span class="sr-sev" style="background:${sevCol}22;color:${sevCol};border:1px solid ${sevCol}44">${crisis.severity}</span>
      `;
      row.addEventListener('mouseenter', () => {
        dropdown.querySelectorAll('.search-result').forEach(r => { r.classList.remove('focused'); r.setAttribute('aria-selected', 'false'); });
        row.classList.add('focused');
        row.setAttribute('aria-selected', 'true');
        focusIdx = i;
        input.setAttribute('aria-activedescendant', row.id);
      });
      row.addEventListener('click', () => {
        selectCrisis(crisis);
        if (crisis.lat != null && crisis.lon != null) flyToLatLon(crisis.lat, crisis.lon);
        input.value = crisis.title;
        closeDropdown();
      });
      dropdown.appendChild(row);
    });
    dropdown.classList.add('open');
    input.setAttribute('aria-expanded', 'true');
    focusIdx = -1;
  }

  input.addEventListener('input', e => showDropdown(e.target.value));

  input.addEventListener('keydown', e => {
    const rows = dropdown.querySelectorAll('.search-result');
    if (!rows.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      focusIdx = Math.min(focusIdx + 1, rows.length - 1);
      rows.forEach((r, i) => { r.classList.toggle('focused', i === focusIdx); r.setAttribute('aria-selected', i === focusIdx); });
      input.setAttribute('aria-activedescendant', rows[focusIdx].id);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      focusIdx = Math.max(focusIdx - 1, 0);
      rows.forEach((r, i) => { r.classList.toggle('focused', i === focusIdx); r.setAttribute('aria-selected', i === focusIdx); });
      input.setAttribute('aria-activedescendant', rows[focusIdx].id);
    } else if (e.key === 'Enter' && focusIdx >= 0) {
      rows[focusIdx].click();
    } else if (e.key === 'Escape') {
      closeDropdown();
      input.blur();
    }
  });

  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) closeDropdown();
  });
})();

// ════════════════════════════════════════════════════════════
// EXPORT: PRINTABLE INTELLIGENCE BRIEFING
// ════════════════════════════════════════════════════════════

function exportBriefing() {
  if (!selected) return;
  const c   = selected;
  const tm  = TYPE_META[c.type] || { color: '#333', name: 'Unknown' };
  const now = new Date().toLocaleDateString('en-US', { year:'numeric', month:'long', day:'numeric' });

  const el = id => document.getElementById(id);
  el('pb-date').textContent          = now;
  el('pb-footer-date').textContent   = `Generated ${now} by GeoIntel`;
  el('pb-title').textContent         = c.title;

  const sevColor = c.severity > 80 ? '#c0392b' : c.severity > 60 ? '#e67e22' : '#f39c12';
  el('pb-sev').innerHTML   = `<span style="color:${sevColor};font-weight:700">${c.severity}/100</span>`;
  el('pb-conf').textContent = `${c.confidence}%`;
  el('pb-type').textContent    = tm.name;
  el('pb-country').textContent = c.country;

  // Date
  const dateStr = c.date_start || c.date || '';
  const dYear   = dateStr ? new Date(dateStr).getFullYear() : '';
  el('pb-meta').innerHTML = `
    <span>${dYear || 'Date unknown'}</span>
    <span style="color:#bbb">·</span>
    <span>${tm.name}</span>
    <span style="color:#bbb">·</span>
    <span>Severity ${c.severity}</span>
  `;

  el('pb-analysis').textContent    = c.analysis  || 'No analysis available.';
  el('pb-impact').textContent      = c.impact    || 'No impact assessment available.';
  el('pb-stakeholders').textContent = c.stakeholders?.length
    ? c.stakeholders.map(s => ACTORS.find(a => a.id === s)?.name || s).join(', ')
    : 'No stakeholders identified.';

  window.print();
}
