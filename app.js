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
  election:          { name:'Election',         color:'#7c9fff' },
  referendum:        { name:'Referendum',        color:'#a78bfa' },
  leadership_change: { name:'Leadership Change', color:'#ffb347' },
  civil_unrest:      { name:'Civil Unrest',      color:'#ff5d8f' },
  summit:            { name:'Summit',            color:'#5eead4' },
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
    election:          'political',
    referendum:        'political',
    leadership_change: 'political',
    civil_unrest:      'political',
    summit:            'political',
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
const DEFAULT_ROTX = 0.25, DEFAULT_ROTY = 0, DEFAULT_ZOOM = 1;
let zoom = DEFAULT_ZOOM, rotX = DEFAULT_ROTX, rotY = DEFAULT_ROTY;
let selected = null;
let drag = false, lastMX = 0, lastMY = 0;
let mx = 0, my = 0;
let currentYear = 2026, playDir = 1, playing = false;
let lastSunUpdateAt = 0; // throttles the expensive getSubsolarPoint() call — see drawGlobe()
let cachedSubsolar = null; // last getSubsolarPoint() result; re-rotated into view space every frame
let showTrade = false; // sea routes
let showAir   = false; // air cargo corridors
let showRail  = false; // rail freight corridors
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

// Trade/transit routes across three modes — sea, air, rail. Each route is
// one object: { id, label, mode, waypoints: [[lat,lon], ...], vol (1-3),
// importance, cargo, ownership }. `waypoints` replaces a flat [lat1,lon1,
// lat2,lon2] pair because a single great-circle chord is only geographically
// sound between two points a vehicle could plausibly travel the straight
// line between — true for most air routes, false for most sea routes, and
// false for essentially all rail routes.
//
// Every SEA route's waypoint chain was verified by sampling ~40 points per
// segment (matching drawArcPath's own SLERP interpolation) and running each
// sample through a real point-in-polygon test against the actual 50m
// coastline mesh (topoFeaturesHigh) — not just eyeballing whether a traced
// lat/lon "looked" oceanic, which is exactly what let several of these ship
// past land-crossings through review earlier: a direct Suez–Rotterdam chord
// cuts across the Balkans, Rotterdam–Cape Town's cuts across Tunisia/Libya,
// Houston–Rotterdam's cuts across the entire continental US, LA–Panama's
// cuts across mainland Mexico, and Shanghai–Cape Town's cuts across
// Vietnam/Laos/Thailand/Myanmar and then Madagascar. Every sea route below
// is now a chain of real waypoints (Malacca Strait, Bab el-Mandeb, the
// Strait of Gibraltar, the Dover Strait, the Windward Passage, etc.) that
// passed that check with zero interior land hits (endpoints are port
// cities and are expected to be "on land").
const TRADE_ROUTES = [
  // Trans-Pacific
  { id:'shanghai-la', label:'Shanghai–LA', mode:'sea', vol:3, importanceScore:96,
    waypoints:[[31.2,121.5],[28.0,135.0],[33.7,-118.2]],
    importance:'The single busiest containerized trade lane in the world, linking China’s largest port to the US’s largest container gateway complex (LA/Long Beach).',
    cargo:'Manufactured consumer goods, electronics, furniture, and apparel moving from Chinese factories to US retail.',
    ownership:'No single owner — international waters (high seas under UNCLOS).' },
  { id:'tokyo-la', label:'Tokyo–LA', mode:'sea', vol:2, importanceScore:68,
    waypoints:[[35.7,139.7],[33.7,-118.2]],
    importance:'Backbone of Japan–US goods trade and a key artery for the just-in-time auto-parts supply chain.',
    cargo:'Automobiles, auto parts, and industrial machinery.',
    ownership:'No single owner — international waters.' },
  { id:'singapore-la', label:'Singapore–LA', mode:'sea', vol:2, importanceScore:62,
    waypoints:[[1.4,103.8],[33.7,-118.2]],
    importance:'Connects Southeast Asia’s largest transshipment hub directly to the US West Coast.',
    cargo:'Electronics, refined petroleum products, and transshipped regional manufactures.',
    ownership:'No single owner — international waters.' },
  // Asia–Europe corridor (Malacca → Indian Ocean → Bab el-Mandeb → Suez)
  { id:'shanghai-singapore', label:'Shanghai–Singapore', mode:'sea', vol:3, importanceScore:92,
    waypoints:[[31.2,121.5],[26.0,124.0],[10.0,114.0],[1.4,103.8]],
    importance:'The South China Sea leg of nearly all Asia-to-Europe and Asia-to-Middle East containerized trade, funneling into the Strait of Malacca.',
    cargo:'Containerized manufactured goods bound for Europe and the Middle East via the Malacca Strait.',
    ownership:'No single owner — international waters.' },
  { id:'mumbai-suez', label:'Mumbai–Suez', mode:'sea', vol:2, importanceScore:78,
    waypoints:[[19.1,72.9],[12.0,48.0],[12.5,43.55],[20.0,38.0],[30.0,32.5]],
    importance:'The Indian Ocean/Red Sea corridor carrying roughly 12% of global trade volume toward the Suez Canal; the Bab el-Mandeb leg has been repeatedly disrupted by Houthi attacks on shipping since late 2023.',
    cargo:'Containerized goods, crude oil and refined products, and South Asian textiles and pharmaceuticals bound for Europe.',
    ownership:'No single owner along most of the route; Bab el-Mandeb is bordered by Yemen and Djibouti/Eritrea but remains international waters.' },
  { id:'suez-rotterdam', label:'Suez–Rotterdam', mode:'sea', vol:3, importanceScore:90,
    waypoints:[[30.0,32.5],[31.5,32.3],[33.5,28.0],[36.0,15.0],[38.0,8.0],[35.9,-6.0],[36.0,-11.0],[46.0,-10.0],[49.8,-4.0],[50.3,-0.5],[51.0,1.5],[51.5,2.8],[51.9,4.5]],
    importance:'The Mediterranean/North Sea final leg of the Asia–Europe corridor, arriving at Europe’s largest port.',
    cargo:'Containerized consumer goods, chemicals, and refined petroleum products.',
    ownership:'The Suez Canal segment is owned and operated by the Egyptian Suez Canal Authority (SCA); the remainder is international waters.' },
  // Indian Ocean
  { id:'dubai-mumbai', label:'Dubai–Mumbai', mode:'sea', vol:2, importanceScore:55,
    waypoints:[[25.2,55.3],[19.1,72.9]],
    importance:'A short but heavily trafficked Gulf-to-South Asia feeder lane; Dubai’s Jebel Ali is the Gulf’s dominant transshipment hub.',
    cargo:'Refined petroleum products, foodstuffs, and re-exported manufactured goods.',
    ownership:'No single owner — international waters.' },
  { id:'singapore-mumbai', label:'Singapore–Mumbai', mode:'sea', vol:2, importanceScore:60,
    waypoints:[[1.4,103.8],[2.0,102.0],[3.5,100.2],[5.5,97.5],[6.0,95.0],[7.0,92.0],[5.0,80.0],[10.0,74.0],[19.1,72.9]],
    importance:'Connects Southeast Asian transshipment volume to India’s largest port complex.',
    cargo:'Containerized manufactures, electronics, and chemicals.',
    ownership:'No single owner — international waters.' },
  // North Atlantic
  { id:'ny-rotterdam', label:'NY–Rotterdam', mode:'sea', vol:3, importanceScore:88,
    waypoints:[[40.7,-74.0],[42.0,-50.0],[47.0,-15.0],[49.8,-4.0],[50.3,-0.5],[51.0,1.5],[51.5,2.8],[51.9,4.5]],
    importance:'The primary container corridor of the transatlantic trade, the world’s second-largest bilateral trade relationship.',
    cargo:'Machinery, pharmaceuticals, chemicals, automobiles, and agricultural products.',
    ownership:'No single owner — international waters.' },
  { id:'houston-rotterdam', label:'Houston–Rotterdam', mode:'sea', vol:2, importanceScore:70,
    waypoints:[[29.8,-95.4],[25.0,-88.0],[24.0,-82.0],[24.0,-80.0],[35.0,-70.0],[47.0,-15.0],[49.8,-4.0],[50.3,-0.5],[51.0,1.5],[51.5,2.8],[51.9,4.5]],
    importance:'A key energy and petrochemical corridor linking the US Gulf Coast refining/export complex to European markets.',
    cargo:'Crude oil, LNG, refined petroleum products, and petrochemicals/plastics.',
    ownership:'No single owner — international waters.' },
  // Cape Route (Africa) — Shanghai–Cape Town reuses the same Malacca-Strait
  // transit as Shanghai–Singapore/Singapore–Mumbai, then passes south of
  // Sri Lanka and south of Madagascar; Rotterdam–Cape Town stays in the
  // Atlantic well clear of the West African coast the whole way.
  { id:'shanghai-capetown', label:'Shanghai–Cape Town', mode:'sea', vol:1, importanceScore:50,
    waypoints:[[31.2,121.5],[26.0,124.0],[10.0,114.0],[1.4,103.8],[2.0,102.0],[3.5,100.2],[5.5,97.5],[6.0,95.0],[7.0,92.0],[0.0,80.0],[-30.0,45.0],[-33.9,18.4]],
    importance:'An alternative to the Suez route around the Cape of Good Hope, used increasingly since 2023 to avoid Red Sea attacks despite adding roughly 10 days of transit.',
    cargo:'Containerized goods rerouted from the Suez corridor; South African minerals on return legs.',
    ownership:'No single owner — international waters.' },
  { id:'rotterdam-capetown', label:'Rotterdam–Cape Town', mode:'sea', vol:1, importanceScore:45,
    waypoints:[[51.9,4.5],[51.5,2.8],[51.0,1.5],[50.3,-0.5],[47.0,-8.0],[36.0,-12.0],[21.0,-21.0],[0.0,-15.0],[-25.0,3.0],[-33.9,18.4]],
    importance:'European leg of the Cape route, and a direct link to South Africa’s import/export economy.',
    cargo:'Manufactured imports to South Africa; export legs carry coal, iron ore, and precious metals.',
    ownership:'No single owner — international waters.' },
  // Americas
  { id:'ny-panama', label:'NY–Panama', mode:'sea', vol:2, importanceScore:65,
    waypoints:[[40.7,-74.0],[20.0,-74.0],[9.0,-79.5]], // via the Windward Passage, east of Cuba
    importance:'US East Coast access to the Panama Canal, the shortcut between the Atlantic and Pacific.',
    cargo:'Containerized goods and bulk grain awaiting canal transit.',
    ownership:'No single owner along the sea route; the Panama Canal itself is owned and operated by the Panama Canal Authority (ACP), a Panamanian government agency, since the US handed over full control in 1999.' },
  { id:'la-panama', label:'LA–Panama', mode:'sea', vol:2, importanceScore:63,
    waypoints:[[33.7,-118.2],[20.0,-115.0],[10.0,-90.0],[6.5,-81.0],[6.0,-80.0],[9.0,-79.5]],
    importance:'US West Coast feeder into the Panama Canal, an alternative to overland rail for Asia-to-US-East-Coast cargo.',
    cargo:'Containerized Asian imports transshipping toward the US Gulf and East Coasts.',
    ownership:'No single owner along the sea route; the Panama Canal itself is owned and operated by the Panama Canal Authority (ACP).' },
  // Key straits (short markers)
  { id:'strait-of-malacca', label:'Strait of Malacca', mode:'sea', vol:3, importanceScore:99,
    waypoints:[[1.4,103.8],[2.0,102.0],[3.5,100.2],[5.5,97.5],[5.5,95.3]],
    importance:'The world’s busiest and most critical shipping chokepoint by volume — roughly a quarter of all seaborne trade, including most of China’s oil imports, passes through here.',
    cargo:'Crude oil (especially to China, Japan, and South Korea), containerized goods, and LNG.',
    ownership:'No single owner; littoral states Indonesia, Malaysia, and Singapore jointly patrol and manage traffic under the Malacca Strait Patrol, but the strait remains international waters.' },
  { id:'bab-el-mandeb', label:'Bab el-Mandeb', mode:'sea', vol:2, importanceScore:82,
    waypoints:[[12.5,43.5],[11.5,43.5]],
    importance:'Gateway between the Red Sea/Suez Canal and the Indian Ocean; a Houthi missile and drone campaign against shipping here since late 2023 has forced many carriers onto the longer Cape of Good Hope route.',
    cargo:'Containerized Asia–Europe trade, crude oil, and LNG.',
    ownership:'No single owner — bordered by Yemen to the east and Djibouti/Eritrea to the west; international waters.' },
  { id:'strait-of-hormuz', label:'Strait of Hormuz', mode:'sea', vol:3, importanceScore:97,
    waypoints:[[26.5,56.5],[24.5,58.5]],
    importance:'The world’s most important oil chokepoint — roughly one-fifth of global oil consumption transits here; Iran has repeatedly threatened to close it during periods of tension with the US and West.',
    cargo:'Crude oil and LNG, overwhelmingly.',
    ownership:'No single owner — bordered by Iran to the north and Oman to the south; international waters.' },
];

