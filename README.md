# 🌊 FloodCast — Live Flood Forecast Dashboard

An automated live flood forecasting web application and API platform that monitors hourly CSV simulation outputs from InfoWorks ICM, ingests the data into a database, exposes JSON API endpoints for external plugin extraction, and displays live forecasts on an interactive dashboard.

**Location:** Kuching, Sarawak, Malaysia

---

## 🏗️ Architecture

```
ICM Water/Live → CSV exports → File Watcher → SQLite DB → FastAPI → Vue.js Dashboard
                (data/exports/)   (watchdog)    (async)     (REST)    (Leaflet + ECharts)
```

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+** (for backend)
- **Node.js 22+** (for frontend)

### 1. Start the Backend (FastAPI)

```bash
cd backend
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### 2. Start the Frontend (Vue.js)

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be available at `http://localhost:5173`.

### 3. Ingest Data

Drop your ICM CSV files into the `data/exports/` directory:

- `Node_Flood Forecast*.csv` — Time-series forecast data
- `*Alert definition list*.csv` — Alert/warning definitions

The file watcher will automatically detect and ingest new files.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|:-------|:---------|:------------|
| `GET` | `/api/v1/nodes` | List all monitoring nodes with current status |
| `GET` | `/api/v1/node-forecast?node_id=Drain_53` | Get water level forecast for a node |
| `GET` | `/api/v1/node-forecast/latest?lat=1.4908&lon=110.2738` | Nearest node spatial forecast |
| `GET` | `/api/v1/alerts/active` | Currently active alerts |
| `GET` | `/api/v1/alerts/history` | Alert history with filtering |
| `GET` | `/api/v1/dashboard/summary` | Dashboard summary statistics |
| `GET` | `/docs` | Interactive Swagger API docs |
| `GET` | `/health` | System health check |

---

## 📁 Project Structure

```
Flood Live Data Website/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Configuration & constants
│   │   ├── database.py          # Async SQLite engine
│   │   ├── models.py            # SQLAlchemy ORM models
│   │   ├── schemas.py           # Pydantic response schemas
│   │   ├── routers/
│   │   │   ├── forecasts.py     # Node & forecast endpoints
│   │   │   ├── alerts.py        # Alert endpoints
│   │   │   └── dashboard.py     # Dashboard summary
│   │   └── services/
│   │       ├── csv_ingester.py  # CSV parsing & upsert
│   │       └── file_watcher.py  # Watchdog + APScheduler
│   ├── schema.sql               # Reference SQL schema
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── FloodMap.vue     # Leaflet GIS map
│   │   │   ├── HydrographChart.vue # ECharts time-series
│   │   │   ├── AlertFeed.vue    # Alert notification panel
│   │   │   └── StatsBar.vue     # Summary statistics
│   │   ├── views/
│   │   │   └── DashboardView.vue
│   │   ├── composables/
│   │   │   └── useApi.ts        # API client
│   │   ├── assets/main.css      # Design system
│   │   ├── App.vue              # Root layout
│   │   └── main.ts              # Entry point
│   └── vite.config.ts
├── data/
│   └── exports/                 # Drop ICM CSVs here
└── README.md
```

---

## ⚙️ Configuration

Edit `backend/app/config.py` to customize:

- **Node metadata** (GIS coordinates, names)
- **Warning/alert thresholds** (default: 2.0m / 3.0m)
- **Watch interval** (default: 3600 seconds)
- **CORS origins** (frontend dev server URLs)

---

## 🔄 Migration to PostgreSQL

The app uses SQLite by default for zero-config setup. To migrate:

1. Install PostgreSQL + TimescaleDB + PostGIS
2. Update `DATABASE_URL` in config to `postgresql+asyncpg://...`
3. Replace `aiosqlite` with `asyncpg` in requirements.txt
4. See `backend/schema.sql` for PostgreSQL-specific migration notes

---

## 📄 License

MIT
