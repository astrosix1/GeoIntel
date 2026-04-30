# GeoIntel Backend API

Real-time geopolitical intelligence platform backend. Aggregates data from multiple sources (ACLED, NewsAPI, World Bank) and serves via REST API.

## Setup

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment

Edit `.env`:

```env
# NewsAPI key (sign up at https://newsapi.org)
NEWSAPI_KEY=your_key_here

# Database (SQLite by default, can use PostgreSQL)
DATABASE_URL=sqlite:///geointel.db

# Redis (optional, for caching)
REDIS_URL=redis://localhost:6379

# App settings
FLASK_ENV=development
DEBUG=True
```

### 3. Initialize Database

```bash
python models.py
```

This creates tables and initializes core actors.

### 4. Run the API

```bash
python app.py
```

Server runs on `http://localhost:5000`

## API Endpoints

### Crises

**GET /api/crises**
- Get all active crises
- Params: `type` (conflict/military/etc), `min_severity` (0-100), `days` (7-365)

```bash
curl http://localhost:5000/api/crises?type=conflict&min_severity=70
```

**GET /api/crises/{id}**
- Detailed info on specific crisis + related news and forecasts

**PATCH /api/crises/{id}**
- Update crisis (admin endpoint)

### Actors

**GET /api/actors**
- Get all geopolitical actors (US, China, Russia, etc)

**GET /api/actors/{id}**
- Get specific actor + their relationships

### Relationships

**GET /api/relationships**
- Get all actor relationships (alliances, conflicts, etc)
- Params: `type` (alliance/conflict/tension/etc)

### Forecasts

**GET /api/forecasts/{crisis_id}**
- Get probabilistic forecasts for a crisis

### News

**GET /api/news**
- Recent articles
- Params: `crisis_id`, `days`, `limit`

### Economic Data

**GET /api/economic/{country_code}**
- Economic indicators (GDP, inflation, exports, etc)

### Admin

**POST /api/admin/sync**
- Manually trigger data sync from all sources

**GET /api/admin/stats**
- Database statistics

**GET /api/health**
- Health check

## Data Sources

### ACLED (Armed Conflict Location & Event Data)
- Free, real-time global conflict data
- Updated daily
- Covers: battles, protests, violence, strategic developments
- ~20,000 events/month

### NewsAPI
- Aggregates articles from 50+ news sources
- Sentiment analysis on headlines
- Requires free API key

### World Bank
- Economic indicators (GDP, trade, inflation, unemployment)
- Updated quarterly/annually
- Covers 200+ countries

## Architecture

```
backend/
├── models.py           # SQLAlchemy ORM models
├── data_sources.py     # Connectors to external APIs
├── app.py              # Flask API server
├── requirements.txt    # Python dependencies
├── .env               # Configuration
└── geointel.db        # SQLite database
```

### Models

- **Crisis**: Geopolitical crises with severity, type, location, stakeholders
- **Actor**: States/NGOs/organizations with power metrics
- **Relationship**: Connections between actors (alliance/conflict/etc)
- **Forecast**: Probabilistic predictions on crisis outcomes
- **News**: Cached articles with sentiment analysis
- **EconomicData**: Country-level economic indicators

### Background Sync

Scheduler runs data sync every hour:
1. Fetch latest ACLED events
2. Fetch news articles  
3. Fetch economic updates
4. Upsert to database (creates or updates)

## Usage Example

### Python

```python
import requests

# Get all active conflicts
response = requests.get('http://localhost:5000/api/crises?type=conflict')
crises = response.json()

# Get details on Ukraine
response = requests.get('http://localhost:5000/api/crises/acled_12345')
crisis = response.json()

print(crisis['title'])  # Ukraine-Russia War
print(crisis['severity'])  # 95
print(crisis['stakeholders'])  # ['RU', 'US', 'EU']
print(crisis['forecasts'])  # Probabilistic outcomes
```

### JavaScript (from frontend)

```javascript
// Fetch all crises
const response = await fetch('http://localhost:5000/api/crises');
const data = await response.json();

// Get crisis details
const crisis = await fetch(`http://localhost:5000/api/crises/${id}`).then(r => r.json());

// Get actor relationships
const actors = await fetch('http://localhost:5000/api/actors').then(r => r.json());
const rels = await fetch('http://localhost:5000/api/relationships').then(r => r.json());
```

## Database Schema

### crises table
- id (PK)
- type, title, country, lat, lon
- severity (0-100), confidence (0-100)
- date_start, date_updated
- analysis, impact
- stakeholders (CSV)
- military_score, economic_score, political_score, etc (0-100 each)
- source, source_id, is_verified

### actors table
- id (PK): US, CN, RU, EU, IN, etc
- name, category
- lat, lon (capital location)
- color (for visualization)
- military_power, economic_power, political_influence, technological_capability (0-100 each)
- is_nuclear

### relationships table
- id (PK)
- actor_a, actor_b
- type: alliance, conflict, tension, economic, proxy
- strength, stability (0-100)

## Extending

### Add New Data Source

1. Create connector in `data_sources.py`:

```python
class MyDataConnector:
    @staticmethod
    def fetch_data():
        # Fetch from API
        # Parse response
        # Return list of dicts
        pass
    
    @staticmethod
    def _parse_item(item):
        # Convert to Crisis/News/etc format
        pass
```

2. Add to `DataAggregator.sync_all_sources()`:

```python
def sync_all_sources():
    # ... existing code ...
    
    my_data = MyDataConnector.fetch_data()
    for item in my_data:
        DataAggregator._upsert_crisis(session, item)
```

3. Optionally add scheduler job:

```python
scheduler.add_job(
    func=MyDataConnector.fetch_data,
    trigger="interval",
    hours=6,  # Sync every 6 hours
)
```

### Add Forecast Logic

```python
# In app.py or separate forecasting.py

def generate_forecasts_for_crisis(crisis_id):
    session = Session()
    crisis = session.query(Crisis).filter(Crisis.id == crisis_id).first()
    
    # Find similar historical crises
    similar = find_historical_analogs(crisis)
    
    # Calculate probabilities based on outcomes
    forecasts = [
        Forecast(
            id=f"{crisis_id}_escalation",
            crisis_id=crisis_id,
            question="Will this escalate within 6 months?",
            prob_unlikely=35,
            prob_possible=45,
            prob_likely=20,
            method="Historical"
        ),
        # ... more forecasts
    ]
    
    for f in forecasts:
        session.add(f)
    
    session.commit()
    session.close()
```

## Notes

- ACLED is free and requires no API key
- NewsAPI requires free account (newsapi.org)
- World Bank data is freely available via API
- For production, migrate from SQLite to PostgreSQL
- Add Redis for caching frequent queries
- Consider adding authentication for admin endpoints
- Rate limits on external APIs should be respected

## Next Steps

Once backend is running and serving real data, connect frontend to these API endpoints instead of using placeholder CRISES array.