// Air cargo corridors. Aircraft aren't blocked by land the way ships are,
// so most of these are simple 2-point great-circle hops between hub
// airports — except Hong Kong–Dubai–Frankfurt, deliberately bent through
// Dubai rather than a direct arc, because most Western/Asian carriers have
// avoided Russian airspace since 2022 and now route south through Gulf
// hubs instead of the shorter polar/Siberian great circle — a real,
// current geopolitical cost reflected directly in the flown path.
const AIR_ROUTES = [
  { id:'hk-anc-memphis', label:'Hong Kong–Anchorage–Memphis', mode:'air', vol:3, importanceScore:88,
    waypoints:[[22.3,113.9],[61.2,-149.9],[35.0,-90.0]],
    importance:'Backbone of express and e-commerce air freight between Asia and North America; Anchorage’s position makes it the great-circle refueling waypoint for nearly all trans-Pacific cargo flights, and Memphis is FedEx’s global superhub.',
    cargo:'High-value express parcels, electronics, e-commerce goods, and pharmaceuticals.',
    ownership:'No single owner — international and US sovereign airspace; Anchorage airport is operated by the State of Alaska, Memphis hub privately operated by FedEx.' },
  { id:'shanghai-la-air', label:'Shanghai–LA (Air)', mode:'air', vol:3, importanceScore:85,
    waypoints:[[31.2,121.5],[33.9,-118.4]],
    importance:'The dominant Asia–US air cargo lane for time-sensitive e-commerce, driven heavily by cross-border parcel volume from Chinese platforms.',
    cargo:'E-commerce parcels, electronics, and express apparel shipments.',
    ownership:'No single owner — international and US sovereign airspace; LAX operated by Los Angeles World Airports.' },
  { id:'incheon-anc-chicago', label:'Incheon–Anchorage–Chicago', mode:'air', vol:2, importanceScore:60,
    waypoints:[[37.5,126.4],[61.2,-149.9],[41.98,-87.9]],
    importance:'Korea’s main air-cargo gateway to the US Midwest, again routed via the Anchorage refueling hub.',
    cargo:'Semiconductors, electronics components, and automotive parts.',
    ownership:'No single owner — international and US sovereign airspace.' },
  { id:'hk-dubai-frankfurt', label:'Hong Kong–Dubai–Frankfurt', mode:'air', vol:3, importanceScore:84,
    waypoints:[[22.3,113.9],[25.25,55.36],[50.03,8.57]],
    importance:'The main Asia–Europe air cargo corridor. Historically flown closer to a direct great circle over Russia/Central Asia, but since Russia closed its airspace to most Western carriers in 2022, traffic has shifted south via Gulf hubs like Dubai — adding hours of flight time as a direct, visible cost of the closure.',
    cargo:'Electronics, pharmaceuticals, and high-value manufactured goods.',
    ownership:'No single owner — sovereign airspace of each country overflown; hub operators are Dubai Airports and Fraport AG (Frankfurt).' },
  { id:'dubai-london', label:'Dubai–London', mode:'air', vol:2, importanceScore:66,
    waypoints:[[25.25,55.36],[51.47,-0.45]],
    importance:'Connects the Gulf’s largest cargo and passenger hub to Europe’s busiest airport by international freight tonnage.',
    cargo:'Express freight, pharmaceuticals, and high-value or perishable goods such as fresh produce and flowers.',
    ownership:'No single owner — sovereign airspace of countries overflown; Heathrow is operated by Heathrow Airport Holdings.' },
];

// Rail freight corridors. Unlike sea routes, these are *supposed* to run
// overland through Central Asia and Russia — rail is fully constrained to
// physical track, so the same Kazakhstan/Russia corridor that was wrong
// for a ship (see the comment on TRADE_ROUTES above) is exactly correct
// here. Do not "fix" these to avoid land the way the sea routes were fixed.
const RAIL_ROUTES = [
  { id:'cn-europe-northern', label:'China–Europe Railway Express (Northern Corridor)', mode:'rail', vol:3, importanceScore:80,
    waypoints:[[34.3,108.9],[44.2,80.4],[51.2,71.4],[55.75,37.6],[53.9,27.6],[52.2,21.0],[51.4,6.8]],
    importance:'The flagship "Belt and Road" rail corridor, cutting China–Europe transit time to roughly 15-18 days versus 35-45 days by sea; over 15,000 trains ran in 2023 alone.',
    cargo:'Electronics, machinery, and automobiles eastbound-return; European autos, food products, and machinery westbound-return from Europe.',
    ownership:'Jointly operated across the state railways of China (China Railway), Kazakhstan (KTZ), Russia (RZD), Belarus (BCh), and Poland (PKP), coordinated under the China Railway Express brand.' },
  { id:'middle-corridor', label:'Middle Corridor (Trans-Caspian)', mode:'rail', vol:2, importanceScore:62,
    waypoints:[[44.2,80.4],[43.65,51.2],[40.4,49.9],[41.7,44.8],[41.0,28.9]],
    importance:'The sanctions-era alternative to the Russia-transiting Northern Corridor, crossing the Caspian Sea by ferry between Kazakhstan and Azerbaijan; volumes have surged since 2022 as shippers avoid Russian territory, though ferry capacity remains a bottleneck.',
    cargo:'Containerized goods, grain, and minerals rerouted off the Northern Corridor.',
    ownership:'Coordinated by a multilateral Middle Corridor consortium of the state railways and port authorities of Kazakhstan, Azerbaijan, Georgia, and Turkey, with no single national operator.' },
  { id:'trans-siberian', label:'Trans-Siberian Railway', mode:'rail', vol:2, importanceScore:48,
    waypoints:[[43.1,131.9],[56.0,92.9],[55.75,37.6]],
    importance:'The historic backbone of Russian domestic and Pacific-to-European freight, and (before 2022) a transit option for Asia–Europe container traffic — now used almost exclusively for Russian domestic and regional trade given Western sanctions and avoidance.',
    cargo:'Coal, timber, oil and gas products, and containerized domestic freight.',
    ownership:'Owned and operated by Russian Railways (RZD), a Russian state-owned company.' },
  { id:'na-intermodal', label:'North American Intermodal (LA–Chicago–NY)', mode:'rail', vol:3, importanceScore:82,
    waypoints:[[33.7,-118.2],[41.85,-87.65],[40.7,-74.0]],
    importance:'The rail backbone that moves trans-Pacific container traffic inland from West Coast ports to the US interior and East Coast, avoiding a much longer all-water Panama Canal route.',
    cargo:'Containerized imports from Asia — electronics, apparel, consumer goods; eastbound-return also carries US agricultural exports back toward West Coast ports.',
    ownership:'Operated by privately owned US Class I railroads — primarily BNSF and Union Pacific from the coast to Chicago, then CSX and Norfolk Southern onward to the East Coast.' },
];

const ALL_ROUTES = [...TRADE_ROUTES, ...AIR_ROUTES, ...RAIL_ROUTES];
const ROUTES_BY_ID = new Map(ALL_ROUTES.map(r => [r.id, r]));

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

// Layer toggles
let showArcs  = false;
let showHeat  = false;
let showCasc  = false;
let flatMap   = false;

// Severity filter (0 = all, 80 = critical only)
let minSeverityFilter = 0;

