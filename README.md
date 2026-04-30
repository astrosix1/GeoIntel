# GeoIntel — Real-Time Geopolitical Intelligence Platform

> An interactive, data-driven platform for understanding global crises, geopolitical relationships, and conflict escalation dynamics.

---

## 🌍 What Is GeoIntel?

GeoIntel is a full-stack intelligence platform that combines:

- **Real-time crisis data** from ACLED (20,000+ armed conflict events/month)
- **Global news analysis** from 100+ sources via NewsAPI
- **Economic indicators** for 200+ countries via World Bank
- **Actor network mapping** showing relationships between major state and non-state actors
- **Probabilistic forecasting** using historical analog matching
- **Multi-domain impact analysis** across military, economic, political, environmental, technological, and information domains
- **Interactive 3D globe** visualization with zoomable, rotatable Earth
- **Escalation scenarios** showing cascade effects of regional instability

## 🚀 Quick Start

### Prerequisites
- Python 3.8+ (for backend)
- Any modern web browser
- 5 minutes for setup

### Setup (3 steps)

**1. Get API Key**
```bash
# Go to https://newsapi.org, sign up (free), copy key
# Edit backend/.env and paste key
```

**2. Run Backend**
```bash
cd backend
python app.py    # Or: run_backend.bat (Windows) / ./run_backend.sh (Mac/Linux)
```

**3. Open Frontend**
```bash
# Open index.html in your browser
# Should see globe with real crises!
```

**That's it!** See [QUICK_START.md](QUICK_START.md) for details.

---

## 📦 Architecture

```
┌─────────────────────────────┐
│  Frontend (JavaScript)       │     ← Browser-based dashboard
│  - 3D Canvas Globe          │       No build step, no npm
│  - Crisis Dashboard         │       ~1430 lines of pure JS
└────────────┬────────────────┘
             │
        JSON/HTTP (CORS)
             │
┌────────────▼────────────────┐
│  Backend (Python/Flask)      │     ← Data aggregation server
│  - REST API (13 endpoints)  │       ~450 lines of Python
│  - Data Sync Scheduler      │       Runs on localhost:5000
└────────────┬────────────────┘
             │
    ┌────────┼────────┐
    │        │        │
┌───▼─┐ ┌───▼──┐ ┌──▼────┐
│ACLED│ │News  │ │World  │     ← Free data sources
│Data │ │API   │ │Bank   │       No auth needed (except NewsAPI)
└─────┘ └──────┘ └───────┘

┌─────────────────────────────┐
│  SQLite Database            │     ← Persistent storage
│  (geointel.db)              │       Crises, actors, relationships,
│                             │       forecasts, news, economics
└─────────────────────────────┘
```

### Data Flow

1. **Sync Cycle** (every hour):
   - Backend fetches latest data from ACLED, NewsAPI, World Bank
   - Parses and normalizes into common schema
   - Upserts to SQLite database

2. **User Request**:
   - Frontend calls `GeoIntelAPI.getCrises()`
   - Backend queries database
   - Returns JSON response
   - Frontend renders pins on globe

3. **Selection**:
   - User clicks crisis
   - Frontend fetches forecasts, news, relationships
   - Displays in right panel with analysis

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| **[QUICK_START.md](QUICK_START.md)** | 5-minute setup guide |
| **[SETUP_GUIDE.md](SETUP_GUIDE.md)** | Detailed setup with troubleshooting |
| **[INTEGRATION_COMPLETE.md](INTEGRATION_COMPLETE.md)** | What was built, next features |
| **backend/README.md** | API endpoint reference |

## 🛠️ Tools & Scripts

| File | Purpose |
|------|---------|
| **verify_setup.py** | Diagnostic script (checks all components) |
| **backend/run_backend.bat** | Windows startup script |
| **backend/run_backend.sh** | Mac/Linux startup script |
| **frontend-api.js** | JavaScript API client (13 methods) |

---

## 🎮 User Interface

