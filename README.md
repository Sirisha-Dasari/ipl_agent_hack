# IPL Agentic Intelligence v2.0

> A production-grade, agentic AI dashboard for live IPL match analytics — powered by Google ADK, Gemini Flash, Google Search, and a dynamic real-time frontend.

---

## What's New in v2.0

- **Google Search integration** — ADK agent uses `google_search` tool for real-time IPL scores, news, and player updates
- **14 analytical tools** — expanded from 11 (added `get_head_to_head`, `get_pitch_and_weather`, `search_ipl_news`)
- **Dynamic Canvas frontend** — animated particle background, real-time win probability bars, momentum ring gauge, over-by-over bar charts, recent balls visualization
- **6 interactive agent panels** — Commentary, Strategy, Stats, Head-to-Head, Pitch/Weather, Post-Match Report
- **Team color system** — all 10 IPL teams with branded colors
- **Smart fallbacks** — graceful mock data when API is unavailable, no crashes

---

## Project Features (At a glance)

- Dashboard (FastAPI + Uvicorn): interactive scoreboard, momentum gauges, AI tool panels (http://127.0.0.1:8000).
- REST API endpoints: commentary, strategy, stats, head-to-head, venue, post-match, agent trace/analysis.
- Agentic analytics: 14 tools for pre/live/post-match intelligence (win probability, momentum, strategy, commentary, summaries).
- Google ADK integration: `root_agent` using `gemini-flash-latest` and `google_search` tool; ADK Dev UI available.
- ADK Web UI: interactive agent sessions, traces and artifacts (runs on alternate port, e.g. 8002).
- Standalone runner: `run_agent.py` streams agent output with proper InvocationContext handling.
- Environment & secrets: `.env` support (`GOOGLE_API_KEY`, `CRIC_API_KEY`) and `.env.example` template.
- Data sources: CricAPI (live scores) + Google Search; mock/demo mode available for offline testing.
- Local dev persistence: in-memory session service with artifact storage under `.adk`.
- Heuristic models: built-in momentum, pressure index, and win-probability calculators for frontend visualizations.
- Dev helpers: `debug_agent.py` and trace endpoints to inspect agent structure and tool traces.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  FastAPI (main.py)                   │
│   GET /          → Dynamic HTML Dashboard            │
│   GET /api/*     → JSON data endpoints               │
└───────────────┬─────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────┐
│            ipl_agent/agent.py                        │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │           Google ADK Root Agent             │     │
│  │  model: gemini-flash-latest                 │     │
│  │  tools: [google_search + 14 custom tools]   │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  Data Sources:                                       │
│  ├── CricAPI (live match data, CRIC_API_KEY)         │
│  ├── Google Search (real-time news & scores)         │
│  └── Mock data (fallback, always works)              │
└─────────────────────────────────────────────────────┘
```

---

## Tools Inventory (14 tools)

| Tool | Phase | Description |
|------|-------|-------------|
| `get_live_match_data` | All | Live score via CricAPI |
| `get_match_status` | All | Pre/Live/Completed detection |
| `get_team_form` | Pre | Last 5 matches, NRR, position |
| `get_player_stats` | Pre/Post | Batsmen, bowlers, impact players |
| `get_head_to_head` | Pre | Historical rivalry data |
| `get_pitch_and_weather` | Pre | Venue conditions, dew, toss advice |
| `analyze_momentum` | Live | Pressure index, phase, RR comparison |
| `predict_win_probability` | Live | Multi-factor probability model |
| `suggest_strategy` | Live | Batting/bowling/field tactics |
| `generate_commentary` | Live | Context-aware narrative |
| `generate_notifications` | Live | Smart alerts (wickets, surges) |
| `generate_key_insights` | Live/Post | Turning points, momentum shifts |
| `generate_post_match_summary` | Post | Full match report |
| `search_ipl_news` | All | Real-time Google Search (ADK) |

---

## Setup & Run

### 1. Clone and install

```bash
python -m venv venv
# Windows
venv\Scripts\Activate.ps1
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file:
```env
GOOGLE_API_KEY=your_gemini_api_key
CRIC_API_KEY=your_cricapi_key
```

### 3A. Run FastAPI Dashboard

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** — the full dynamic dashboard.

### 3B. Run ADK Agent (with Google Search)

```bash
adk web
```

Open **http://127.0.0.1:8000** — the ADK chat interface with trace view.

### Environment file (recommended)

Use the example file to create a local `.env` and keep secrets out of source control:

```powershell
copy .env.example .env
# then edit .env and fill in your keys (DO NOT commit .env)
```

The app and the agent will automatically load `.env` (via `python-dotenv`) on startup.

---

## Dashboard Features

- **Live Scoreboard** — Real-time score, overs, CRR/RRR, recent balls (color-coded)
- **Win Probability Bar** — Animated dual-fill bar with team colors
- **Momentum Ring** — Circular pressure gauge (0–100 index)
- **Over-by-Over Bars** — Last 5 overs run visualization
- **6 AI Tool Panels** — Click to trigger any analytics workflow
- **Key Insights Row** — Auto-populated turning points, pressure moments, momentum shifts
- **Live Notifications** — Toast alerts for wickets, surge moments
- **Match Selector** — Switch between ongoing IPL matches

---

## Example ADK Prompts

```
Give me the live score for MI vs CSK and predict who will win
What strategy should CSK adopt in the death overs?
Show me the head-to-head record between RCB and KKR
What's the pitch and weather report for Wankhede today?
Generate a post-match summary for today's game
Show me your tool trace
```

---

## Notes

- `DEMO_MODE = True` in `agent.py` forces mock data (useful for dev/testing)
- Google Search in ADK requires `GOOGLE_API_KEY` with Search API enabled
- CricAPI free tier limits apply; mock fallback always works
- Deploy to Cloud Run: `adk deploy cloud_run`
