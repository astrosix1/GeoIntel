# GeoIntel Setup Guide

## Overview
The GeoIntel platform consists of:
- **Backend**: Python/Flask REST API that aggregates real-world geopolitical data
- **Frontend**: Interactive Canvas-based globe dashboard
- **Data Sources**: ACLED (conflicts), NewsAPI (news), World Bank (economic data)

---

## Step 1: Backend Setup

### A. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

This installs:
- Flask 3.0.0 - Web framework
- SQLAlchemy 2.0.23 - Database ORM
- requests 2.31.0 - HTTP client
- APScheduler 3.10.4 - Background task scheduling
- textblob 0.17.1 - Sentiment analysis
- python-dotenv 1.0.0 - Configuration management
- Plus 6 additional supporting libraries

### B. Configure API Keys

Edit `backend/.env`:

```env
# Required: Get free NewsAPI key (60 requests/day free tier)
NEWSAPI_KEY=your_newsapi_key_here

# Optional: ACLED doesn't require auth, but email is appreciated
ACLED_EMAIL=your_email@example.com

# Database (SQLite default, no setup needed)
DATABASE_URL=sqlite:///geointel.db

# Optional: For production caching (skip for now)
REDIS_URL=redis://localhost:6379
```

**Getting API Keys:**

1. **NewsAPI** (Required for news articles):
   - Go to https://newsapi.org
   - Sign up for free account
   - Copy your API key
   - Paste into `.env` file

2. **ACLED** (Armed Conflict Location & Event Data):
   - Free, no key required
   - But provide your email to support research: https://acleddata.com

3. **World Bank** (Economic indicators):
   - Completely free, no auth needed
   - API at https://api.worldbank.org/v2

### C. Initialize Database

```bash
python models.py
```

This creates:
- SQLite database (`geointel.db`)
- 6 tables (crises, actors, relationships, forecasts, news, economic_data)
- Preloaded actors (US, China, Russia, EU, India, Iran, Israel, North Korea)

### D. Run the Backend Server

```bash
python app.py
```

You should see:
```
 * Running on http://0.0.0.0:5000
 * Background scheduler started
 * Database initialized
```

The server:
- Listens on `http://localhost:5000`
- Automatically syncs data every hour (ACLED, News, Economic)
- Provides 13 REST API endpoints
- Enables CORS for frontend access

---

## Step 2: Frontend Access

### Open the Dashboard

1. **From the backend directory**, the frontend files are at the parent level:
   ```
   Event Globe/
   ├── index.html           ← Open this in browser
   ├── frontend-api.js      ← API client (auto-imported)
   ├── topojson.min.js      ← Map data library
   ├── countries-110m.json  ← Country boundary data
   └── backend/
       ├── app.py
       ├── models.py
       ├── data_sources.py
       ├── requirements.txt
       ├── .env
       └── geointel.db
   ```

2. **Open in Browser**:
   - Double-click `index.html`, OR
   - Run `python -m http.server 8000` from the Event Globe directory
   - Visit `http://localhost:8000/index.html`

3. **Verify Connection**:
   - Look for "Backend connected successfully" in browser console (F12)
   - If error appears top-right, backend isn't running

---

## API Endpoints Reference

### Crises
- `GET /api/crises` - List all active crises (optional filters: type, min_severity, days)
- `GET /api/crises/{id}` - Get crisis detail + news + forecasts
- `PATCH /api/crises/{id}` - Update crisis (admin only)

### Actors
- `GET /api/actors` - List all actors
- `GET /api/actors/{id}` - Get actor + relationships

### Relationships
- `GET /api/relationships` - List actor relationships (optional filter: type)

### Forecasts
- `GET /api/forecasts/{crisis_id}` - Get probabilistic forecasts

### News
- `GET /api/news` - Recent articles (filters: crisis_id, days, limit)

### Economic
- `GET /api/economic/{country_code}` - Economic indicators (eg: /api/economic/US)

### Admin
- `POST /api/admin/sync` - Manually trigger data sync
- `GET /api/admin/stats` - Database statistics
- `GET /api/health` - Health check

---

## Frontend Interface

### Left Sidebar
- **Search**: Find crises by name or country
- **Domains**: Filter by impact type (military, economic, political, etc.)
- **Crisis Types**: Filter by conflict type
- **Active Crises List**: Click to select and analyze