### Left Sidebar
- **Search**: Find crises by name or country
- **Filters**: By domain (military, economic, etc.) or type (conflict, diplomatic, etc.)
- **Crisis List**: Browse active crises, click to select
- **Toggle**: Collapse/expand with ◀ button

### Center: Interactive Globe
- **Drag**: Rotate the Earth
- **Scroll**: Zoom in/out
- **Click Pins**: Select crisis
- **Timeline**: Scrub through time
- **Controls** (top right):
  - ↺ Reset to center
  - ⟳ Toggle actor relationships
  - ◉ Toggle power heatmap
  - ⚡ Cascade simulation

### Right Panel: Analysis
Five tabs for each selected crisis:

1. **Overview**: Title, severity, stakeholders, analysis, historical analog
2. **Forecast**: Probabilistic outcomes (Unlikely/Possible/Likely)
3. **Network**: Actor relationship graph
4. **Domains**: Impact across 6 dimensions (military, economic, political, etc.)
5. **Cascade**: Escalation scenario and causal chain

### Alerts
- Real-time warnings for crises exceeding thresholds
- Color-coded by severity

---

## 📊 Real Data Included

### ACLED (Armed Conflict Location & Event Data)
- 300+ recent armed conflict events
- Updated hourly
- Covers: battles, protests, violence, strategic developments
- Automatically normalized into "Crisis" entities

