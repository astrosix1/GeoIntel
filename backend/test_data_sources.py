#!/usr/bin/env python3
"""
Test if data sources are working
"""
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

print("\n" + "="*60)
print("TESTING DATA SOURCES")
print("="*60)

# Test ACLED
print("\n1. TESTING ACLED (Armed Conflicts)...")
try:
    import requests
    from datetime import datetime, timedelta

    end_date = datetime.utcnow().date()
    response = requests.get(
        f"https://api.acleddata.com/api/terms/year/?year={end_date.year}",
        timeout=10
    )

    if response.status_code == 200:
        data = response.json()
        if 'data' in data:
            print(f"   ✅ ACLED working - Found {len(data['data'])} events")
        else:
            print(f"   ⚠️  ACLED response missing 'data' field")
    else:
        print(f"   ❌ ACLED error: HTTP {response.status_code}")

except Exception as e:
    print(f"   ❌ ACLED error: {e}")

# Test NewsAPI
print("\n2. TESTING NewsAPI (News Articles)...")
try:
    api_key = os.getenv('NEWSAPI_KEY')

    if not api_key or api_key == 'your_newsapi_key_here':
        print(f"   ❌ NEWSAPI_KEY not set in .env")
        print(f"      Go to https://newsapi.org to get a free key")
    else:
        import requests
        params = {
            'q': 'geopolitical conflict',
            'sortBy': 'publishedAt',
            'language': 'en',
            'apiKey': api_key,
            'pageSize': 10,
        }

        response = requests.get(
            'https://newsapi.org/v2/everything',
            params=params,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ NewsAPI working - Found {len(data.get('articles', []))} articles")
        else:
            print(f"   ❌ NewsAPI error: HTTP {response.status_code}")
            print(f"      Response: {response.text[:200]}")

except Exception as e:
    print(f"   ❌ NewsAPI error: {e}")

# Test World Bank
print("\n3. TESTING World Bank (Economic Data)...")
try:
    import requests

    response = requests.get(
        'https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.CD',
        params={'format': 'json', 'per_page': 5},
        timeout=10
    )

    if response.status_code == 200:
        data = response.json()
        if len(data) > 1:
            print(f"   ✅ World Bank working - Got economic data")
        else:
            print(f"   ⚠️  World Bank response empty")
    else:
        print(f"   ❌ World Bank error: HTTP {response.status_code}")

except Exception as e:
    print(f"   ❌ World Bank error: {e}")

# Test Database
print("\n4. TESTING Database...")
try:
    from models import Session, Crisis
    session = Session()
    count = session.query(Crisis).count()
    session.close()
    print(f"   ✅ Database working - {count} crises in database")

except Exception as e:
    print(f"   ❌ Database error: {e}")

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print("""
If ACLED shows 0 events or errors, the API might be down.
If NewsAPI shows error, add NEWSAPI_KEY to .env:
  1. Go to https://newsapi.org
  2. Sign up (free)
  3. Get your API key
  4. Edit backend/.env and add: NEWSAPI_KEY=your_key
  5. Restart backend

World Bank should always work (no auth needed).

If database shows 0 crises, run data sync:
  curl -X POST http://localhost:5000/api/admin/sync
""")
print("="*60 + "\n")
