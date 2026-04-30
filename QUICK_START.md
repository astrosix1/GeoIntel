# 🚀 Quick Start - GeoIntel Platform

## ⏱️ 5-Minute Setup

### 1️⃣ Get API Key (2 min)
```
1. Go to https://newsapi.org
2. Click "Get API Key" → Sign up (free)
3. Copy your API key
4. Open backend/.env
5. Replace "your_newsapi_key_here" with your key
```

### 2️⃣ Install & Run Backend (2 min)

**Windows:**
```bash
cd backend
run_backend.bat
```

**Mac/Linux:**
```bash
cd backend
./run_backend.sh
```

Wait for: `* Running on http://0.0.0.0:5000`

### 3️⃣ Open Frontend (1 min)
```
1. Double-click: index.html
   OR: Open http://localhost:8000/index.html
2. Check browser console (F12) for "Backend connected"
3. See real crises from ACLED, news, forecasts!
```

---

## ✅ Verification

```bash
# Run diagnostic:
python verify_setup.py
```

Should see all ✅ green checks.

---

## 🎮 How to Use

| Feature | How |
|---------|-----|
| **Rotate Globe** | Click & drag |
| **Zoom** | Scroll wheel |
| **Select Crisis** | Click on pin or list item |
| **View Forecasts** | Click crisis → Forecast tab |
| **See Relationships** | Click crisis → Network tab |
| **Analyze Impact** | Click crisis → Domains tab |
| **Scenario** | Click crisis → Cascade tab |
| **Search** | Type in left panel search |
| **Filter Types** | Click type chips (left panel) |
| **Collapse Sidebar** | Click ◀ button |

---

## 📊 Real Data Included

- **ACLED**: Armed conflict data (updated hourly)
- **NewsAPI**: News articles from 100+ sources (updated every 30 min)
- **World Bank**: Economic data for 200+ countries (updated daily)
- **Forecasts**: Probabilistic predictions
- **Actors**: US, China, Russia, EU, India, Iran, Israel, N.Korea
- **Relationships**: 13 major geopolitical connections

---

## ❓ Troubleshooting

| Problem | Solution |
|---------|----------|
| "Backend unavailable" alert | Run `python app.py` in backend folder |
| No news articles | Add NEWSAPI_KEY to backend/.env |
| "Module not found" error | Run `pip install -r backend/requirements.txt` |
| Port 5000 already in use | Kill the other process or use different port |

---

## 📚 Full Documentation

- **SETUP_GUIDE.md** - Complete setup with all details
- **INTEGRATION_COMPLETE.md** - What was done & next features
- **backend/README.md** - API endpoint reference

---

## 💻 Manual Setup (If scripts don't work)

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
# OR
venv\Scripts\activate.bat       # Windows

# Install packages
pip install -r requirements.txt

# Initialize database
python models.py

# Run server
python app.py
```

Then open `index.html` in browser.

---

## 🎯 What's Working

✅ Real geopolitical crises from ACLED  
✅ Actor network visualization  
✅ Probabilistic forecasting  
✅ Multi-domain impact analysis  
✅ News article integration  
✅ Historical analogs  
✅ Cascade/escalation simulation  
✅ Interactive 3D globe  
✅ Automatic data sync (hourly)  

---

**That's it!** You're running a professional geopolitical intelligence platform with real-world data.

Any issues? Check the browser console (F12) for error messages.