// Bookmarks persisted in localStorage, keyed by the crisis's real string id
// (e.g. "sample_kyiv") — this used to coerce every id to Number(), which
// collapses any non-numeric string to NaN. Since Set membership treats NaN
// as equal to itself, bookmarking ANY one crisis silently marked EVERY
// crisis as bookmarked. `.filter(id => typeof id === 'string')` drops any
// leftover `null` entries from that old bug (JSON.stringify(NaN) → "null"),
// so existing corrupted localStorage state self-heals on next load instead
// of showing a phantom entry forever.
const bookmarks = new Set(
  (JSON.parse(localStorage.getItem('geointel_bookmarks') || '[]')).filter(id => typeof id === 'string')
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
//
// devicePixelRatio is capped at 2: many phones report 3 (some higher),
// which would size the backing store to 9x the pixel count of a DPR=1
// screen (3x in each dimension) — for a full-viewport canvas redrawn every
// frame, including a per-pixel terrain-shading pass, that's a dominant cost
// on hardware already weaker than desktop. 2x is still indistinguishable
// from native on a phone screen; the difference above that is not visible
// at normal viewing distance but the CPU/GPU cost of pushing that many
// more pixels every frame very much is.
function getCanvasDPR() { return Math.min(2, window.devicePixelRatio || 1); }

function fitCanvasToDisplay(cvs, context) {
  const dpr  = getCanvasDPR();
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
// Raw view-space unit vector for a lat/lon, before the screen-projection
// step — shared by project() and the sun/day-night overlay in drawGlobe(),
// so both agree exactly on where a given lat/lon currently sits relative
// to the camera.
function latLonToViewVec(lat, lon) {
  if (rotX !== _rotXCache) { _cosRotX = Math.cos(rotX); _sinRotX = Math.sin(rotX); _rotXCache = rotX; }
  const phi = lat * Math.PI / 180;
  const lam = lon * Math.PI / 180;
  const cp  = Math.cos(phi);
  const x   = cp * Math.sin(lam + rotY);
  const y   = Math.sin(phi) * _cosRotX - cp * Math.cos(lam + rotY) * _sinRotX;
  const z   = Math.sin(phi) * _sinRotX + cp * Math.cos(lam + rotY) * _cosRotX;
  return { x, y, z };
}
function project(lat, lon) {
  const { x, y, z } = latLonToViewVec(lat, lon);
  const r = R();
  return { sx: CX() + r * x, sy: CY() - r * y, z };
}

// Draw filled/stroked geo ring. `targetCtx` defaults to the main canvas
// context but can be an offscreen one — see the high-detail land cache in
// drawGlobe(), which renders the (expensive, ~80k-point) 50m mesh into a
// cached bitmap rather than replaying this every frame.
// `batch`: when true, don't paint per-ring — just add this ring's visible
// run(s) as subpath(s) of the caller's already-open path (via moveTo,
// which starts a new subpath without discarding earlier ones — no
// beginPath() needed between runs). The caller does ONE beginPath() before
// the whole batch and ONE fill()/stroke() after. This matters a lot at
// high-detail-mesh scale: painting ~241 countries (each with, on average,
// several rings/back-face-split runs) via a separate fill() per run was
// measured at ~210ms; canvas fill()/stroke() calls carry real fixed
// overhead beyond the geometry itself, so batching hundreds of them into
// one call is a large win, not just a constant-factor one. Non-batch
// behavior (the default) is unchanged — every existing caller still gets
// its own independent, immediately-painted path.
// `projectFn` defaults to the rotating-globe project() but can be swapped
// for a flat equirectangular mapping (see bakeEquirectTexture) to reuse
// this same fill/stroke logic for baking the WebGL sphere's texture
// instead of drawing onto the rotating 2D canvas.
function geoRing(ring, fill, targetCtx = ctx, batch = false, projectFn = project) {
  let started = false;
  let prevLon = null;
  for (let i = 0; i < ring.length; i++) {
    const [lo, la] = ring[i];
    // A >180° raw-longitude jump between consecutive ring vertices means
    // this edge crosses the antimeridian — break the subpath instead of
    // connecting it with a lineTo, or a flat/equirect projectFn (see
    // bakeEquirectTexture) draws a rogue edge spanning nearly the whole
    // canvas width (this is how Antarctica's coastline, which circles all
    // longitudes, produced a hole in its own fill and glitched the pole
    // row it happened to land near).
    if (prevLon !== null && Math.abs(lo - prevLon) > 180) {
      if (started && !batch) { fill ? targetCtx.fill() : targetCtx.stroke(); }
      started = false;
    }
    prevLon = lo;
    const p = projectFn(la, lo);
    // Frustum culling: skip back-facing coordinates (z < -0.1)
    if (p.z < -0.1) { if (started && !batch) { fill ? targetCtx.fill() : targetCtx.stroke(); } started = false; continue; }
    if (!started) { if (!batch) targetCtx.beginPath(); targetCtx.moveTo(p.sx, p.sy); started = true; }
    else targetCtx.lineTo(p.sx, p.sy);
  }
  if (started && !batch) { fill ? targetCtx.fill() : targetCtx.stroke(); }
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

// For each route, compute a risk level (0–3) based on nearby active crises
function routeRiskLevel(waypoints) {
  // Sample along the *actual* great-circle path — the same SLERP used to
  // draw the arc (see drawArcPath/latLonToVec/slerpVec below) — rather than
  // naive lat/lon linear interpolation. That mattered a lot here: every
  // trans-Pacific route (Shanghai-LA, Tokyo-LA, Singapore-LA) crosses the
  // antimeridian, where linearly "averaging" longitude lands nowhere near
  // the real path — e.g. Shanghai (121.5°E) and LA (-118.2°) average to
  // ~1.65°E, near Africa, while the real route crosses the Pacific near
  // 180°. Risk was being checked against the wrong hemisphere entirely for
  // those routes.
  //
  // Generalized to a waypoints array (not just 2 endpoints) so long
  // multi-hop routes — rail corridors especially — get checked against
  // crises along their whole path, not just their two far-apart ends. Each
  // interior segment's t=0 sample is skipped since it's identical to the
  // previous segment's t=1.
  const samples = [];
  for (let seg = 0; seg < waypoints.length - 1; seg++) {
    const v1 = latLonToVec(waypoints[seg][0], waypoints[seg][1]);
    const v2 = latLonToVec(waypoints[seg + 1][0], waypoints[seg + 1][1]);
    const ts = seg === 0 ? [0, 0.25, 0.5, 0.75, 1] : [0.25, 0.5, 0.75, 1];
    for (const t of ts) samples.push(vecToLatLon(slerpVec(v1, v2, t)));
  }
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

// Route color can show either dynamic "risk" (nearby-crisis-driven,
// ROUTE_RISK_COLORS above) or static "importance" (how vital the route is
// to global trade, independent of current events) — a toggle button swaps
// which one the globe/panel/tooltip all key off of. A straight RGB lerp
// (not an HSL hue rotation) is used so the importance gradient's midtones
// don't visually collide with the risk gradient's yellow/orange midtones.
let routeColorMode = 'risk'; // 'risk' | 'importance'
const IMPORTANCE_COLOR_LOW  = [61, 255, 170];  // matches ROUTE_RISK_COLORS[0], #3dffaa
const IMPORTANCE_COLOR_HIGH = [255, 59, 59];   // matches ROUTE_RISK_COLORS[3], #ff3b3b
function importanceColor(score) {
  const t = Math.max(0, Math.min(100, score ?? 50)) / 100;
  const lerp = (i) => Math.round(IMPORTANCE_COLOR_LOW[i] + (IMPORTANCE_COLOR_HIGH[i] - IMPORTANCE_COLOR_LOW[i]) * t);
  const toHex = (n) => n.toString(16).padStart(2, '0');
  return `#${toHex(lerp(0))}${toHex(lerp(1))}${toHex(lerp(2))}`; // hex, matching ROUTE_RISK_COLORS' format so '+alpha' suffixes work
}

// 4-stop blue→green→yellow→red heat-map ramp. Unlike importanceColor()
// (2-stop, returns a hex string for CSS use), this writes raw RGB values
// into a reused output array — it runs once per pixel in
// drawCrisisHeatmap()'s colorize pass, so no string formatting or
// allocation in the hot path.
const HEAT_RAMP = [
  [30,  60,  220],   // 0.00 cool blue — low/no density
  [40,  200, 120],   // 0.33 green
  [230, 210, 40],    // 0.66 yellow
  [230, 40,  40],    // 1.00 red — peak density
];
function heatRampColor(t, out) {
  t = Math.max(0, Math.min(1, t));
  const scaled = t * (HEAT_RAMP.length - 1);
  const i0 = Math.min(HEAT_RAMP.length - 2, Math.floor(scaled));
  const localT = scaled - i0;
  const c0 = HEAT_RAMP[i0], c1 = HEAT_RAMP[i0 + 1];
  out[0] = c0[0] + (c1[0] - c0[0]) * localT;
  out[1] = c0[1] + (c1[1] - c0[1]) * localT;
  out[2] = c0[2] + (c1[2] - c0[2]) * localT;
}

// Visual differentiation between the three route modes — risk-based color
// stays meaningful for all three (so it isn't spent on distinguishing
// mode), dash pattern is what tells sea/air/rail apart when layers overlap.
// Sea and rail get a thicker, glowing "highlight" treatment rather than a
// thin line: their waypoint-to-waypoint segments are individually shorter
// than a typical single-hop flight, so each segment's great-circle
// curvature is subtler — a thin or dotted line makes that curve easy to
// miss entirely, while a bold glowing stroke makes it unmistakable. Air
// stays a thin dashed line, matching how flight paths are usually drawn.
const MODE_STYLE = {
  sea:  { dash: [],     widthMul: 2.0, glow: true  },
  air:  { dash: [6, 4], widthMul: 1.0, glow: false },
  rail: { dash: [2, 3], widthMul: 2.0, glow: true  },
};

// Stores screen-space hit-points for hover/click detection, updated each draw
let tradeRouteScreenPts = [];

// Draw whichever route layers are currently toggled on, color-coded by
// disruption risk and styled by mode (see MODE_STYLE).
function drawAllRoutes() {
  tradeRouteScreenPts = [];
  if (showTrade) drawRouteSet(TRADE_ROUTES);
  if (showAir)   drawRouteSet(AIR_ROUTES);
  if (showRail)  drawRouteSet(RAIL_ROUTES);
}

function drawRouteSet(routes) {
  routes.forEach(route => {
    const risk  = routeRiskLevel(route.waypoints);
    const color = routeColorMode === 'importance'
      ? importanceColor(route.importanceScore ?? route.vol * 30)
      : ROUTE_RISK_COLORS[risk];
    const style = MODE_STYLE[route.mode];
    const alpha = Math.min(1, 0.3 + route.vol * 0.1 + (risk > 0 ? 0.15 : 0) + (style.glow ? 0.1 : 0));
    const width = (0.7 + route.vol * 0.4 + (risk * 0.3)) * style.widthMul;
    drawArcPath(route.waypoints, color, width, alpha, style.dash, style.glow);

    // Hit-point for hover/click detection: the route's actual middle
    // waypoint (a real point on the path) rather than a linear midpoint of
    // its endpoints, which for a bent multi-hop route can land nowhere
    // near the drawn line.
    const mid = route.waypoints[Math.floor(route.waypoints.length / 2)];
    const mp = project(mid[0], mid[1]);
    if (mp.z > 0) tradeRouteScreenPts.push({ id: route.id, mode: route.mode, label: route.label, vol: route.vol, risk, importanceScore: route.importanceScore, sx: mp.sx, sy: mp.sy });
  });
}

function drawGeoFeature(geom, fill, targetCtx = ctx, batch = false, projectFn = project) {
  if (!geom) return;
  if (geom.type === 'Polygon')      geom.coordinates.forEach(r => geoRing(r, fill, targetCtx, batch, projectFn));
  else if (geom.type === 'MultiPolygon') geom.coordinates.forEach(p => p.forEach(r => geoRing(r, fill, targetCtx, batch, projectFn)));
}

// See geoRing's comment for what `batch` and `projectFn` mean and why they exist.
function drawGeoMesh(geom, targetCtx = ctx, batch = false, projectFn = project) {
  if (!geom || geom.type !== 'MultiLineString') return;
  geom.coordinates.forEach(line => {
    let started = false;
    let prevLon = null;
    for (const [lo, la] of line) {
      // See geoRing's matching comment — same antimeridian-crossing break.
      if (prevLon !== null && Math.abs(lo - prevLon) > 180) {
        if (started && !batch) { targetCtx.stroke(); }
        started = false;
      }
      prevLon = lo;
      const p = projectFn(la, lo);
      if (p.z < 0) { if (started && !batch) { targetCtx.stroke(); } started = false; continue; }
      if (!started) { if (!batch) targetCtx.beginPath(); targetCtx.moveTo(p.sx, p.sy); started = true; }
      else targetCtx.lineTo(p.sx, p.sy);
    }
    if (started && !batch) targetCtx.stroke();
  });
}

// Approximate subsolar point (the lat/lon where the sun is directly
// overhead) for real-time day/night shading. ~1° accuracy — plenty for a
// visual effect, no equation-of-time correction needed.
function getSubsolarPoint(date = new Date()) {
  const start = Date.UTC(date.getUTCFullYear(), 0, 1);
  const dayOfYear = Math.floor((date.getTime() - start) / 86400000);
  const declination = -23.44 * Math.cos((2 * Math.PI / 365) * (dayOfYear + 10));
  const utcHours = date.getUTCHours() + date.getUTCMinutes() / 60;
  const subsolarLon = -(utcHours - 12) * 15;
  return { lat: declination, lon: subsolarLon };
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

// Same great-circle drawing as drawArc(), generalized to a path of 2+
// waypoints instead of exactly 2 — draws one continuous stroke across all
// consecutive segments, with an optional dash pattern and glow (see
// MODE_STYLE) for telling route modes apart when multiple layers overlap.
// drawArc() itself is left untouched since relationship arcs and
// cascade-sim arcs still use it directly and only ever need 2 points.
function drawArcPath(waypoints, color, width = 1.2, alpha = 0.5, dash = [], glow = false) {
  const steps = 60;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dash);
  if (glow) {
    ctx.shadowColor = color;
    ctx.shadowBlur = 10;
  }

  let started = false;
  for (let seg = 0; seg < waypoints.length - 1; seg++) {
    const v1 = latLonToVec(waypoints[seg][0], waypoints[seg][1]);
    const v2 = latLonToVec(waypoints[seg + 1][0], waypoints[seg + 1][1]);
    for (let i = 0; i <= steps; i++) {
      const [la, lo] = vecToLatLon(slerpVec(v1, v2, i / steps));
      const p = project(la, lo);
      if (p.z < 0) { if (started) { ctx.stroke(); started = false; } continue; }
      if (!started) { ctx.beginPath(); ctx.moveTo(p.sx, p.sy); started = true; }
      else ctx.lineTo(p.sx, p.sy);
    }
  }
  if (started) ctx.stroke();
  ctx.setLineDash([]); // reset so later ctx.stroke() calls this frame aren't dashed
  ctx.restore();
}

// Pulse animation state
let pulse = 0;

// Canvas size optimization - track previous dimensions to avoid redundant resizing
let lastCanvasWidth = 0, lastCanvasHeight = 0;

// ── World map data (low/high detail) ────────────────────────────────────
// The 3D globe's land/border/terrain rendering moved to WebGL (see
// webgl-globe.js and bakeEquirectTexture() below) — it bakes a texture
// once from whichever of these has loaded, rather than re-projecting
// points every frame, so the low/high split and isSettled()/markMotion()
// below no longer matter for THAT. They're kept because drawFlatMap()'s
// 2D flat-map mode (a separate, unrelated view — see flatProject()) still
// uses the same live/settled mesh-swap pattern for its own performance.
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
    if (activeType !== 'all' && c.type !== activeType) return false;
    if (activeDomain !== 'all' && getDomainForType(c.type) !== activeDomain) return false;
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
// just an array index, not a draw call. Applied once into the WebGL
// sphere's baked texture (see bakeEquirectTexture / sampleElevationBilinear
// below) rather than per-frame — baking it in means the per-pixel relief
// pass only ever runs when the texture is (re)built, not every frame.
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

// NOTE: heatmap mode (showHeat) and highlighted-country glow used to be
// handled here (recoloring the land fill / drawing a glow) when this was
// rendered per-frame onto the rotating canvas. Now that the sphere is a
// GPU-rendered, one-time-baked texture (see bakeEquirectTexture below),
// showHeat now drives drawCrisisHeatmap() (Canvas2D overlay, not the
// WebGL texture — see its own comment), a crisis-density view rather
// than the old per-actor power glow. Two things remain deliberate,
// documented gaps rather than
// oversights: (1) showHeat's old land-recolor (#1a4a2e vs the baked
// texture's current land color — a barely perceptible difference) would
// require re-baking the WebGL texture on every toggle for negligible
// visual gain; (2) highlighted-country glow isn't wired back in at all.
// Both toggle buttons still work without erroring. The old logic (land
// recolor, highlighted-country outline) is preserved in git history.

// ════════════════════════════════════════════════════════════
// WEBGL GLOBE INTEGRATION — bakes land/borders/terrain into a flat
// equirectangular texture (once, not per frame) for the GPU sphere in
// webgl-globe.js to display. See the plan file for the full architecture.
// ════════════════════════════════════════════════════════════

// Pure, static equirect mapping — NOT flatProject() (which is the
// interactive flat-MAP mode's projection and carries its own pan/zoom
// state, fZoom/fPanX/fPanY, that a one-time texture bake must not use).
// The +TEXTURE_LON_OFFSET_DEG matches the geometry-axis correction
// applied to the sphere mesh in webgl-globe.js — both sides of that
// correction must agree, see that file's comment for the derivation.
function flatProjectForBake(lat, lon, W, H) {
  const lonOffset = (window.GlobeGL && window.GlobeGL.TEXTURE_LON_OFFSET_DEG) || 0;
  const wrappedLon = ((lon + lonOffset + 180) % 360 + 360) % 360 - 180;
  return {
    sx: (wrappedLon + 180) / 360 * W,
    sy: (90 - lat) / 180 * H,
    z: 1, // an equirect bake has no back side to cull
  };
}

const EQUIRECT_TEXTURE_W = 4096, EQUIRECT_TEXTURE_H = 2048;
let equirectCanvas = null, equirectCtx = null;

// Bakes ocean + land + borders (+ terrain relief, if the elevation texture
// has finished loading) once into a flat canvas and hands it to
// window.GlobeGL as the sphere's texture. Cheap relative to the OLD
// per-frame rotating-mesh redraw this replaces — this only ever runs when
// the underlying data actually changes (mesh tier upgrade from low→high
// res), not every frame or every rotation.
function bakeEquirectTexture(features, borders) {
  if (!window.GlobeGL || !window.GlobeGL.ready) return;
  if (!equirectCanvas) {
    equirectCanvas = document.createElement('canvas');
    equirectCanvas.width = EQUIRECT_TEXTURE_W;
    equirectCanvas.height = EQUIRECT_TEXTURE_H;
    equirectCtx = equirectCanvas.getContext('2d');
  }
  const W = EQUIRECT_TEXTURE_W, H = EQUIRECT_TEXTURE_H;
  const bakeProject = (lat, lon) => flatProjectForBake(lat, lon, W, H);

  equirectCtx.clearRect(0, 0, W, H);
  equirectCtx.fillStyle = '#0f4068';
  equirectCtx.fillRect(0, 0, W, H);

  // One beginPath()/fill() PER FEATURE (batch=true still applies within a
  // feature's own rings) rather than one accumulated path across every
  // country — bounds any residual antimeridian/winding defect to a single
  // country instead of letting it punch holes in unrelated fill coverage
  // sharing the same scanline (this is how Antarctica's coastline used to
  // leave a stray ocean-colored gap). Runs twice total (once per LOD
  // tier), not per frame, so the extra fill() calls are free.
  equirectCtx.fillStyle = 'rgba(26,60,40,0.95)';
  features.forEach(f => {
    equirectCtx.beginPath();
    drawGeoFeature(f.geometry, true, equirectCtx, true, bakeProject);
    equirectCtx.fill();
  });

  if (elevationPixels) {
    // Per-pixel relief-shading factor, applied once to the flat bake
    // instead of per-frame to a rotated canvas (the old approach, before
    // this became a WebGL-rendered sphere) — sample (lon,lat) directly
    // from pixel coordinates since there's no rotation to invert here.
    const imgData = equirectCtx.getImageData(0, 0, W, H);
    const px = imgData.data;
    for (let py = 0; py < H; py++) {
      const lat = 90 - (py / H) * 180;
      for (let pxi = 0; pxi < W; pxi++) {
        const idx = (py * W + pxi) * 4;
        if (px[idx + 3] === 0) continue; // ocean, not land
        const lon = (pxi / W) * 360 - 180;
        const elev = sampleElevationBilinear(lon, lat);
        const factor = 1 + (elev - 55) / 255 * 0.85;
        px[idx]     = Math.min(255, Math.max(0, px[idx]     * factor));
        px[idx + 1] = Math.min(255, Math.max(0, px[idx + 1] * factor));
        px[idx + 2] = Math.min(255, Math.max(0, px[idx + 2] * factor));
      }
    }
    equirectCtx.putImageData(imgData, 0, 0);
  }

  equirectCtx.strokeStyle = 'rgba(255,255,255,0.25)';
  equirectCtx.lineWidth = 1.2;
  equirectCtx.beginPath();
  drawGeoMesh(borders, equirectCtx, true, bakeProject);
  equirectCtx.stroke();

  window.GlobeGL.regenerateTexture(equirectCanvas);
}

function drawGlobe() {
  // Flat map mode — skip 3D globe entirely
  if (flatMap) { drawFlatMap(); return; }

  // Only resize canvas if dimensions actually changed (avoid expensive layout recalc on every frame)
  const newWidth = canvas.clientWidth;
  const newHeight = canvas.clientHeight;
  if (newWidth !== lastCanvasWidth || newHeight !== lastCanvasHeight) {
    fitCanvasToDisplay(canvas, ctx);
    if (window.GlobeGL && window.GlobeGL.ready) window.GlobeGL.resize(newWidth, newHeight, getCanvasDPR());
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

  // #canvas is now a transparent overlay — the sphere itself (ocean, land,
  // borders, terrain relief, real-time day/night lighting) is rendered by
  // the GPU onto #glCanvas beneath it; see webgl-globe.js and
  // bakeEquirectTexture() above. clearRect, not an opaque fillRect, or
  // this would hide the WebGL layer.
  ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);

  if (window.GlobeGL && window.GlobeGL.ready) {
    window.GlobeGL.setFrustum(canvas.clientWidth / 2, canvas.clientHeight / 2, r);
    window.GlobeGL.setRotation(rotX, rotY);
    // Subsolar drift is slow (~15°/hour) — recomputing the underlying
    // date/declination math every ~60s is indistinguishable from every
    // frame and far cheaper. But the light's DIRECTION relative to the
    // rotating mesh must be re-derived every frame (cheap — reuses
    // latLonToViewVec, the same rotation-aware function pins use), or the
    // lit region drifts across geography as the globe spins instead of
    // staying pinned to the real subsolar point.
    if (!lastSunUpdateAt || performance.now() - lastSunUpdateAt > 60000) {
      cachedSubsolar = getSubsolarPoint();
      lastSunUpdateAt = performance.now();
    }
    if (cachedSubsolar) {
      const sv = latLonToViewVec(cachedSubsolar.lat, cachedSubsolar.lon);
      window.GlobeGL.setSunDirection(sv.x, sv.y, sv.z);
    }
    window.GlobeGL.render();
  }

  // Atmosphere halo — cosmetic, screen-space, sits at/outside the sphere's
  // silhouette edge, so it stays on the 2D overlay same as before.
  const atm = ctx.createRadialGradient(cx, cy, r * 0.92, cx, cy, r * 1.18);
  atm.addColorStop(0, 'rgba(78,158,255,0.07)');
  atm.addColorStop(1, 'rgba(78,158,255,0)');
  ctx.fillStyle = atm;
  ctx.beginPath(); ctx.arc(cx, cy, r * 1.18, 0, Math.PI * 2); ctx.fill();

  // Trade/transit routes (sea/air/rail — each gated on its own toggle inside)
  if (showTrade || showAir || showRail) drawAllRoutes();

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

  // Crisis density heat map, gated behind the showHeat toggle, then pins on top
  if (showHeat) drawCrisisHeatmap();
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
    (activeType === 'all' || c.type === activeType) &&
    (activeDomain === 'all' || getDomainForType(c.type) === activeDomain) &&
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

    const isUpcoming = c.status === 'upcoming';

    ctx.save();
    ctx.globalAlpha = fadeOpacity;
    ctx.shadowColor = col;
    ctx.shadowBlur  = isActive ? 22 : isHovered ? 14 : 8;

    if (isUpcoming) {
      // Scheduled-but-not-yet-happened events (elections, referendums) read
      // as "known in advance" rather than "detected" — a dashed outline
      // ring with a small solid centre dot, instead of the full glow-filled
      // circle used for reactive crises.
      ctx.fillStyle = col;
      ctx.beginPath(); ctx.arc(sx, sy, r2 * 0.35, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur  = 0;

      ctx.strokeStyle = col;
      ctx.lineWidth   = 1.5;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.arc(sx, sy, r2, 0, Math.PI * 2); ctx.stroke();
      ctx.setLineDash([]);
    } else {
      ctx.fillStyle   = col;
      ctx.beginPath(); ctx.arc(sx, sy, r2, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur  = 0;

      ctx.strokeStyle = 'rgba(255,255,255,0.85)';
      ctx.lineWidth   = 1.5;
      ctx.stroke();
    }

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

// TRUE density heat map: crisis contributions accumulate additively
// ('lighter' blending) into an intensity field, so overlapping/clustered
// crises compound into hotter zones — unlike the old drawHeatmapOverlay(),
// which colored each crisis independently with no interaction between
// nearby crises. Two-pass: (1) accumulate grayscale intensity into a
// DOWNSAMPLED offscreen buffer (perf: this is screen-space and must
// re-run every frame during rotation, unlike the WebGL sphere's
// once-baked texture — downsampling avoids a full-res per-pixel readback
// every frame), (2) colorize that buffer's pixels in-place through the
// heat ramp, then upscale-composite onto the sphere with drawImage
// (cheap, GPU-accelerated; the upscale's implicit softening is
// desirable here, not a quality loss, since the content is already
// blurred and low-frequency).
const HEAT_DOWNSAMPLE = 0.4; // buffer edge = 0.4 * (2r)
function drawCrisisHeatmap() {
  const cx = CX(), cy = CY(), r = R();

  const filteredCrises = filterByDateRange(CRISES, currentYear).filter(c => {
    return (activeType === 'all' || c.type === activeType) &&
      (activeDomain === 'all' || getDomainForType(c.type) === activeDomain) &&
      (c.location_confidence ?? 70) >= 75;
  });
  if (filteredCrises.length === 0) return;

  // Buffer covers the sphere's 2r x 2r bounding box, downsampled.
  const bufSize = Math.max(1, Math.round(2 * r * HEAT_DOWNSAMPLE));
  const scale = bufSize / (2 * r); // CSS-px screen space -> buffer-local space

  const off = document.createElement('canvas');
  off.width = bufSize;
  off.height = bufSize;
  // willReadFrequently: this buffer is always read back via getImageData
  // below — without this hint, a freshly-created canvas defaults to a
  // GPU-backed surface and that readback forces an expensive GPU->CPU
  // sync (measured ~19ms on a fresh 252x252 canvas vs ~2ms with the hint,
  // i.e. the dominant cost of this whole function without it).
  const offCtx = off.getContext('2d', { willReadFrequently: true });

  // Pass 1: additive accumulation of soft weight blobs. No ctx.filter
  // blur here — measured cost: applying a CSS blur filter during drawing
  // forces this canvas onto a much more expensive path for the
  // getImageData readback below (~15ms vs ~1ms for the same draws
  // without it, even with willReadFrequently set — the dominant cost of
  // this whole function). Softness instead comes from the gradient's own
  // multi-stop falloff plus the implicit smoothing of upscaling this
  // downsampled buffer back to full size in the final composite.
  offCtx.globalCompositeOperation = 'lighter';

  const spreadR = r * 0.22 * scale; // fixed-ish geographic spread, not severity-scaled

  filteredCrises.forEach(crisis => {
    const p = project(crisis.lat, crisis.lon);
    if (p.z < 0.04) return;

    // Screen space (cx-r .. cx+r) -> buffer-local (0 .. bufSize)
    const bx = (p.sx - (cx - r)) * scale;
    const by = (p.sy - (cy - r)) * scale;

    const severity = (crisis.severity || 50) / 100;
    // Kept well under 1.0 even at max severity (0.18-0.50 range) so a
    // SINGLE crisis never saturates the accumulation buffer's alpha —
    // otherwise 'lighter' blending has no headroom left to show that a
    // cluster of crises is hotter than any one of them alone, which
    // defeats the entire point of a density heat map. (Verified: with
    // the earlier 0.25-0.80 range plus a 1.6x post-boost below, one
    // severity-90 crisis alone already hit the 255 alpha ceiling.)
    const peakAlpha = 0.18 + severity * 0.32;

    const grad = offCtx.createRadialGradient(bx, by, 0, bx, by, spreadR);
    grad.addColorStop(0,   `rgba(255,255,255,${peakAlpha})`);
    grad.addColorStop(0.5, `rgba(255,255,255,${peakAlpha * 0.35})`);
    grad.addColorStop(1,   'rgba(255,255,255,0)');

    offCtx.fillStyle = grad;
    offCtx.beginPath();
    offCtx.arc(bx, by, spreadR, 0, Math.PI * 2);
    offCtx.fill();
  });

  offCtx.globalCompositeOperation = 'source-over';

  // Pass 2: colorize accumulated grayscale intensity through the heat ramp.
  const imgData = offCtx.getImageData(0, 0, bufSize, bufSize);
  const data = imgData.data;
  const rgb = [0, 0, 0];
  for (let i = 0; i < data.length; i += 4) {
    const intensity = data[i + 3] / 255; // accumulated alpha = accumulated density
    if (intensity <= 0.003) continue;
    heatRampColor(intensity, rgb);
    data[i]     = rgb[0];
    data[i + 1] = rgb[1];
    data[i + 2] = rgb[2];
    // Deliberately NO extra boost multiplier here (unlike an earlier
    // version that used *1.6): that boost was applied per-pixel BEFORE
    // compositing, so it saturated a single crisis's own alpha to the
    // 255 ceiling just as easily as a whole cluster's, erasing the
    // density signal this function exists to show. Overall visibility
    // instead comes from `baseAlpha` below, a single multiplier applied
    // uniformly at composite time — it makes the whole layer more or
    // less visible without disturbing the RELATIVE intensity differences
    // between sparse and dense areas that a boost baked in here would.
    data[i + 3] = Math.round(intensity * 255);
  }
  offCtx.putImageData(imgData, 0, 0);

  // Zoom-aware fade so pins stay readable when zoomed in — punchier
  // baseline (0.85 max) than the old drawHeatmapOverlay's 0.35 cap,
  // since "too subtle" was the explicit complaint. Safe to push higher
  // here specifically because peakAlpha/no-boost above now leave real
  // headroom in the 0-255 range for density to show through — this
  // baseAlpha is a uniform final multiplier, not a per-pixel one.
  const baseAlpha = Math.max(0.1, 0.85 - (zoom - 0.5) * 0.28);

  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.clip();
  ctx.globalAlpha = baseAlpha;
  ctx.drawImage(off, 0, 0, bufSize, bufSize, cx - r, cy - r, 2 * r, 2 * r);
  ctx.globalAlpha = 1;
  ctx.restore();
}

// ════════════════════════════════════════════════════════════
// UI: SELECTION & PANELS
// ════════════════════════════════════════════════════════════

function selectCrisis(crisis) {
  setPanelMode('crisis');
  selected = crisis;
  document.getElementById('colRight').classList.add('open');
  updateAllPanels();
  updateEventsList();
}

// Route selection — parallel to selectCrisis() but for a sea/air/rail route
// clicked on the globe. Kept fully separate from selectCrisis/
// updateAllPanels rather than branching those on type: `selected` and
// updateAllPanels() assume a Crisis shape (severity, stakeholders, domains,
// …) throughout, so a route gets its own state and its own panel content
// instead. The two share the same #colRight container/open-close mechanics
// and swap which content is visible via setPanelMode() — selecting one
// replaces the other, matching how selecting a different crisis already
// replaces whatever crisis was previously shown.
let selectedRoute = null;

function setPanelMode(mode) { // 'crisis' | 'route'
  const tabBar = document.getElementById('tabBar');
  if (tabBar) tabBar.style.display = mode === 'crisis' ? 'flex' : 'none';
  // Clearing the inline style (rather than setting 'flex') lets the
  // existing .tab-content/.tab-content.active CSS rules resume deciding
  // which single tab is visible, exactly as they do today.
  document.querySelectorAll('.tab-content').forEach(el => {
    el.style.display = mode === 'crisis' ? '' : 'none';
  });
  const routePanel = document.getElementById('routeInfoPanel');
  if (routePanel) routePanel.style.display = mode === 'route' ? 'flex' : 'none';
}

function selectRoute(route) {
  if (!route) return;
  setPanelMode('route');
  selectedRoute = route;
  document.getElementById('colRight').classList.add('open');
  updateRoutePanel(route);
}

function updateRoutePanel(route) {
  const risk = routeRiskLevel(route.waypoints);
  const riskColor = ROUTE_RISK_COLORS[risk];

  const modeBadge = document.getElementById('ri-mode-badge');
  const modeMeta = { sea: ['🚢 Sea', '#4e9eff'], air: ['✈️ Air', '#b94eff'], rail: ['🚂 Rail', '#ff8833'] }[route.mode] || [route.mode, '#888'];
  modeBadge.textContent = modeMeta[0];
  modeBadge.style.background = modeMeta[1] + '33';
  modeBadge.style.color = modeMeta[1];
  modeBadge.style.border = `1px solid ${modeMeta[1]}55`;

  const riskBadge = document.getElementById('ri-risk-badge');
  riskBadge.textContent = `${ROUTE_RISK_LABELS[risk]} risk`;
  riskBadge.style.background = riskColor + '18';
  riskBadge.style.borderColor = riskColor + '44';
  riskBadge.style.color = riskColor;

  const importanceBadge = document.getElementById('ri-importance-badge');
  const importanceScore = route.importanceScore ?? route.vol * 30;
  const importanceCol = importanceColor(importanceScore);
  importanceBadge.textContent = `${importanceScore}/100 importance`;
  importanceBadge.style.background = importanceCol + '18';
  importanceBadge.style.borderColor = importanceCol + '44';
  importanceBadge.style.color = importanceCol;

  document.getElementById('ri-title').textContent = route.label;
  document.getElementById('ri-volume').textContent = TRADE_VOL_LABEL[route.vol] || '—';
  document.getElementById('ri-importance').textContent = route.importance || 'No data available.';
  document.getElementById('ri-cargo').textContent = route.cargo || 'No data available.';
  document.getElementById('ri-ownership').textContent = route.ownership || 'No data available.';
}

// Heuristic forecasts carry a real relative signal (system reads this as
// higher/lower risk) but no real statistical precision — so the UI shows a
// qualitative band, not the underlying number, even though the bar width
// still tracks it for a quick visual comparison.
function probBand(v) {
  if (v >= 60) return 'High';
  if (v >= 30) return 'Med';
  return 'Low';
}

function updateAllPanels() {
  if (!selected) return;
  const c = selected;

  document.getElementById('panelTitleText').textContent = c.title;

  // ── Forecast ──
  document.getElementById('forecastEmpty').style.display = 'none';
  const fc = document.getElementById('forecastContent');
  fc.style.display = 'flex';
  fc.innerHTML = (c.forecasts || []).map(f => `
    <div class="forecast-item">
      <div class="forecast-q">${escapeHtml(f.q)}</div>
      <div class="prob-bars">
        <div class="prob-row">
          <span class="prob-lbl">Unlikely</span>
          <div class="prob-track"><div class="prob-fill" style="width:${f.low}%;background:#3dffaa"></div></div>
          <span class="prob-pct" style="color:#3dffaa">${probBand(f.low)}</span>
        </div>
        <div class="prob-row">
          <span class="prob-lbl">Possible</span>
          <div class="prob-track"><div class="prob-fill" style="width:${f.mid}%;background:#ffd93d"></div></div>
          <span class="prob-pct" style="color:#ffd93d">${probBand(f.mid)}</span>
        </div>
        <div class="prob-row">
          <span class="prob-lbl">Likely</span>
          <div class="prob-track"><div class="prob-fill" style="width:${f.high}%;background:#ff3b3b"></div></div>
          <span class="prob-pct" style="color:#ff3b3b">${probBand(f.high)}</span>
        </div>
      </div>
    </div>
  `).join('');
}

// ════════════════════════════════════════════════════════════
// UI: FILTERS
// ════════════════════════════════════════════════════════════

let activeDomain = 'all';
let activeType   = 'all';

function selectDomain(key) {
  activeDomain = key;
  document.querySelectorAll('#domainChips .chip').forEach(c => c.classList.toggle('on', c.dataset.key === key));
  updateEventsList();
}
function selectType(key) {
  activeType = key;
  document.querySelectorAll('#typeChips .chip').forEach(c => c.classList.toggle('on', c.dataset.key === key));
  updateEventsList();
}

function buildChips() {
  const dc = document.getElementById('domainChips');
  const allDomainChip = document.createElement('div');
  allDomainChip.className = 'chip on';
  allDomainChip.dataset.key = 'all';
  allDomainChip.textContent = 'All';
  allDomainChip.addEventListener('click', () => selectDomain('all'));
  dc.appendChild(allDomainChip);

  Object.entries(DOMAINS).forEach(([key, d]) => {
    const chip = document.createElement('div');
    chip.className = 'chip';
    chip.dataset.key = key;
    chip.style.color = d.color;
    chip.style.borderColor = d.color + '66';
    chip.style.background  = d.color + '18';
    chip.innerHTML = `${d.icon} ${d.name}`;
    chip.addEventListener('click', () => selectDomain(key));
    dc.appendChild(chip);
  });

  const tc = document.getElementById('typeChips');
  const allTypeChip = document.createElement('div');
  allTypeChip.className = 'chip on';
  allTypeChip.dataset.key = 'all';
  allTypeChip.textContent = 'All';
  allTypeChip.addEventListener('click', () => selectType('all'));
  tc.appendChild(allTypeChip);

  Object.entries(TYPE_META).forEach(([key, t]) => {
    const chip = document.createElement('div');
    chip.className = 'chip';
    chip.dataset.key = key;
    chip.style.color = t.color;
    chip.style.borderColor = t.color + '66';
    chip.style.background  = t.color + '18';
    chip.textContent = t.name;
    chip.addEventListener('click', () => selectType(key));
    tc.appendChild(chip);
  });
}

// Shared by updateEventsList() (the sidebar list) and the Export control
// (app.js's exportCrisisData) so the on-screen count and an exported file
// are provably describing the same set — this used to be duplicated inline
// inside updateEventsList() only.
function getFilteredCrises() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const crisisesInYear = filterByDateRange(CRISES, currentYear);

  return crisisesInYear
    .filter(c => {
      // Dated events (elections, referendums, summits — 'upcoming' before
      // they happen, 'resolved' once they have) live in the Calendar tab
      // instead — otherwise, on a database with no other crises yet, this
      // "ongoing crises" list would show nothing but those.
      if (c.status === 'upcoming' || c.status === 'resolved') return false;
      const typeMatch = activeType === 'all' || c.type === activeType;
      const domainMatch = activeDomain === 'all' || getDomainForType(c.type) === activeDomain;
      const countryMatch = !countryFilter || c.country === countryFilter;
      return typeMatch && domainMatch && countryMatch;
    })
    .filter(c => c.title.toLowerCase().includes(q) || c.country.toLowerCase().includes(q));
}

function updateEventsList() {
  const list = document.getElementById('eventsList');
  list.innerHTML = '';

  const filtered = getFilteredCrises();

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
      <button class="bookmark-btn ${bookmarks.has(crisis.id) ? 'on' : ''}" data-bid="${crisis.id}" title="Bookmark">★</button>
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

    // Re-render cached data now that this tab is actually visible (each
    // panel's data was already fetched once in selectCrisis — this just
    // repaints it, cheap and idempotent).
    if (id === 'briefing' && selected) updateBriefingPanel(selected.briefing);
    if (id === 'history' && selected) updateHistoryPanel(selected.history);
    if (id === 'news' && selected) updateNewsPanel(selected.news);
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
    if (id === 'calendar') renderCalendar();
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

  // Route hover tooltip (sea/air/rail — whichever layers are toggled on)
  if ((showTrade || showAir || showRail) && tradeRouteScreenPts.length > 0) {
    const tip = document.getElementById('tradeTooltip');
    let closest = null, closestD = Infinity;
    for (const pt of tradeRouteScreenPts) {
      const d = Math.hypot(mx - pt.sx, my - pt.sy);
      if (d < closestD) { closestD = d; closest = pt; }
    }
    if (closest && closestD < 40) {
      const route = ROUTES_BY_ID.get(closest.id);
      const modeIcon = { sea: '🚢', air: '✈️', rail: '🚂' }[closest.mode] || '';
      const importanceScore = closest.importanceScore ?? closest.vol * 30;
      const statColor = routeColorMode === 'importance' ? importanceColor(importanceScore) : ROUTE_RISK_COLORS[closest.risk];
      const statLabel = routeColorMode === 'importance' ? `${importanceScore}/100 importance` : `${ROUTE_RISK_LABELS[closest.risk]}`;
      // Same great-circle sampling as routeRiskLevel() — see its comment
      // for why naive lat/lon-linear midpoints are wrong, generalized here
      // the same way to sample along the whole waypoint chain, not just
      // two far-apart endpoints.
      const routeSamples = [];
      for (let seg = 0; seg < route.waypoints.length - 1; seg++) {
        const rv1 = latLonToVec(route.waypoints[seg][0], route.waypoints[seg][1]);
        const rv2 = latLonToVec(route.waypoints[seg + 1][0], route.waypoints[seg + 1][1]);
        [0, 0.5, 1].forEach(t => routeSamples.push(vecToLatLon(slerpVec(rv1, rv2, t))));
      }
      const threats = CRISES
        .filter(c => routeSamples.some(([sl,so]) => geoDistKm(c.lat||0, c.lon||0, sl, so) < 1650))  // ~15° at the equator
        .sort((a, b) => b.severity - a.severity)
        .slice(0, 3);
      const threatHtml = threats.length
        ? threats.map(c => `<div style="color:${c.severity>80?'#ff3b3b':c.severity>60?'#ff8833':'#ffd93d'};margin-top:3px">⚠ ${escapeHtml(c.title)} (${escapeHtml(c.country)})</div>`).join('')
        : '<div style="color:var(--dim);margin-top:3px">No active threats nearby</div>';
      tip.innerHTML = `
        <div style="font-weight:700;color:#ffd93d;margin-bottom:4px">${modeIcon} ${closest.label}</div>
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
          <span style="color:${statColor};font-weight:700">${statLabel}</span>
          <span style="color:var(--dim)">·</span>
          <span style="color:var(--dim)">${TRADE_VOL_LABEL[closest.vol]}</span>
        </div>
        <div style="font-size:9px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin-top:4px">Nearby threats</div>
        ${threatHtml}
        <div style="font-size:9px;color:var(--dim);margin-top:6px">Click for full route details</div>
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
    if (activeType !== 'all' && crisis.type !== activeType) continue;
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

  // Check route clicks (sea/air/rail — whichever layers are toggled on),
  // same 40px threshold and nearest-point search the hover tooltip uses.
  if (showTrade || showAir || showRail) {
    let closest = null, closestD = Infinity;
    for (const pt of tradeRouteScreenPts) {
      const d = Math.hypot(emx - pt.sx, emy - pt.sy);
      if (d < closestD) { closestD = d; closest = pt; }
    }
    if (closest && closestD < 40) {
      selectRoute(ROUTES_BY_ID.get(closest.id));
      return;
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

document.getElementById('resetBtn').addEventListener('click', () => { rotX = DEFAULT_ROTX; rotY = DEFAULT_ROTY; zoom = DEFAULT_ZOOM; });

// Idle mode: hides all HUD, resets the globe to its default view, and
// auto-rotates indefinitely — a "screensaver" state. The button itself
// lives outside every hidden container (position:fixed on its own) so it
// stays visible and clickable both to enter and to exit idle mode.
let idleMode = false;
const IDLE_HIDE_SELECTORS = ['#colLeft', '.globe-controls', '#timelinePanel', '#arcLegend', '#relPanel', '#breakingAlert', '#countryTooltip', '#tradeTooltip'];
document.getElementById('idleModeBtn').addEventListener('click', function() {
  idleMode = !idleMode;
  this.classList.toggle('active', idleMode);
  if (idleMode) {
    IDLE_HIDE_SELECTORS.forEach(sel => {
      const el = document.querySelector(sel);
      if (el) { el.dataset._prevDisplay = el.style.display; el.style.display = 'none'; }
    });
    document.getElementById('colRight').classList.remove('open');
    rotX = DEFAULT_ROTX; rotY = DEFAULT_ROTY; zoom = DEFAULT_ZOOM;
  } else {
    IDLE_HIDE_SELECTORS.forEach(sel => {
      const el = document.querySelector(sel);
      if (el) el.style.display = el.dataset._prevDisplay || '';
    });
  }
});
document.getElementById('arcBtn').addEventListener('click', function() {
  showArcs = !showArcs;
  this.classList.toggle('active', showArcs);
  document.getElementById('arcLegend').style.display = showArcs ? 'block' : 'none';
});
document.getElementById('heatBtn').addEventListener('click', function() {
  showHeat = !showHeat;
  this.classList.toggle('active', showHeat);
});
document.getElementById('cascBtn').addEventListener('click', async function() {
  if (!selected) return;
  showCasc = !showCasc;
  this.classList.toggle('active', showCasc);
  // Cascade arcs (drawn in the globe loop — see `if (showCasc && selected)`
  // above) need selected.cascade, which used to be fetched by the now-
  // removed Cascade tab's "Simulate Escalation" button. Fetch it here on
  // first activation instead, so this toggle still works standalone; once
  // fetched it's cached on the crisis object like every other lazy-loaded
  // field, so re-toggling doesn't refetch.
  if (showCasc && !selected.cascade) {
    try {
      const API_BASE = window.GEOINTEL_API_BASE ||
        (window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api');
      const response = await fetch(`${API_BASE}/crises/${selected.id}/cascade?depth=2&threshold=40`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      selected.cascade = await response.json();
    } catch (error) {
      console.error('Cascade simulation error:', error);
      showCasc = false;
      this.classList.remove('active');
    }
  }
});
document.getElementById('routeColorBtn').addEventListener('click', function() {
  routeColorMode = routeColorMode === 'risk' ? 'importance' : 'risk';
  this.classList.toggle('active', routeColorMode === 'importance');
});
document.getElementById('tradeBtn').addEventListener('click', function() {
  showTrade = !showTrade;
  this.classList.toggle('active', showTrade);
});
document.getElementById('planeBtn').addEventListener('click', function() {
  showAir = !showAir;
  this.classList.toggle('active', showAir);
});
const timelinePanel = document.getElementById('timelinePanel');
document.getElementById('timelineBtn').addEventListener('click', function() {
  const showing = timelinePanel.style.display === 'none';
  timelinePanel.style.display = showing ? '' : 'none';
  this.classList.toggle('active', showing);
});
document.getElementById('trainBtn').addEventListener('click', function() {
  showRail = !showRail;
  this.classList.toggle('active', showRail);
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

// Share — deep link. Shared by the copy-link button and the social-share
// button below, so both always build the exact same URL.
function buildShareUrl(crisis) {
  const url = new URL(window.location.href);
  url.searchParams.set('crisis', crisis.id);
  return url.toString();
}

document.getElementById('shareBtn').addEventListener('click', () => {
  if (!selected) return;
  navigator.clipboard.writeText(buildShareUrl(selected)).then(() => {
    const btn = document.getElementById('shareBtn');
    btn.textContent = '✓';
    btn.style.color = '#3dffaa';
    setTimeout(() => { btn.textContent = '🔗'; btn.style.color = 'var(--accent)'; }, 1800);
  });
});

// Social share — the Web Share API gives a native share sheet (all
// installed apps) where supported, mainly mobile browsers; everywhere else,
// fall back to a pre-filled X/Twitter share-intent link in a new tab.
document.getElementById('shareSocialBtn').addEventListener('click', () => {
  if (!selected) return;
  const url = buildShareUrl(selected);
  const text = `${selected.title} — via GeoIntel`;

  if (navigator.share) {
    navigator.share({ title: selected.title, text, url }).catch(() => {});
    return;
  }
  const intentUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`;
  window.open(intentUrl, '_blank', 'noopener,noreferrer');
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
  // Crisis.id is always a real string (e.g. "sample_kyiv", "acled_12345") —
  // parseInt() used to run on it here, which returns NaN for every real id,
  // silently no-opping this entire function for every possible share link.
  const id = new URLSearchParams(window.location.search).get('crisis');
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
    is_verified: raw.is_verified || false,
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
  const id = crisis.id;
  if (bookmarks.has(id)) {
    bookmarks.delete(id);
  } else {
    bookmarks.add(id);
  }
  localStorage.setItem('geointel_bookmarks', JSON.stringify([...bookmarks]));
  updateWatchlist();
  updateEventsList(); // refresh stars in crisis list
}

function updateWatchlist() {
  const list = document.getElementById('watchlistItems');
  const countEl = document.getElementById('watchlistCount');
  if (!list) return;
  list.innerHTML = '';
  const saved = CRISES.filter(c => bookmarks.has(c.id));
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

// Calendar: a chronological agenda of "vital events" with a known date —
// upcoming ones (elections, referendums, summits: status='upcoming' with a
// real date_scheduled) grouped above past/recorded ones (everything else,
// by date/date_start). Independent of the Domains/Types chip filters, same
// as the Watchlist tab — this is a browse view, not a re-filtered subset.
function renderCalendar() {
  const list = document.getElementById('calendarList');
  const countEl = document.getElementById('calendarCount');
  if (!list) return;
  list.innerHTML = '';

  const upcoming = CRISES.filter(c => c.status === 'upcoming' && c.date_scheduled)
    .sort((a, b) => new Date(a.date_scheduled) - new Date(b.date_scheduled));
  // Only *concluded* dated events (status flipped to 'resolved' once they
  // happen) — not every non-upcoming crisis, which would otherwise sweep
  // in genuinely ongoing reactive crises (status 'active') too and
  // duplicate the Crises tab under a misleading "Past" heading.
  const past = CRISES.filter(c => c.status === 'resolved' && (c.date || c.date_start))
    .sort((a, b) => new Date(b.date || b.date_start) - new Date(a.date || a.date_start));

  if (countEl) countEl.textContent = `${upcoming.length} upcoming`;

  if (upcoming.length === 0 && past.length === 0) {
    list.innerHTML = '<div class="watchlist-empty"><div class="wi">📅</div><div>No dated events yet</div></div>';
    return;
  }

  const rowDate = (c, dateField) => new Date(dateField === 'date_scheduled' ? c.date_scheduled : (c.date || c.date_start));

  const renderRow = (c, dateField) => {
    const tm = TYPE_META[c.type] || {};
    const d = rowDate(c, dateField);
    const el = document.createElement('div');
    el.className = 'evt-item' + (c.id === selected?.id ? ' sel' : '');
    el.innerHTML = `
      <div style="flex:1;min-width:0;">
        <div class="evt-name">${escapeHtml(c.title)}</div>
        <div class="evt-sub">
          <span style="color:${tm.color || '#888'}">${tm.name || ''}</span>
          · ${escapeHtml(c.country)} · ${isNaN(d) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
        </div>
      </div>
    `;
    el.addEventListener('click', () => selectCrisis(c));
    return el;
  };

  const renderGroup = (heading, items, dateField) => {
    if (!items.length) return;
    const groupHdr = document.createElement('div');
    groupHdr.className = 'section-lbl';
    groupHdr.style.cssText = 'margin:8px 0 4px;padding:0 10px;';
    groupHdr.textContent = heading;
    list.appendChild(groupHdr);

    let lastMonthKey = null;
    items.forEach(c => {
      const d = rowDate(c, dateField);
      if (!isNaN(d)) {
        const monthKey = `${d.getFullYear()}-${d.getMonth()}`;
        if (monthKey !== lastMonthKey) {
          const hdr = document.createElement('div');
          hdr.style.cssText = 'font-size:9px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;padding:6px 10px 2px;';
          hdr.textContent = d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
          list.appendChild(hdr);
          lastMonthKey = monthKey;
        }
      }
      list.appendChild(renderRow(c, dateField));
    });
  };

  renderGroup('Upcoming', upcoming, 'date_scheduled');
  renderGroup('Past', past, 'date');
}

document.getElementById('clearWatchlist').addEventListener('click', () => {
  bookmarks.clear();
  localStorage.setItem('geointel_bookmarks', JSON.stringify([]));
  updateWatchlist();
  updateEventsList();
});

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  // Don't fire when typing in an input
  if (['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)) return;
  switch (e.key.toLowerCase()) {
    case 'f': toggleFullscreen(); break;
    case 'h': document.getElementById('heatBtn').click(); break;
    case 'r': document.getElementById('arcBtn').click(); break;
    case 'c': document.getElementById('routeColorBtn').click(); break;
    case 't': document.getElementById('timelineBtn').click(); break;
    case 'i': document.getElementById('idleModeBtn').click(); break;
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

const IDLE_ROTATE_SPEED = 0.0012; // rad/frame, slow continuous drift while idle mode is active
function loop() {
  decayStaleDragVelocity();
  applyInertia();
  if (idleMode && !drag) rotY += IDLE_ROTATE_SPEED;
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
        is_verified: c.is_verified || false,
        status: c.status || 'active',
        date_scheduled: c.date_scheduled || null,
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
        // These are real WorldBank-derived stats (economic_power) or
        // genuinely unrated (the other three have no real data source) —
        // `?? null` preserves that distinction instead of `|| 50` silently
        // turning "not rated" back into a fabricated middle-of-the-road number.
        military_power: a.military ?? null,
        economic_power: a.economic ?? null,
        political_influence: a.political ?? null,
        technological_capability: a.technology ?? null,
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
      // Anchored inside .globe-col (which is `position:relative`), not
      // document.body — a viewport-fixed top-right banner sat directly on
      // top of the crisis panel's own tab row, since .col-right also claims
      // the top-right corner (absolutely, on desktop; in normal flow right
      // below the globe, on mobile). .globe-controls already owns
      // top-right of this container, so top-LEFT is the one corner that's
      // clear of both the panel and the controls at every breakpoint.
      alertEl.style.cssText = 'position:absolute;top:10px;left:10px;background:#ff3b3b33;border:1px solid #ff3b3b66;color:#ff8888;padding:10px 15px;border-radius:6px;z-index:50;font-size:12px;max-width:calc(100% - 20px);width:300px;';
      document.querySelector('.globe-col').appendChild(alertEl);
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

async function loadBriefing(id) { try { const r = await fetch(`${(window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api')}/crises/${id}/briefing`); return r.ok ? await r.json() : null; } catch (e) { return null; } }
async function loadDeepHistory(id) { try { const r = await fetch(`${(window.location.hostname === 'localhost' ? 'http://localhost:5000/api' : '/api')}/crises/${id}/history`); return r.ok ? await r.json() : null; } catch (e) { return null; } }

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
    // Source citations render as markdown links, e.g. "[Reuters — Title](url)"
    // in the ## Sources section. escapeHtml already ran, so both the link
    // text and URL are entity-escaped — safe to drop straight into the
    // anchor. Restricted to http(s) so a malformed source URL can't smuggle
    // in a javascript: scheme. Bare bracket citations like "[3]" in the body
    // text have no following "(...)" and are left untouched (intentional —
    // they're footnote markers, not links).
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
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

// Trust-signal badges shown above every tab (reliability, citation count,
// human-verified) — these are all genuinely computed from real stored data
// (calculate_source_reliability, the briefing's numbered source list,
// Crisis.is_verified), unlike the fabricated metrics this redesign removed.
const RELIABILITY_COLORS = {
  verified:     '#3dffaa',
  corroborated: '#4e9eff',
  reported:     '#ffd93d',
  unverified:   '#ff8a3d',
  unknown:      'var(--dim)',
};

function updatePanelBadges(crisis) {
  const el = document.getElementById('panelBadges');
  if (!el) return;
  const badges = [];

  const rel = crisis.reliability;
  if (rel && rel.reliability && rel.reliability !== 'unknown') {
    const color = RELIABILITY_COLORS[rel.reliability] || 'var(--accent)';
    badges.push(`<span class="conf-badge" style="padding:3px 9px;font-size:10px;color:${color};border-color:${color}40;background:${color}1f">${escapeHtml(rel.reliability)} (${rel.source_count} source${rel.source_count === 1 ? '' : 's'})</span>`);
  }

  const sourceCount = crisis.briefing && Array.isArray(crisis.briefing.sources) ? crisis.briefing.sources.length : 0;
  if (sourceCount > 0) {
    badges.push(`<span class="conf-badge" style="padding:3px 9px;font-size:10px">${sourceCount} cited source${sourceCount === 1 ? '' : 's'}</span>`);
  }

  if (crisis.is_verified) {
    badges.push(`<span class="conf-badge" style="padding:3px 9px;font-size:10px;color:#3dffaa;border-color:#3dffaa40;background:#3dffaa1f">✓ Verified</span>`);
  }

  el.innerHTML = badges.join('');
}

// Every briefing/history response carries a real `model` field distinguishing
// actual Claude generation from the rule-based static fallback (which fires
// whenever ANTHROPIC_API_KEY isn't configured) — surface that distinction
// directly rather than letting static content masquerade as AI analysis.
function setGenBadge(el, model) {
  if (!el) return;
  if (!model) { el.style.display = 'none'; return; }
  const isAI = model.startsWith('claude-');
  el.textContent = isAI ? '🤖 AI-generated' : '📋 Static (rule-based)';
  el.style.color = isAI ? '#4e9eff' : 'var(--dim)';
  el.style.borderColor = isAI ? '#4e9eff40' : 'rgba(255,255,255,.15)';
  el.style.background = isAI ? '#4e9eff1f' : 'rgba(255,255,255,.05)';
  el.style.display = 'block';
}

function updateBriefingPanel(br) {
  const c = document.getElementById('briefingContent'), e = document.getElementById('briefingEmpty');
  const loadingEl = document.getElementById('briefing-loading');
  const textEl    = document.getElementById('briefing-text');
  const imgWrap   = document.getElementById('briefing-image-wrap');
  const imgEl     = document.getElementById('briefing-image');
  const genBadge  = document.getElementById('briefing-genbadge');

  if (!br) {
    c.style.display = 'none';
    loadingEl.style.display = 'none'; textEl.style.display = 'none';
    imgWrap.style.display = 'none';
    genBadge.style.display = 'none';
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

  setGenBadge(genBadge, br.model);

  // Render markdown-formatted briefing text
  renderMarkdown(textEl, br.briefing);
}

function updateHistoryPanel(hist) {
  const c = document.getElementById('historyContent'), e = document.getElementById('historyEmpty');
  const loadingEl = document.getElementById('history-loading');
  const textEl    = document.getElementById('history-text');
  const analogyEl = document.getElementById('history-analogy');
  const genBadge  = document.getElementById('history-genbadge');

  if (!hist) {
    c.style.display = 'none';
    loadingEl.style.display = 'none'; textEl.style.display = 'none';
    analogyEl.style.display = 'none';
    genBadge.style.display = 'none';
    if (selected) {
      showPanelUnavailable(e, 'Deep historical analysis unavailable for this crisis<br>(check ANTHROPIC_API_KEY on the backend, or try again shortly)');
    } else {
      resetPanelEmpty(e);
      e.style.display = 'flex';
    }
    return;
  }
  resetPanelEmpty(e);
  e.style.display = 'none'; c.style.display = 'flex';
  loadingEl.style.display = 'none'; textEl.style.display = 'block';

  setGenBadge(genBadge, hist.model);

  // The analogy's "strength" is a qualitative word (strong/moderate/loose)
  // from the model, never a numeric match percentage — no real precedent
  // database backs a precise figure, so this stays a fast visual anchor for
  // a comparison already stated in the rendered prose, not a new claim.
  if (hist.analogy && hist.analogy.match && hist.analogy.strength) {
    analogyEl.textContent = `Strongest historical parallel: ${hist.analogy.match} (${hist.analogy.strength})`;
    analogyEl.style.display = 'block';
  } else {
    analogyEl.style.display = 'none';
  }

  renderMarkdown(textEl, hist.history);
}

// Per-crisis news articles — the fetch (crisis.news, via GeoIntelAPI.getNews
// in selectCrisis below) already existed; this just renders it, matching the
// same pattern as updateBriefingPanel/updateHistoryPanel above.
function updateNewsPanel(articles) {
  const c = document.getElementById('newsContent'), e = document.getElementById('newsEmpty');

  if (!articles) {
    c.style.display = 'none';
    if (selected) {
      showPanelUnavailable(e, 'News articles unavailable for this crisis<br>(try again shortly)');
    } else {
      resetPanelEmpty(e);
      e.style.display = 'flex';
    }
    return;
  }
  if (articles.length === 0) {
    c.style.display = 'none';
    showPanelUnavailable(e, 'No recent news articles found<br>for this crisis');
    return;
  }

  resetPanelEmpty(e);
  e.style.display = 'none';
  c.style.display = 'flex';

  c.innerHTML = articles.map(a => {
    // Two possible shapes reach here: real DB-backed articles use
    // published_at (snake_case, News.to_dict()); the synthetic fallback
    // generated when no real articles are indexed uses publishedAt
    // (camelCase, backend's _generate_contextual_news). Accept either.
    const rawDate = a.published_at || a.publishedAt;
    const dateStr = rawDate ? new Date(rawDate).toLocaleDateString() : '';
    const meta = [escapeHtml(a.source || 'Unknown source'), dateStr].filter(Boolean).join(' • ');
    const body = `
      <div style="font-weight:600;color:#e0eaff;font-size:11px;margin-bottom:3px;line-height:1.4">${escapeHtml(a.title || 'Untitled')}</div>
      <div style="color:var(--dim);font-size:9px">${meta}</div>`;
    const itemStyle = 'display:block;padding:8px;border:1px solid rgba(255,255,255,.1);border-radius:3px;background:rgba(255,255,255,.03);text-decoration:none;transition:background .2s;';
    // Only a clickable link for http(s) URLs — same scheme restriction
    // renderMarkdown() already applies to source citations, so a
    // malformed/untrusted URL can't smuggle a javascript: scheme.
    return /^https?:\/\//.test(a.url || '')
      ? `<a href="${escapeHtml(a.url)}" target="_blank" rel="noopener noreferrer" style="${itemStyle}" onmouseover="this.style.background='rgba(78,158,255,.1)'" onmouseout="this.style.background='rgba(255,255,255,.03)'">${body}</a>`
      : `<div style="${itemStyle}">${body}</div>`;
  }).join('');
}

// Enhanced selectCrisis with all new data
const originalSelectCrisis = selectCrisis;
selectCrisis = async function(crisis) {
  setPanelMode('crisis');
  selected = crisis;
  document.getElementById('colRight').classList.add('open');

  // These four lookups are independent — each is its own network round-trip
  // with no data dependency on the others. Awaiting them one at a time (as
  // this used to) means the total wait is their SUM; on higher-latency
  // connections (mobile/cellular especially, where 150-300ms per request
  // isn't unusual) that turned clicking a pin into a multi-second wait
  // before anything populated. Firing them concurrently drops that to
  // roughly the slowest single request.
  if (!crisis.briefing) document.getElementById('briefing-loading').style.display = 'block';
  if (!crisis.history) document.getElementById('history-loading').style.display = 'block';

  await Promise.all([
    (async () => {
      if (crisis.forecasts && crisis.forecasts.length > 0) return;
      try {
        const fr = await GeoIntelAPI.getForecasts(crisis.id);
        if (!fr.error && fr.forecasts) {
          crisis.forecasts = fr.forecasts.map(f => ({ q:f.q, low:f.low, mid:f.mid, high:f.high }));
        }
      } catch (e) {}
    })(),
    (async () => {
      if (crisis.news) return;
      try {
        const nr = await GeoIntelAPI.getNews({ crisis_id: crisis.id, days: 30, limit: 5 });
        if (!nr.error && nr.articles) { crisis.news = nr.articles; }
      } catch (e) {}
    })(),
    (async () => { if (!crisis.briefing) crisis.briefing = await loadBriefing(crisis.id); })(),
    (async () => { if (!crisis.history) crisis.history = await loadDeepHistory(crisis.id); })(),
    (async () => {
      if (crisis.reliability) return;
      try {
        const rr = await GeoIntelAPI.getReliability(crisis.id);
        if (!rr.error) { crisis.reliability = rr; }
      } catch (e) {}
    })(),
  ]);

  updateAllPanels();
  updateBriefingPanel(crisis.briefing);
  updateHistoryPanel(crisis.history);
  updateNewsPanel(crisis.news);
  updatePanelBadges(crisis);
  updateEventsList();
};

// ════════════════════════════════════════════════════════════
// INIT
// ════════════════════════════════════════════════════════════

// webgl-globe.js is loaded as an ES module (<script type="module">), which
// defers its execution until after the document has parsed — potentially
// AFTER this classic script has already run past this point. So: try the
// synchronous path first (module already loaded), and fall back to
// listening for its 'globegl-ready' event otherwise. See webgl-globe.js's
// top comment for the full reasoning.
function initWebGLGlobe() {
  const start = () => {
    window.GlobeGL.init(document.getElementById('glCanvas'));
    window.GlobeGL.resize(canvas.clientWidth, canvas.clientHeight, getCanvasDPR());
    if (topoFeaturesLow && topoMeshLow) bakeEquirectTexture(topoFeaturesLow, topoMeshLow);
  };
  if (window.GlobeGL) start();
  else window.addEventListener('globegl-ready', start, { once: true });
}

async function initApp() {
  initWebGLGlobe();
  buildChips();

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
      // First texture for the GPU sphere — a no-op if GlobeGL hasn't
      // finished loading yet (initWebGLGlobe's own 'globegl-ready'
      // listener bakes it then instead; whichever of the two happens
      // second is the one that actually succeeds).
      bakeEquirectTexture(topoFeaturesLow, topoMeshLow);
    })
    .catch(err => console.error('Map data error (low-res):', err));

  // Skip the high-detail mesh on mobile-sized screens entirely: it's a ~7x
  // larger download, its feature/mesh conversion is the most expensive
  // single operation in the app (~80k points), and it gets rebuilt into a
  // fresh offscreen bitmap on every settle — all real costs on hardware
  // that's typically slower than desktop to begin with, for detail that's
  // barely visible on a globe rendered at ~60vw/max 440px. Falling back to
  // the low-res mesh permanently is safe: getActiveTopo() and drawGlobe()
  // already treat topoFeaturesHigh as optional (`if (topoFeaturesHigh && …)`)
  // since it normally loads in asynchronously anyway.
  if (window.matchMedia('(max-width: 768px)').matches) {
    console.log('[Perf] Mobile-sized viewport detected — skipping high-detail (50m) map mesh');
  } else {
    fetch('countries-50m.json')
      .then(r => r.json())
      .then(data => {
        worldTopoHigh = data;
        const buildHighResCache = () => {
          topoFeaturesHigh = topojson.feature(worldTopoHigh, worldTopoHigh.objects.countries).features;
          topoMeshHigh     = topojson.mesh(worldTopoHigh, worldTopoHigh.objects.countries, (a, b) => a !== b);
          // Upgrade the GPU sphere's texture from the low-res bake to the
          // full 50m one — non-blocking, runs whenever this finishes.
          bakeEquirectTexture(topoFeaturesHigh, topoMeshHigh);
        };
        window.requestIdleCallback ? window.requestIdleCallback(buildHighResCache) : setTimeout(buildHighResCache, 0);
      })
      .catch(err => console.error('Map data error (high-res):', err));
  }
}

// Auto-refresh data every hour
setInterval(async () => {
  await loadRealData();
  updateEventsList();
  buildNewsFeed();
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
// EXPORT: BULK CRISIS DATA (CSV/JSON)
// ════════════════════════════════════════════════════════════

// Downloads the SAME set getFilteredCrises() shows on screen — the current
// type/domain/country filters are translated into the export endpoint's
// query params (min_severity and search text aren't sent server-side since
// this list doesn't apply them either; see getFilteredCrises()). Domain
// doesn't exist as a stored column, so an active domain filter is expressed
// as the comma-separated list of crisis types that belong to it (the
// backend's `type` param accepts a list — see GET /api/crises/export).
function exportCrisisData(format) {
  const options = { format };
  if (activeDomain !== 'all') {
    options.type = Object.keys(TYPE_META).filter(t => getDomainForType(t) === activeDomain).join(',');
  } else if (activeType !== 'all') {
    options.type = activeType;
  }
  if (countryFilter) options.country = countryFilter;

  const url = GeoIntelAPI.getExportUrl(options);
  const a = document.createElement('a');
  a.href = url;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

(() => {
  const btn = document.getElementById('exportDataBtn');
  const dropdown = document.getElementById('exportDataDropdown');
  if (!btn || !dropdown) return;

  btn.addEventListener('click', e => {
    e.stopPropagation();
    dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
  });
  dropdown.querySelectorAll('[data-export-format]').forEach(item => {
    item.addEventListener('click', () => {
      exportCrisisData(item.dataset.exportFormat);
      dropdown.style.display = 'none';
    });
  });
  document.addEventListener('click', e => {
    if (!dropdown.contains(e.target) && e.target !== btn) dropdown.style.display = 'none';
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

  const rel = c.reliability;
  el('pb-reliability').textContent = (rel && rel.reliability && rel.reliability !== 'unknown')
    ? `${rel.reliability} (${rel.source_count} source${rel.source_count === 1 ? '' : 's'})`
    : 'Not enough sources to assess';
  const genModel = c.briefing?.model;
  el('pb-genmethod').textContent = genModel
    ? (genModel.startsWith('claude-') ? 'AI-generated (Claude)' : 'Static (rule-based)')
    : 'Unknown';

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

  // Full AI-generated briefing when one has been generated — this is what
  // makes the export an extensive report instead of a terse summary.
  // renderMarkdown() is the same function the on-screen Brief tab uses, so
  // headings/bullets in the AI text render consistently in both places.
  // Falls back to the short analysis/impact fields (e.g. ANTHROPIC_API_KEY
  // not configured on the backend, so no briefing was ever generated).
  if (c.briefing?.briefing) {
    renderMarkdown(el('pb-briefing'), c.briefing.briefing);
  } else {
    const fallback = [c.analysis, c.impact].filter(Boolean).join('\n\n') || 'No briefing available for this crisis.';
    renderMarkdown(el('pb-briefing'), fallback);
  }

  el('pb-stakeholders').textContent = c.stakeholders?.length
    ? c.stakeholders.map(s => ACTORS.find(a => a.id === s)?.name || s).join(', ')
    : 'No stakeholders identified.';

  window.print();
}