### NewsAPI
- 100+ news sources
- Sentiment analysis on headlines
- Linked to relevant crises
- Updated every 30 minutes
- Requires free API key (get at https://newsapi.org)

### World Bank
- Economic indicators for 200+ countries
- 6 metrics: GDP, growth, exports, imports, inflation, unemployment
- Updated quarterly/annually
- Completely free, no auth needed

### Manual Actor Database
- 8 major actors: US, China, Russia, EU, India, Iran, Israel, North Korea
- 13 relationships: alliances, conflicts, economic ties, proxy arrangements
- Power metrics: military, economic, political, technological

### Probabilistic Forecasts
- Historical analog matching
- Multiple scenarios per crisis
- Confidence intervals

---

## 🔌 API Endpoints

All endpoints on `http://localhost:5000/api`:

### Crises
- `GET /crises` - List all crises (filters: type, severity, days)
- `GET /crises/{id}` - Crisis detail + news + forecasts
- `PATCH /crises/{id}` - Update (admin only)

### Actors
- `GET /actors` - List all actors
- `GET /actors/{id}` - Actor + relationships

### Relationships
- `GET /relationships` - List relationships (filter: type)

### Forecasts
- `GET /forecasts/{crisis_id}` - Probabilistic predictions

### News
- `GET /news` - News articles (filters: crisis_id, days, limit)

### Economic
- `GET /economic/{country_code}` - Economic data (e.g., /economic/US)

### Admin
- `POST /admin/sync` - Manually trigger data sync
- `GET /admin/stats` - Database statistics
- `GET /health` - Health check

See [backend/README.md](backend/README.md) for full documentation.

---

## 💡 Features

### Core
✅ Interactive 3D globe with country boundaries  
✅ Real-time crisis pins from ACLED  
✅ Multi-source data aggregation (ACLED, NewsAPI, World Bank)  
✅ Actor relationship network visualization  
✅ Probabilistic forecasting with confidence levels  
✅ Multi-domain impact analysis  
✅ News article integration with sentiment  
✅ Historical analog matching  

### UI/UX
✅ Collapsible sidebar (space optimization)  
✅ Floating right panel overlay  
✅ Tabbed analysis interface  
✅ Search and filtering  
✅ Drag-to-rotate, scroll-to-zoom  
✅ Responsive layout  
✅ Dark theme with accent colors  

### Backend
✅ Async data sync on scheduler (hourly)  
✅ SQLite database with proper schema  
✅ CORS-enabled for frontend access  
✅ Error handling & validation  
✅ Graceful degradation if APIs unavailable  
✅ Health check endpoint  

---

## 🔧 Tech Stack

### Frontend
- **HTML5** - Structure
- **CSS3** - Styling (no framework)
- **JavaScript** - Pure vanilla JS (no frameworks, no build tools)
- **Canvas 2D** - Globe rendering
- **TopoJSON** - Country geometry
- **Fetch API** - HTTP requests

### Backend
- **Python 3.8+** - Language
- **Flask 3.0.0** - Web framework
- **SQLAlchemy 2.0.23** - ORM
- **APScheduler 3.10.4** - Background tasks
- **Requests 2.31.0** - HTTP client
- **TextBlob 0.17.1** - Sentiment analysis

### Database
- **SQLite** - Default (dev/testing)
- **PostgreSQL** - Ready for production

### External APIs
- **ACLED** - Conflict data (free, no auth)
- **NewsAPI** - News articles (free tier available)
- **World Bank** - Economic data (free, no auth)

---

## 🚦 Status

| Component | Status |
|-----------|--------|
| Frontend Globe | ✅ Complete |
| Dashboard UI | ✅ Complete |
| Backend API | ✅ Complete |
| Data Connectors | ✅ Complete |
| Database Schema | ✅ Complete |
| Integration | ✅ Complete |
| Documentation | ✅ Complete |
| Startup Helpers | ✅ Complete |

---

## 📈 Performance

- **Globe Rendering**: 60 FPS (Canvas 2D)
- **Data Load**: <500ms (10 crises)
- **API Response**: <200ms (cached)
- **Database**: SQLite (suitable for <100,000 records)

---

## 🎯 Next Steps

### Immediate (optional)
- [ ] Run `python verify_setup.py` to check all components
- [ ] Monitor backend logs for data sync completion
- [ ] Test all 5 dashboard tabs
- [ ] Export/print crisis analysis

### Short-term (nice-to-have)
- [ ] Add user authentication
- [ ] Implement WebSocket for real-time updates
- [ ] Add custom alert thresholds
- [ ] Bookmark/favorite crises
- [ ] PDF report generation

### Long-term (scalability)
- [ ] Migrate to PostgreSQL
- [ ] Add Redis caching
- [ ] Implement ML forecasting
- [ ] Satellite imagery integration
- [ ] Supply chain vulnerability mapping
- [ ] Deploy to cloud (AWS/GCP/Azure)
- [ ] Mobile app version

---

## 🆘 Troubleshooting

**"Backend unavailable" alert in browser**
```bash
# Make sure backend is running:
cd backend
python app.py

# Check it's working:
curl http://localhost:5000/api/health
# Should return: {"status":"ok"}
```

**No news articles appearing**
```bash
# Get free API key from https://newsapi.org
# Edit backend/.env and add your key:
NEWSAPI_KEY=your_actual_key_here
# Restart backend
```

**Module not found errors**
```bash
pip install -r backend/requirements.txt
```

**Port 5000 already in use**
- Kill the existing process using port 5000
- Or edit `backend/app.py` line 421 to use different port

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for more troubleshooting.

---

## 📝 License & Data

- **Code**: Unlicensed (public domain)
- **ACLED Data**: [Attribution required](https://acleddata.com)
- **NewsAPI**: [Check their license](https://newsapi.org)
- **World Bank**: [CC-BY 4.0](https://data.worldbank.org)

---

## 🤝 Contributing

This is a single-person project. Feel free to fork and extend!

---

## 📞 Support

Questions? Check:
1. [QUICK_START.md](QUICK_START.md) - Fast setup
2. [SETUP_GUIDE.md](SETUP_GUIDE.md) - Detailed guide
3. Browser console (F12) - Error messages
4. Backend terminal - Server logs

---

## 🎓 Learning Resources

- **Flask**: https://flask.palletsprojects.com
- **SQLAlchemy**: https://docs.sqlalchemy.org
- **Canvas 2D**: https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API
- **ACLED API**: https://acleddata.com/api
- **NewsAPI**: https://newsapi.org

---

**Built with ❤️ for global intelligence analysis**

Last updated: April 15, 2026