### Globe Center
- **Interactive 3D Globe**: Drag to rotate, scroll to zoom
- **Event Pins**: Color-coded by severity
- **Timeline**: Scrub through 2020-2026
- **Controls** (top right):
  - ↺ Reset view
  - ⟳ Toggle relationships
  - ◉ Toggle power heatmap
  - ⚡ Cascade simulation

### Right Panel (Floating)
Click a crisis to see:
- **Overview**: Title, severity, stakeholders, analysis, historical analogy
- **Forecast**: Probabilistic scenarios (Unlikely/Possible/Likely)
- **Network**: Actor relationship graph
- **Domains**: Multi-domain impact analysis
- **Cascade**: Scenario simulation of escalation

### Alerts
Active warnings tied to high-severity crises

---

## Data Refresh Schedule

By default, data syncs automatically:
- **ACLED** (conflicts): Every 1 hour
- **News**: Every 30 minutes
- **Economic**: Every 24 hours

Or manually trigger via:
```bash
curl -X POST http://localhost:5000/api/admin/sync
```

---

## Troubleshooting

### "Backend not available" error
**Problem**: Frontend can't connect to backend
**Solution**:
1. Verify backend is running: `python app.py`
2. Check port 5000 is listening: `netstat -an | grep 5000` (Windows: `netstat -ab`)
3. Verify localhost:5000/api/health returns `{"status":"ok"}`

### "NEWSAPI_KEY not set" warning
**Problem**: News articles not loading
**Solution**:
1. Sign up at https://newsapi.org
2. Copy API key
3. Edit `backend/.env`: `NEWSAPI_KEY=your_key`
4. Restart backend: `python app.py`

### Database locked error
**Problem**: SQLite database in use by another process
**Solution**:
1. Ensure only ONE `python app.py` instance running
2. Delete `geointel.db` to reset
3. Run `python models.py` to recreate

### Module not found errors
**Problem**: Missing Python packages
**Solution**:
```bash
pip install -r requirements.txt
```

---

## Next Steps

### To extend the platform:

1. **Add New Data Source**:
   - Create connector in `backend/data_sources.py`
   - Add to `DataAggregator.sync_all_sources()`
   - Update database models if needed

2. **Customize Forecasts**:
   - Edit forecast logic in `backend/data_sources.py`
   - Add historical analogs database

3. **Production Deployment**:
   - Migrate from SQLite to PostgreSQL
   - Add Redis caching for frequent queries
   - Implement authentication for admin endpoints
   - Use Gunicorn/uWSGI instead of Flask dev server
   - Set up SSL/TLS certificates

4. **Enhanced Visualization**:
   - Add real-time data streaming (WebSockets)
   - Implement satellite imagery overlays
   - Add sankey/flow diagrams for cascade effects

---

## Architecture Diagram

```
┌─────────────────────────────────────┐
│   Frontend (JavaScript/Canvas)      │
│  - Interactive 3D Globe             │
│  - Crisis Dashboard                 │
│  - Real-time Analysis Panels        │
└──────────────┬──────────────────────┘
               │
        HTTP (CORS)
               │
┌──────────────▼──────────────────────┐
│    Backend (Python/Flask)           │
│  - REST API (13 endpoints)          │
│  - Background Scheduler             │
│  - Database ORM (SQLAlchemy)        │
└──────────────┬──────────────────────┘
               │
   ┌───────────┼───────────┐
   │           │           │
┌──▼──┐  ┌────▼──┐  ┌────▼────┐
│ACLED│  │NewsAPI│  │World    │
│Data │  │       │  │Bank     │
└─────┘  └───────┘  └─────────┘

┌─────────────────────────────────────┐
│  SQLite Database (geointel.db)      │
│  - Crises (300+)                    │
│  - Actors (8+)                      │
│  - Relationships (13+)              │
│  - Forecasts (1000+)                │
│  - News (1000+)                     │
│  - Economic Indicators (1000+)      │
└─────────────────────────────────────┘
```

---

## Key Features

✅ **Real-Time Data**: Updated hourly from authoritative sources  
✅ **Multi-Domain Analysis**: Military, Economic, Political, Environmental, Technology, Information  
✅ **Probabilistic Forecasting**: Bayesian estimates of outcomes  
✅ **Actor Network Mapping**: Relationship visualization between states/NGOs  
✅ **Cascade Simulation**: What-if escalation scenarios  
✅ **Sentiment Analysis**: News article emotional tone  
✅ **Historical Analogs**: Pattern matching with past crises  
✅ **Zero-Auth Design**: Fully public by default, easy to add auth later  

---

**Questions?** Check the backend/README.md for API documentation details.
