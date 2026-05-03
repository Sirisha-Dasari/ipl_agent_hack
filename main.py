from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
import json
from dotenv import load_dotenv
import os
from collections import defaultdict, deque
from datetime import datetime

# Load environment variables from .env (if present)
load_dotenv()

from ipl_agent.agent import (
    get_live_match_data, predict_win_probability,
    analyze_momentum, get_match_status, generate_key_insights,
    generate_commentary, suggest_strategy, get_player_stats,
    get_team_form, get_head_to_head, get_pitch_and_weather,
  generate_post_match_summary, generate_notifications, get_previous_match_stats, TEAM_COLORS,
    show_tool_trace, ADK_AVAILABLE
)

app = FastAPI(title="IPL Agentic Intelligence Dashboard")

# In-memory per-match win probability history (keeps last 10 samples)
win_prob_histories = defaultdict(lambda: deque(maxlen=10))
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "win_prob_history.json")


def _load_win_prob_histories() -> None:
  """Load trend history from disk if available."""
  if not os.path.exists(HISTORY_FILE):
    return
  try:
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
      raw = json.load(f)
    for k, v in (raw or {}).items():
      if isinstance(v, list):
        win_prob_histories[k] = deque(v[-10:], maxlen=10)
  except Exception as ex:
    print(f"[Dashboard] Could not load history file: {ex}")


def _save_win_prob_histories() -> None:
  """Persist current trend history to disk."""
  try:
    payload = {k: list(v) for k, v in win_prob_histories.items()}
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
      json.dump(payload, f, ensure_ascii=True, indent=2)
  except Exception as ex:
    print(f"[Dashboard] Could not save history file: {ex}")


_load_win_prob_histories()


# ─────────────────────────────────────────────
# AGENT ENDPOINT (Multi-step reasoning + Google Search)
# ─────────────────────────────────────────────

@app.get("/api/agent/trace")
def api_agent_trace():
    """Get the tool execution trace showing agentic reasoning."""
    try:
        return show_tool_trace()["data"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agent/analysis")
def api_agent_analysis(query: str = Query(default="Analyze the current IPL match")):
    """
    Run multi-step agentic analysis on IPL match.
    Uses generate_key_insights + win_probability + commentary + strategy.
    """
    try:
        match_data = get_live_match_data("latest")["data"]
        team1 = match_data.get("team1", "MI")
        team2 = match_data.get("team2", "CSK")
        
        # Multi-step agentic reasoning pipeline
        insights = generate_key_insights(match_data)["data"]
        win_prob = predict_win_probability(match_data, team1, team2)["data"]
        strategy = suggest_strategy(match_data)["data"]
        commentary = generate_commentary(match_data)["data"]
        notifications = generate_notifications(match_data)["data"]
        momentum = analyze_momentum(match_data)["data"]
        
        return {
            "agentic_pipeline": "Multi-step reasoning active",
            "query": query,
            "match": match_data,
            "key_insights": insights,
            "win_probability": win_prob,
            "strategy": strategy,
            "commentary": commentary,
            "notifications": notifications,
            "momentum": momentum,
            "adkEnabled": ADK_AVAILABLE,
            "trace_available": "/api/agent/trace"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/api/dashboard")
def api_dashboard(match_id: str = Query(default="latest")):
    try:
        match_response = get_live_match_data(match_id)
        match_data = match_response["data"]
    except Exception as e:
        match_data = {"team1": "MI", "team2": "CSK", "status": "live",
                      "score": 0, "wickets": 0, "overs": 0.0,
                      "run_rate": 0, "required_run_rate": 0,
                      "balls_remaining": 120, "wickets_remaining": 10,
                      "venue": "TBD", "batting_team": "MI",
                      "last_5_overs": [], "recent_balls": []}

    team1 = match_data.get("team1", "MI")
    team2 = match_data.get("team2", "CSK")

    try:
        win_prob = predict_win_probability(match_data, team1, team2)["data"]
    except Exception:
        win_prob = {"probability_team1": 50, "probability_team2": 50, "confidence": "Low"}

    # record win-prob snapshot for trend display
    try:
      snap = {
        "ts": datetime.utcnow().isoformat() + 'Z',
        "overs": match_data.get("overs"),
        "p1": int(win_prob.get("probability_team1", 0)),
        "p2": int(win_prob.get("probability_team2", 0)),
      }
      win_prob_histories[match_id].append(snap)
      _save_win_prob_histories()
    except Exception:
      pass

    try:
        momentum_data = analyze_momentum(match_data)["data"]
        m_text = momentum_data.get("momentum", "Evenly poised")
        if "batting" in m_text.lower():
            momentum_data["indicator"] = "↑"
            momentum_data["indicator_class"] = "up"
        elif "bowling" in m_text.lower():
            momentum_data["indicator"] = "↓"
            momentum_data["indicator_class"] = "down"
        else:
            momentum_data["indicator"] = "↔"
            momentum_data["indicator_class"] = "neutral"
    except Exception:
        momentum_data = {"momentum": "Even", "indicator": "↔", "indicator_class": "neutral",
                         "pressure_level": "Medium", "pressure_index": 50, "last_5_overs": []}

    try:
        insights = generate_key_insights(match_data)["data"]
        turning_point = insights.get("turning_points", ["Match progressing steadily."])[0]
        all_insights = insights
    except Exception:
        turning_point = "Analyzing match data..."
        all_insights = {}

    try:
        notifs = generate_notifications(match_data)["data"]
    except Exception:
        notifs = {"alerts": ["Match is live — data loading..."], "priority": "normal"}

    t1_colors = TEAM_COLORS.get(team1, {"primary": "#00f2fe", "secondary": "#4facfe"})
    t2_colors = TEAM_COLORS.get(team2, {"primary": "#ff0844", "secondary": "#ffb199"})

    return {
        "match": match_data,
        "win_prob": win_prob,
      "win_prob_trend": list(win_prob_histories.get(match_id, [])),
        "momentum": momentum_data,
        "insight": turning_point,
        "all_insights": all_insights,
        "notifications": notifs,
        "team1_colors": t1_colors,
        "team2_colors": t2_colors
    }


@app.get("/api/commentary")
def api_commentary(match_id: str = Query(default="latest")):
    try:
        match_data = get_live_match_data(match_id)["data"]
        return generate_commentary(match_data)["data"]
    except Exception:
        return {"commentary": "The match is about to begin... tension builds!", "ball_by_ball": "", "atmosphere": ""}


@app.get("/api/strategy")
def api_strategy(match_id: str = Query(default="latest")):
    try:
        match_data = get_live_match_data(match_id)["data"]
        return suggest_strategy(match_data)["data"]
    except Exception:
        return {"batting_strategy": "N/A", "bowling_strategy": "N/A", "field_placements": [], "phase": "unknown"}


@app.get("/api/stats/{team}")
def api_stats(team: str):
    try:
        form = get_team_form(team)["data"]
        players = get_player_stats(team)["data"]
        colors = TEAM_COLORS.get(team.upper(), {"primary": "#00f2fe", "secondary": "#4facfe", "name": team.upper()})
        return {"form": form, "players": players, "colors": colors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/h2h/{team1}/{team2}")
def api_h2h(team1: str, team2: str):
    try:
        return get_head_to_head(team1, team2)["data"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/venue")
def api_venue(venue: str = Query(default="Wankhede")):
    try:
        return get_pitch_and_weather(venue)["data"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/post-match")
def api_post_match(match_id: str = Query(default="latest")):
    try:
        match_data = get_live_match_data(match_id)["data"]
        return generate_post_match_summary(match_data)["data"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/previous-stats")
def api_previous_stats(team: str = Query(default="")):
    try:
        return get_previous_match_stats(team)["data"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# FRONTEND
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    html = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IPL Intelligence — Agentic AI Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&family=Bebas+Neue&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #060810;
  --bg2: #0d1117;
  --card: rgba(255,255,255,0.028);
  --card-hover: rgba(255,255,255,0.055);
  --border: rgba(255,255,255,0.07);
  --border-glow: rgba(255,200,0,0.25);
  --gold: #FFD700;
  --gold2: #FFA500;
  --cyan: #00f0ff;
  --blue: #3b82f6;
  --green: #22c55e;
  --red: #ef4444;
  --text: #e8eaf0;
  --muted: #64748b;
  --font-display: 'Bebas Neue', sans-serif;
  --font-body: 'Rajdhani', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html { scroll-behavior: smooth; }

body {
  font-family: var(--font-body);
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  overflow-x: hidden;
  font-size: 16px;
  line-height: 1.5;
}

/* ── CANVAS BG ── */
#bgCanvas {
  position: fixed; top: 0; left: 0;
  width: 100%; height: 100%;
  z-index: -2; pointer-events: none;
}

/* ── HEADER ── */
header {
  display: flex; align-items: center;
  justify-content: space-between;
  padding: 14px 36px;
  background: rgba(6,8,16,0.88);
  backdrop-filter: blur(18px);
  border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 200;
}

.logo {
  font-family: var(--font-display);
  font-size: 28px; letter-spacing: 2px;
  background: linear-gradient(90deg, var(--gold), var(--gold2), var(--cyan));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.logo span { font-size: 13px; display: block; font-family: var(--font-mono); color: var(--muted); -webkit-text-fill-color: var(--muted); letter-spacing: 4px; margin-top: -4px; }

.header-right { display: flex; align-items: center; gap: 20px; }

.live-badge {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 16px; border-radius: 999px;
  background: rgba(34,197,94,0.1);
  border: 1px solid rgba(34,197,94,0.3);
  font-family: var(--font-mono); font-size: 12px; font-weight: 700;
  color: var(--green); letter-spacing: 2px;
}
.live-badge.warn {
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.45);
  color: #f59e0b;
}
.live-badge.warn .live-dot {
  background: #f59e0b;
  box-shadow: 0 0 8px #f59e0b;
}
.live-badge.critical {
  background: rgba(239, 68, 68, 0.16);
  border-color: rgba(239, 68, 68, 0.5);
  color: #ef4444;
}
.live-badge.critical .live-dot {
  background: #ef4444;
  box-shadow: 0 0 8px #ef4444;
}
.live-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
  animation: livePulse 1.4s ease-in-out infinite;
}
@keyframes livePulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

.match-selector {
  background: var(--card); border: 1px solid var(--border);
  color: var(--text); padding: 7px 14px; border-radius: 8px;
  font-family: var(--font-body); font-size: 15px; cursor: pointer;
  outline: none;
}
.match-selector:focus { border-color: var(--gold); }

.view-tabs {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 999px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.02);
}

.prev-filter {
  background: var(--card);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 6px 10px;
  border-radius: 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 1px;
  outline: none;
}

.prev-filter:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.export-btn {
  border: 1px solid var(--border);
  background: rgba(34, 197, 94, 0.14);
  color: #86efac;
  padding: 6px 10px;
  border-radius: 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 1px;
  cursor: pointer;
}

.export-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.view-tab {
  border: 0;
  background: transparent;
  color: var(--muted);
  padding: 6px 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 1px;
  cursor: pointer;
}

.view-tab.active {
  background: rgba(255, 215, 0, 0.18);
  color: var(--gold);
}

/* ── LAYOUT ── */
.main-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 340px;
  grid-template-rows: auto auto auto;
  gap: 20px;
  padding: 24px 28px;
  max-width: 1700px;
  margin: 0 auto;
}

/* ── CARDS ── */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px;
  position: relative;
  overflow: hidden;
  transition: border-color 0.3s, background 0.3s;
}
.card::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, transparent, var(--gold), transparent);
  opacity: 0; transition: opacity 0.3s;
}
.card:hover { background: var(--card-hover); border-color: rgba(255,215,0,0.2); }
.card:hover::before { opacity: 1; }

.card-label {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: 3px;
  color: var(--muted); text-transform: uppercase;
  margin-bottom: 16px;
  display: flex; align-items: center; gap: 10px;
}
.card-label::after {
  content: ''; flex: 1; height: 1px;
  background: var(--border);
}

/* ── API ERROR BANNER ── */
.api-error-banner {
  display: none;
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.4;
}
.api-error-banner.warn {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.4);
  color: #fbbf24;
}
.api-error-banner.critical {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.45);
  color: #f87171;
}

/* ── SCOREBOARD (spans 2 cols) ── */
.card-score { grid-column: 1 / 3; }

.score-inner {
  display: flex; align-items: center;
  justify-content: space-between; gap: 20px;
}

.team-block { text-align: center; flex: 1; }
.team-abbr {
  font-family: var(--font-display);
  font-size: 60px; line-height: 1;
  letter-spacing: 2px;
}
.team-full { font-size: 13px; color: var(--muted); margin-top: 4px; font-family: var(--font-mono); }

.vs-separator {
  display: flex; flex-direction: column;
  align-items: center; gap: 8px;
  flex-shrink: 0;
}
.vs-text { font-family: var(--font-display); font-size: 22px; color: var(--muted); }

.score-center { text-align: center; flex: 2; }
.main-score {
  font-family: var(--font-display);
  font-size: 88px; line-height: 1; letter-spacing: -1px;
  color: #fff;
}
.score-detail {
  display: flex; justify-content: center; gap: 24px;
  margin-top: 8px; font-family: var(--font-mono); font-size: 14px; color: var(--muted);
}
.score-detail .val { color: var(--text); font-weight: 700; }

/* Recent balls */
.recent-balls {
  display: flex; gap: 8px; justify-content: center;
  margin-top: 18px;
}
.ball {
  width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-mono); font-size: 13px; font-weight: 700;
  border: 1.5px solid;
}
.ball-4  { background: rgba(59,130,246,0.15); border-color: var(--blue); color: var(--blue); }
.ball-6  { background: rgba(255,215,0,0.15);  border-color: var(--gold); color: var(--gold); }
.ball-W  { background: rgba(239,68,68,0.15);  border-color: var(--red);  color: var(--red); }
.ball-0  { background: rgba(100,116,139,0.1); border-color: var(--muted); color: var(--muted); }
.ball-nb { background: rgba(168,85,247,0.15); border-color: #a855f7; color: #a855f7; }
.ball-num { background: rgba(34,197,94,0.12); border-color: rgba(34,197,94,0.4); color: var(--green); }

/* ── WIN PROBABILITY BAR ── */
.prob-section { margin-top: 20px; }
.prob-labels { display: flex; justify-content: space-between; margin-bottom: 6px; font-family: var(--font-mono); font-size: 13px; }
.prob-bar-track {
  height: 12px; border-radius: 6px;
  background: rgba(255,255,255,0.05);
  overflow: hidden; position: relative;
}
.prob-fill-t1 {
  height: 100%; border-radius: 6px 0 0 6px;
  transition: width 1.2s cubic-bezier(0.4,0,0.2,1);
  position: absolute; left: 0; top: 0;
}
.prob-fill-t2 {
  height: 100%; border-radius: 0 6px 6px 0;
  transition: width 1.2s cubic-bezier(0.4,0,0.2,1);
  position: absolute; right: 0; top: 0;
}
.prob-numbers { display: flex; justify-content: space-between; margin-top: 6px; font-size: 20px; font-family: var(--font-display); }

/* ── WIN TREND SPARKLINE ── */
.trend-wrap {
  margin-top: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255,255,255,0.02);
}
.trend-title {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--muted);
  margin-bottom: 6px;
}
.trend-svg {
  width: 100%;
  height: 44px;
  display: block;
}
.trend-summary {
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── MOMENTUM CARD ── */
.momentum-ring-container {
  display: flex; justify-content: center; padding: 10px 0;
}
.momentum-ring {
  position: relative; width: 160px; height: 160px;
}
.momentum-ring svg { transform: rotate(-90deg); }
.momentum-ring .ring-bg { fill: none; stroke: rgba(255,255,255,0.06); stroke-width: 10; }
.momentum-ring .ring-fill { fill: none; stroke-width: 10; stroke-linecap: round; transition: stroke-dashoffset 1.5s cubic-bezier(0.4,0,0.2,1); }
.momentum-center {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  text-align: center;
}
.momentum-pct { font-family: var(--font-display); font-size: 36px; line-height: 1; }
.momentum-label { font-size: 11px; color: var(--muted); font-family: var(--font-mono); letter-spacing: 1px; }

.momentum-text { text-align: center; margin-top: 12px; }
.momentum-title { font-size: 15px; font-weight: 600; color: var(--text); }
.momentum-sub { font-family: var(--font-mono); font-size: 11px; color: var(--muted); margin-top: 4px; line-height: 1.4; }

.phase-badges { display: flex; gap: 8px; justify-content: center; margin-top: 12px; flex-wrap: wrap; }
.phase-badge {
  padding: 4px 12px; border-radius: 4px;
  font-family: var(--font-mono); font-size: 11px; letter-spacing: 1px;
  border: 1px solid;
}

/* ── RATES MINI-GRID ── */
.rates-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
.rate-box {
  background: rgba(255,255,255,0.03); border-radius: 10px;
  padding: 12px 14px; text-align: center;
  border: 1px solid var(--border);
}
.rate-val { font-family: var(--font-display); font-size: 28px; color: #fff; }
.rate-lbl { font-family: var(--font-mono); font-size: 10px; letter-spacing: 2px; color: var(--muted); margin-top: 2px; }

/* ── TOOL PANEL (right col, spans rows) ── */
.card-tools { grid-column: 3; grid-row: 1 / 4; display: flex; flex-direction: column; gap: 12px; }

.tool-btn {
  width: 100%;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border);
  color: var(--text); padding: 14px 18px;
  border-radius: 10px;
  font-family: var(--font-body); font-size: 16px; font-weight: 600;
  cursor: pointer; text-align: left;
  display: flex; align-items: center; gap: 12px;
  transition: all 0.2s;
  position: relative; overflow: hidden;
}
.tool-btn::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--gold); opacity: 0; transition: opacity 0.2s;
}
.tool-btn:hover {
  background: rgba(255,215,0,0.08);
  border-color: rgba(255,215,0,0.3);
  transform: translateX(3px);
}
.tool-btn:hover::before { opacity: 1; }
.tool-btn.active {
  background: rgba(255,215,0,0.1);
  border-color: rgba(255,215,0,0.4);
}
.tool-icon { font-size: 20px; flex-shrink: 0; }
.tool-text { display: flex; flex-direction: column; }
.tool-name { font-size: 14px; font-weight: 700; }
.tool-desc { font-size: 11px; color: var(--muted); font-family: var(--font-mono); }

.output-area {
  flex: 1; background: rgba(0,0,0,0.4);
  border: 1px solid var(--border); border-radius: 10px;
  padding: 18px; min-height: 280px;
  font-size: 14px; line-height: 1.65;
  color: #c8d0e0;
  overflow-y: auto;
  font-family: var(--font-mono);
}
.output-area .o-title {
  font-size: 16px; font-weight: 700; font-family: var(--font-body);
  color: var(--gold); margin-bottom: 12px; display: block;
}
.output-area .o-section { color: var(--cyan); font-weight: 700; margin-top: 10px; }
.output-area .o-value { color: var(--text); }
.output-area .o-muted { color: var(--muted); font-size: 12px; }
.output-area .tag {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 700; margin: 2px;
  border: 1px solid;
}
.tag-W { background: rgba(239,68,68,0.12); border-color: var(--red); color: var(--red); }
.tag-L { background: rgba(239,68,68,0.12); border-color: var(--red); color: var(--red); }

/* ── INSIGHTS ROW (spans 2 cols) ── */
.card-insights { grid-column: 1 / 3; }
.insights-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 4px; }
.insight-box {
  background: rgba(255,255,255,0.025); border-radius: 10px;
  padding: 14px 16px; border-left: 3px solid var(--gold);
}
.insight-box.cyan { border-left-color: var(--cyan); }
.insight-box.green { border-left-color: var(--green); }
.insight-head { font-family: var(--font-mono); font-size: 10px; letter-spacing: 2px; color: var(--muted); margin-bottom: 6px; }
.insight-content { font-size: 13px; line-height: 1.5; color: var(--text); }

/* ── NOTIFICATION TOAST ── */
.toast-container {
  position: fixed; top: 80px; right: 24px; z-index: 999;
  display: flex; flex-direction: column; gap: 10px;
}
.toast {
  padding: 12px 18px; border-radius: 10px;
  border: 1px solid;
  font-family: var(--font-mono); font-size: 13px;
  max-width: 340px; line-height: 1.4;
  animation: toastIn 0.4s cubic-bezier(0.175,0.885,0.32,1.275);
  backdrop-filter: blur(12px);
}
.toast.normal { background: rgba(59,130,246,0.1); border-color: rgba(59,130,246,0.3); color: #93c5fd; }
.toast.high    { background: rgba(255,165,0,0.1);  border-color: rgba(255,165,0,0.3);  color: #fbbf24; }
.toast.critical{ background: rgba(239,68,68,0.1);  border-color: rgba(239,68,68,0.3);  color: #f87171; }
@keyframes toastIn {
  from { opacity:0; transform: translateX(40px); }
  to   { opacity:1; transform: translateX(0); }
}

/* ── LAST 5 OVERS BAR ── */
.over-bars { display: flex; align-items: flex-end; gap: 6px; height: 60px; margin-top: 12px; }
.over-bar-wrap { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; height: 100%; justify-content: flex-end; }
.over-bar {
  width: 100%; border-radius: 3px 3px 0 0;
  transition: height 1s cubic-bezier(0.4,0,0.2,1);
  min-height: 4px;
}
.over-bar-lbl { font-family: var(--font-mono); font-size: 11px; color: var(--muted); }
.over-bar-val { font-family: var(--font-mono); font-size: 12px; font-weight: 700; }

/* ── LOADER ── */
.spinner {
  width: 20px; height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--gold);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── TEAM TOGGLE (stats) ── */
.team-toggle { display: flex; gap: 8px; margin-bottom: 16px; }
.team-toggle-btn {
  padding: 6px 16px; border-radius: 6px;
  font-family: var(--font-body); font-size: 14px; font-weight: 700;
  cursor: pointer; border: 1px solid var(--border);
  background: var(--card); color: var(--muted);
  transition: all 0.2s;
}
.team-toggle-btn.active {
  background: rgba(255,215,0,0.15); border-color: var(--gold); color: var(--gold);
}

/* ── VENUE WEATHER ── */
.venue-row { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.weather-item { text-align: center; }
.weather-icon { font-size: 28px; }
.weather-val { font-family: var(--font-mono); font-size: 13px; color: var(--text); }
.weather-key { font-size: 10px; color: var(--muted); letter-spacing: 1px; }

/* ── SCROLL ── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── FADE IN ── */
.fadein { animation: fadeUp 0.6s ease both; }
@keyframes fadeUp { from { opacity:0; transform: translateY(12px); } to { opacity:1; transform:none; } }

.stagger-1 { animation-delay: 0.05s; }
.stagger-2 { animation-delay: 0.1s; }
.stagger-3 { animation-delay: 0.15s; }
.stagger-4 { animation-delay: 0.2s; }

/* ── RESPONSIVE ── */
@media (max-width: 1200px) {
  .main-grid { grid-template-columns: 1fr 1fr; }
  .card-tools { grid-column: 1 / 3; grid-row: auto; display: grid; grid-template-columns: 1fr 1fr; }
  .card-insights { grid-column: 1 / 3; }
}
@media (max-width: 760px) {
  .main-grid { grid-template-columns: 1fr; padding: 12px; }
  .card-score { grid-column: 1; }
  .card-tools { grid-column: 1; grid-template-columns: 1fr 1fr; }
  .card-insights { grid-column: 1; }
  .insights-grid { grid-template-columns: 1fr; }
  .main-score { font-size: 64px; }
  .team-abbr { font-size: 42px; }
  header { padding: 12px 16px; }
}
</style>
</head>
<body>

<canvas id="bgCanvas"></canvas>
<div class="toast-container" id="toastContainer"></div>

<header>
  <div class="logo">
    IPL INTELLIGENCE
    <span>AGENTIC AI DASHBOARD</span>
  </div>
  <div class="header-right">
    <select class="match-selector" id="matchSelector" onchange="changeMatch(this.value)">
      <option value="latest">Latest IPL Match</option>
      <option value="MI vs CSK">MI vs CSK</option>
      <option value="RCB vs KKR">RCB vs KKR</option>
      <option value="SRH vs DC">SRH vs DC</option>
      <option value="RR vs PBKS">RR vs PBKS</option>
      <option value="LSG vs GT">LSG vs GT</option>
    </select>
    <div class="view-tabs">
      <button class="view-tab active" id="tabLive" onclick="switchView('live')">LIVE</button>
      <button class="view-tab" id="tabPrevious" onclick="switchView('previous')">PREVIOUS</button>
    </div>
    <select id="previousTeamFilter" class="prev-filter" onchange="onPreviousFilterChange()" disabled>
      <option value="">ALL TEAMS</option>
      <option value="MI">MI</option>
      <option value="CSK">CSK</option>
      <option value="RCB">RCB</option>
      <option value="KKR">KKR</option>
      <option value="SRH">SRH</option>
      <option value="DC">DC</option>
      <option value="RR">RR</option>
      <option value="PBKS">PBKS</option>
      <option value="LSG">LSG</option>
      <option value="GT">GT</option>
    </select>
    <button id="exportCsvBtn" class="export-btn" onclick="exportPreviousCSV()" disabled>EXPORT CSV</button>
    <div class="live-badge" id="liveBadge"><div class="live-dot"></div> LIVE</div>
    <div id="syncStatus" style="font-family:var(--font-mono);font-size:11px;color:var(--muted)">SYNCING...</div>
  </div>
</header>

<div class="main-grid">

  <!-- ── SCOREBOARD ── -->
  <div class="card card-score fadein stagger-1">
    <div class="card-label">Live Scoreboard</div>
    <div id="apiErrorBanner" class="api-error-banner"></div>
    <div class="score-inner">

      <div class="team-block">
        <div class="team-abbr" id="team1Name" style="color:#00BFFF">MI</div>
        <div class="team-full" id="team1Full">Mumbai Indians</div>
        <div style="margin-top:12px; font-family:var(--font-display); font-size:20px; color:var(--muted)" id="t1WinPct">50%</div>
        <div style="font-family:var(--font-mono);font-size:10px;color:var(--muted);letter-spacing:2px">WIN PROB</div>
      </div>

      <div class="score-center">
        <div class="main-score" id="mainScore">0/0</div>
        <div class="score-detail">
          <span><span class="val" id="oversVal">0.0</span> OV</span>
          <span>CRR <span class="val" id="crrVal">0.00</span></span>
          <span>RRR <span class="val" id="rrrVal">0.00</span></span>
        </div>
        <div style="font-family:var(--font-mono);font-size:12px;color:var(--muted);margin-top:6px" id="venueText">📍 Stadium</div>
        <div class="recent-balls" id="recentBalls"></div>
        <div style="font-family:var(--font-mono);font-size:12px;color:var(--muted);margin-top:8px" id="partnershipText"></div>
        <div style="font-family:var(--font-body);font-size:14px;color:var(--gold);margin-top:8px;font-weight:700" id="turningPointHighlight">🔍 Turning point: —</div>
      </div>

      <div class="team-block">
        <div class="team-abbr" id="team2Name" style="color:#FDB913">CSK</div>
        <div class="team-full" id="team2Full">Chennai Super Kings</div>
        <div style="margin-top:12px; font-family:var(--font-display); font-size:20px; color:var(--muted)" id="t2WinPct">50%</div>
        <div style="font-family:var(--font-mono);font-size:10px;color:var(--muted);letter-spacing:2px">WIN PROB</div>
      </div>

    </div>

    <!-- Win Probability Bar -->
    <div class="prob-section">
      <div class="prob-labels">
        <span id="probLabel1" style="color:#00BFFF; font-weight:700">MI — 50%</span>
        <span style="color:var(--muted)">Win Probability</span>
        <span id="probLabel2" style="color:#FDB913; font-weight:700">50% — CSK</span>
      </div>
      <div class="prob-bar-track">
        <div class="prob-fill-t1" id="probFill1" style="width:50%; background: linear-gradient(90deg, #004BA0, #00BFFF)"></div>
        <div class="prob-fill-t2" id="probFill2" style="width:50%; background: linear-gradient(90deg, #FDB913, #FF6B00)"></div>
      </div>
      <div class="prob-numbers">
        <span id="probNum1">50</span>
        <span style="color:var(--muted); font-size:14px; font-family:var(--font-mono); align-self:center" id="confidenceLabel">CONFIDENCE: LOW</span>
        <span id="probNum2">50</span>
      </div>
      <!-- Win probability trend sparkline -->
      <div class="trend-wrap">
        <div class="trend-title">WIN PROBABILITY TREND</div>
        <svg class="trend-svg" id="probTrendSvg" viewBox="0 0 300 44" preserveAspectRatio="none"></svg>
        <div class="trend-summary" id="probTrend">Trend: loading…</div>
      </div>
    </div>
  </div>

  <!-- ── MOMENTUM ── -->
  <div class="card fadein stagger-2">
    <div class="card-label">Match Momentum & Pressure</div>

    <div class="momentum-ring-container">
      <div class="momentum-ring">
        <svg width="160" height="160" viewBox="0 0 160 160">
          <circle class="ring-bg" cx="80" cy="80" r="65"/>
          <circle class="ring-fill" id="momentumRing" cx="80" cy="80" r="65"
            stroke="var(--gold)"
            stroke-dasharray="408.4"
            stroke-dashoffset="204.2"/>
        </svg>
        <div class="momentum-center">
          <div class="momentum-pct" id="pressureIdx" style="color:var(--gold)">50</div>
          <div class="momentum-label">PRESSURE</div>
        </div>
      </div>
    </div>

    <div class="momentum-text">
      <div class="momentum-title" id="momentumTitle">Evenly Poised</div>
      <div class="momentum-sub" id="momentumSub">CRR 0.00 vs RRR 0.00 | 0 wickets down</div>
    </div>

    <div class="phase-badges" id="phaseBadges">
      <span class="phase-badge" style="color:var(--muted); border-color:var(--border)" id="phaseBadge">PHASE</span>
      <span class="phase-badge" style="color:var(--muted); border-color:var(--border)" id="pressureBadge">MEDIUM</span>
    </div>

    <div class="rates-grid">
      <div class="rate-box">
        <div class="rate-val" id="crrBox">0.00</div>
        <div class="rate-lbl">CURR. RR</div>
      </div>
      <div class="rate-box">
        <div class="rate-val" id="rrrBox" style="color:var(--gold2)">0.00</div>
        <div class="rate-lbl">REQ. RR</div>
      </div>
    </div>

    <!-- Last 5 overs bars -->
    <div class="card-label" style="margin-top:18px; margin-bottom:0">Last 5 Overs</div>
    <div class="over-bars" id="overBars"></div>

  </div>

  <!-- ── TOOLS PANEL ── -->
  <div class="card card-tools fadein stagger-3">
    <div class="card-label">AI Agent Tools</div>

    <button class="tool-btn" onclick="runTool('commentary')">
      <span class="tool-icon">🎙️</span>
      <span class="tool-text">
        <span class="tool-name">Live Commentary</span>
        <span class="tool-desc">Ball-by-ball narrative</span>
      </span>
    </button>
    <button class="tool-btn" onclick="runTool('strategy')">
      <span class="tool-icon">🧠</span>
      <span class="tool-text">
        <span class="tool-name">Suggest Strategy</span>
        <span class="tool-desc">Batting & bowling tactics</span>
      </span>
    </button>
    <button class="tool-btn" onclick="runTool('stats')">
      <span class="tool-icon">📊</span>
      <span class="tool-text">
        <span class="tool-name">Team Stats</span>
        <span class="tool-desc">Players & form data</span>
      </span>
    </button>
    <button class="tool-btn" onclick="runTool('h2h')">
      <span class="tool-icon">⚔️</span>
      <span class="tool-text">
        <span class="tool-name">Head-to-Head</span>
        <span class="tool-desc">Historical rivalry data</span>
      </span>
    </button>
    <button class="tool-btn" onclick="runTool('venue')">
      <span class="tool-icon">🏟️</span>
      <span class="tool-text">
        <span class="tool-name">Pitch & Weather</span>
        <span class="tool-desc">Venue conditions & dew</span>
      </span>
    </button>
    <button class="tool-btn" onclick="runTool('postmatch')">
      <span class="tool-icon">🏆</span>
      <span class="tool-text">
        <span class="tool-name">Post-Match Report</span>
        <span class="tool-desc">Full match summary</span>
      </span>
    </button>

    <button class="tool-btn" onclick="runTool('history')">
      <span class="tool-icon">🕘</span>
      <span class="tool-text">
        <span class="tool-name">Previous Match Stats</span>
        <span class="tool-desc">Completed IPL match numbers</span>
      </span>
    </button>

    <button class="tool-btn" onclick="runTool('fullAnalysis')">
      <span class="tool-icon">⚡</span>
      <span class="tool-text">
        <span class="tool-name">Run Full Analysis</span>
        <span class="tool-desc">One-click: insights, strategy, commentary</span>
      </span>
    </button>

    <div class="output-area" id="toolOutput">
      <span class="o-title">IPL Agentic Intelligence v2.0</span>
      <span style="color:var(--muted)">Powered by Google ADK · gemini-flash-latest · Real-time data</span>
      <br><br>
      <span class="o-section">● ACTIVE TOOLS</span><br>
      <span class="o-muted">→ get_live_match_data (with CricAPI)<br>→ google_search (real-time IPL news)<br>→ analyze_momentum<br>→ predict_win_probability<br>→ generate_key_insights<br>→ suggest_strategy<br>→ generate_commentary<br>→ get_head_to_head<br>→ get_pitch_and_weather<br>→ +5 more tools</span>
      <br><br>
      <span class="o-muted">Click any tool button above to trigger the agent analytics pipeline.</span>
    </div>
  </div>

  <!-- ── KEY INSIGHTS ── -->
  <div class="card card-insights fadein stagger-4">
    <div class="card-label">Agentic Key Insights</div>
    <div class="insights-grid" id="insightsGrid">
      <div class="insight-box">
        <div class="insight-head">TURNING POINTS</div>
        <div class="insight-content" id="insightTP">Loading...</div>
      </div>
      <div class="insight-box cyan">
        <div class="insight-head">PRESSURE MOMENTS</div>
        <div class="insight-content" id="insightPM">Loading...</div>
      </div>
      <div class="insight-box green">
        <div class="insight-head">MOMENTUM SHIFTS</div>
        <div class="insight-content" id="insightMS">Loading...</div>
      </div>
    </div>
  </div>

</div>

<script>
// ── CANVAS PARTICLE BG ──
const canvas = document.getElementById('bgCanvas');
const ctx = canvas.getContext('2d');
let W, H, particles = [];

function initCanvas() {
  W = canvas.width = window.innerWidth;
  H = canvas.height = window.innerHeight;
}

function createParticles() {
  particles = [];
  const count = Math.floor(W * H / 14000);
  for (let i = 0; i < count; i++) {
    particles.push({
      x: Math.random() * W, y: Math.random() * H,
      r: Math.random() * 1.5 + 0.3,
      vx: (Math.random() - 0.5) * 0.15,
      vy: (Math.random() - 0.5) * 0.15,
      a: Math.random() * 0.4 + 0.05
    });
  }
}

function drawBg() {
  ctx.clearRect(0, 0, W, H);
  // Grid
  ctx.strokeStyle = 'rgba(255,255,255,0.018)';
  ctx.lineWidth = 1;
  for (let x = 0; x < W; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
  for (let y = 0; y < H; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
  // Glow
  const grd = ctx.createRadialGradient(W/2, H/2, 0, W/2, H/2, W*0.7);
  grd.addColorStop(0, 'rgba(255,200,0,0.04)');
  grd.addColorStop(1, 'transparent');
  ctx.fillStyle = grd; ctx.fillRect(0, 0, W, H);
  // Stars
  particles.forEach(p => {
    p.x += p.vx; p.y += p.vy;
    if (p.x < 0 || p.x > W) p.vx *= -1;
    if (p.y < 0 || p.y > H) p.vy *= -1;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
    ctx.fillStyle = `rgba(255,215,0,${p.a})`;
    ctx.fill();
  });
  requestAnimationFrame(drawBg);
}

window.addEventListener('resize', () => { initCanvas(); createParticles(); });
initCanvas(); createParticles(); drawBg();

// ── STATE ──
let currentMatch = 'latest';
let currentTeam1 = 'MI', currentTeam2 = 'CSK';
let lastData = null;
let currentView = 'live';

function changeMatch(val) { currentMatch = val; syncDashboard(); }

function switchView(view) {
  currentView = view;
  const liveTab = document.getElementById('tabLive');
  const prevTab = document.getElementById('tabPrevious');
  const selector = document.getElementById('matchSelector');
  const prevFilter = document.getElementById('previousTeamFilter');
  const exportBtn = document.getElementById('exportCsvBtn');

  if (view === 'previous') {
    liveTab.classList.remove('active');
    prevTab.classList.add('active');
    selector.disabled = true;
    prevFilter.disabled = false;
    exportBtn.disabled = false;
    runTool('history');
    document.getElementById('syncStatus').textContent = 'PREVIOUS MODE';
  } else {
    prevTab.classList.remove('active');
    liveTab.classList.add('active');
    selector.disabled = false;
    prevFilter.disabled = true;
    exportBtn.disabled = true;
    syncDashboard();
  }
}

function onPreviousFilterChange() {
  if (currentView === 'previous') {
    runTool('history');
  }
}

function csvEscape(value) {
  const raw = String(value ?? '');
  return '"' + raw.replace(/"/g, '""') + '"';
}

function buildPreviousCsv(matches) {
  const header = ['Match', 'Date', 'Venue', 'Result', 'Score Summary'];
  const lines = [header.map(csvEscape).join(',')];
  (matches || []).forEach(m => {
    lines.push([
      m.match,
      m.date,
      m.venue,
      m.status,
      (m.score_summary || []).join(' | ')
    ].map(csvEscape).join(','));
  });
  return lines.join('\n');
}

async function exportPreviousCSV() {
  try {
    const teamFilter = document.getElementById('previousTeamFilter')?.value || '';
    const d = await (await fetch(`/api/previous-stats?team=${encodeURIComponent(teamFilter)}`)).json();
    const matches = d.matches || [];
    if (!matches.length) {
      showToast('No previous matches to export.', 'high');
      return;
    }

    const csv = buildPreviousCsv(matches);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const suffix = teamFilter || 'ALL';
    a.href = url;
    a.download = `ipl_previous_matches_${suffix}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(`CSV exported (${matches.length} matches).`, 'normal');
  } catch (e) {
    showToast('CSV export failed.', 'critical');
  }
}

// ── TOAST ──
function showToast(msg, type='normal') {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.style.opacity = '0', 4000);
  setTimeout(() => t.remove(), 4500);
}

// ── BALL RENDERING ──
function renderBall(b) {
  let cls = 'ball-num';
  if (b === '4') cls = 'ball-4';
  else if (b === '6') cls = 'ball-6';
  else if (b === 'W') cls = 'ball-W';
  else if (b === '0' || b === '.') cls = 'ball-0';
  else if (b === 'nb' || b === 'wd') cls = 'ball-nb';
  return `<div class="ball ${cls}">${b}</div>`;
}

// ── OVER BARS ──
function renderOverBars(last5) {
  const c = document.getElementById('overBars');
  if (!last5 || !last5.length) { c.innerHTML = '<span style="color:var(--muted);font-size:12px;font-family:var(--font-mono)">No data</span>'; return; }
  const max = Math.max(...last5, 1);
  c.innerHTML = last5.map((v, i) => {
    const pct = Math.round((v / max) * 100);
    const col = v >= 12 ? 'var(--gold)' : v >= 9 ? 'var(--cyan)' : v >= 7 ? 'var(--green)' : 'var(--muted)';
    return `<div class="over-bar-wrap">
      <div class="over-bar-val" style="color:${col}">${v}</div>
      <div class="over-bar" style="height:${pct}%; background:${col}; opacity:0.7"></div>
      <div class="over-bar-lbl">O${i+1}</div>
    </div>`;
  }).join('');
}

// ── MOMENTUM RING ──
function setMomentumRing(pct, color) {
  const ring = document.getElementById('momentumRing');
  const circ = 408.4;
  const offset = circ - (pct / 100) * circ;
  ring.style.strokeDashoffset = offset;
  ring.style.stroke = color;
  document.getElementById('pressureIdx').style.color = color;
}

function renderProbSparkline(trend, c1, c2) {
  const svg = document.getElementById('probTrendSvg');
  if (!svg) return;

  if (!trend || trend.length < 2) {
    svg.innerHTML = '<line x1="0" y1="22" x2="300" y2="22" stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3 4" />';
    return;
  }

  const width = 300;
  const height = 44;
  const padX = 6;
  const padY = 4;
  const w = width - padX * 2;
  const h = height - padY * 2;
  const n = trend.length;

  function xAt(i) {
    if (n === 1) return padX;
    return padX + (i / (n - 1)) * w;
  }

  function yForProb(p) {
    const clamped = Math.max(0, Math.min(100, Number(p || 0)));
    return padY + ((100 - clamped) / 100) * h;
  }

  const p1Points = trend.map((t, i) => `${xAt(i).toFixed(1)},${yForProb(t.p1).toFixed(1)}`).join(' ');
  const p2Points = trend.map((t, i) => `${xAt(i).toFixed(1)},${yForProb(t.p2).toFixed(1)}`).join(' ');

  const last1 = trend[n - 1];
  const cx1 = xAt(n - 1).toFixed(1);
  const cy1 = yForProb(last1.p1).toFixed(1);
  const cy2 = yForProb(last1.p2).toFixed(1);

  svg.innerHTML = `
    <line x1="0" y1="22" x2="300" y2="22" stroke="rgba(255,255,255,0.1)" stroke-width="1" />
    <polyline fill="none" stroke="${c1.secondary || '#00BFFF'}" stroke-width="2.2" points="${p1Points}" />
    <polyline fill="none" stroke="${c2.secondary || '#FDB913'}" stroke-width="2.2" points="${p2Points}" />
    <circle cx="${cx1}" cy="${cy1}" r="2.8" fill="${c1.secondary || '#00BFFF'}" />
    <circle cx="${cx1}" cy="${cy2}" r="2.8" fill="${c2.secondary || '#FDB913'}" />
  `;
}

// ── DASHBOARD SYNC ──
async function syncDashboard() {
  if (currentView !== 'live') return;
  document.getElementById('syncStatus').textContent = 'SYNCING...';
  try {
    const res = await fetch(`/api/dashboard?match_id=${encodeURIComponent(currentMatch)}`);
    const d = await res.json();
    lastData = d;

    const m = d.match;
    currentTeam1 = m.team1; currentTeam2 = m.team2;

    // Live-data health indicator (prominent when backend is on fallback/mock)
    const badge = document.getElementById('liveBadge');
    const apiErrorBanner = document.getElementById('apiErrorBanner');
    badge.classList.remove('warn', 'critical');
    if (m.api_error) {
      const err = String(m.api_error).toLowerCase();
      const severity = (err.includes('blocked') || err.includes('invalid') || err.includes('forbidden')) ? 'critical' : 'warn';
      badge.classList.add(severity);
      badge.innerHTML = `<div class="live-dot"></div> ${severity === 'critical' ? 'LIVE DEGRADED' : 'LIVE WARNING'}`;
      apiErrorBanner.className = `api-error-banner ${severity}`;
      apiErrorBanner.style.display = 'block';
      apiErrorBanner.innerHTML = `⚠️ Live API issue detected: ${m.api_error}. Showing fallback/mock stream for demo continuity.`;
    } else {
      badge.innerHTML = '<div class="live-dot"></div> LIVE';
      apiErrorBanner.style.display = 'none';
      apiErrorBanner.textContent = '';
    }

    // Teams
    document.getElementById('team1Name').textContent = currentTeam1;
    document.getElementById('team2Name').textContent = currentTeam2;
    document.getElementById('team1Full').textContent = m.team1_full || currentTeam1;
    document.getElementById('team2Full').textContent = m.team2_full || currentTeam2;

    // Apply team colors
    const c1 = d.team1_colors, c2 = d.team2_colors;
    document.getElementById('team1Name').style.color = c1.secondary || '#00BFFF';
    document.getElementById('team2Name').style.color = c2.secondary || '#FDB913';
    document.getElementById('probFill1').style.background = `linear-gradient(90deg, ${c1.primary||'#004BA0'}, ${c1.secondary||'#00BFFF'})`;
    document.getElementById('probFill2').style.background = `linear-gradient(90deg, ${c2.secondary||'#FDB913'}, ${c2.primary||'#FF6B00'})`;

    // Score
    document.getElementById('mainScore').textContent = `${m.score}/${m.wickets}`;
    document.getElementById('oversVal').textContent = m.overs;
    document.getElementById('crrVal').textContent = (m.run_rate||0).toFixed(2);
    document.getElementById('rrrVal').textContent = (m.required_run_rate||0).toFixed(2);
    document.getElementById('venueText').textContent = '📍 ' + (m.venue || 'Stadium');

    // Recent balls
    const balls = m.recent_balls || [];
    document.getElementById('recentBalls').innerHTML = balls.map(renderBall).join('');

    // Partnership
    const p = m.partnership;
    if (p) document.getElementById('partnershipText').textContent = `🤝 ${p.batsman1} & ${p.batsman2} (${p.runs} runs)`;

    // Win probability
    const p1 = d.win_prob.probability_team1, p2 = d.win_prob.probability_team2;
    document.getElementById('probFill1').style.width = `${p1}%`;
    document.getElementById('probFill2').style.width = `${p2}%`;
    document.getElementById('probLabel1').textContent = `${currentTeam1} — ${p1}%`;
    document.getElementById('probLabel2').textContent = `${p2}% — ${currentTeam2}`;
    document.getElementById('probNum1').textContent = p1;
    document.getElementById('probNum2').textContent = p2;
    document.getElementById('t1WinPct').textContent = `${p1}%`;
    document.getElementById('t2WinPct').textContent = `${p2}%`;
    document.getElementById('t1WinPct').style.color = c1.secondary || '#00BFFF';
    document.getElementById('t2WinPct').style.color = c2.secondary || '#FDB913';
    document.getElementById('confidenceLabel').textContent = `CONFIDENCE: ${(d.win_prob.confidence||'LOW').toUpperCase()}`;

    // Win-prob trend render (simple text list)
    const trendEl = document.getElementById('probTrend');
    const trend = d.win_prob_trend || [];
    if (trend && trend.length) {
      trendEl.innerHTML = 'Trend: ' + trend.map(t => `Over ${t.overs||'-'} ${t.p1}%`).join(' · ');
      renderProbSparkline(trend, c1, c2);
    } else {
      trendEl.innerHTML = 'Trend: no recent samples';
      renderProbSparkline([], c1, c2);
    }

    // Momentum
    const mom = d.momentum;
    const pressureIdx = mom.pressure_index || 50;
    document.getElementById('pressureIdx').textContent = Math.round(pressureIdx);
    const momColor = pressureIdx > 70 ? '#ef4444' : pressureIdx > 50 ? '#f97316' : pressureIdx > 30 ? '#eab308' : '#22c55e';
    setMomentumRing(pressureIdx, momColor);
    document.getElementById('momentumTitle').textContent = mom.momentum || 'Evenly Poised';
    document.getElementById('momentumSub').textContent = mom.reason || '';
    document.getElementById('crrBox').textContent = (m.run_rate||0).toFixed(2);
    document.getElementById('rrrBox').textContent = (m.required_run_rate||0).toFixed(2);

    // Phase badge
    const phase = mom.phase || 'middle';
    const pBadge = document.getElementById('phaseBadge');
    const pColors = { powerplay: '#22c55e', middle: '#eab308', 'death overs': '#ef4444' };
    pBadge.textContent = phase.toUpperCase();
    pBadge.style.color = pColors[phase] || 'var(--muted)';
    pBadge.style.borderColor = pColors[phase] || 'var(--border)';
    const pressBadge = document.getElementById('pressureBadge');
    pressBadge.textContent = (mom.pressure_level || 'MEDIUM').toUpperCase();
    pressBadge.style.color = momColor;
    pressBadge.style.borderColor = momColor;

    // Over bars
    renderOverBars(m.last_5_overs || mom.last_5_overs || []);

    // Insights
    const ai = d.all_insights;
    if (ai) {
      document.getElementById('insightTP').innerHTML = (ai.turning_points || []).map(t => `• ${t}`).join('<br>');
      document.getElementById('insightPM').innerHTML = (ai.pressure_moments || []).map(t => `• ${t}`).join('<br>');
      document.getElementById('insightMS').innerHTML = (ai.momentum_shifts || []).map(t => `• ${t}`).join('<br>');
    }
    if (d.insight) document.getElementById('insightTP').innerHTML = `<strong>→ ${d.insight}</strong><br>` + document.getElementById('insightTP').innerHTML;

    // Prominent turning point highlight
    const tpEl = document.getElementById('turningPointHighlight');
    if (d.insight) tpEl.innerHTML = `🔥 Turning Point: ${d.insight}`;
    else if (ai && ai.turning_points && ai.turning_points.length) tpEl.innerHTML = `🔥 Turning Point: ${ai.turning_points[0]}`;
    else tpEl.innerHTML = '🔍 Turning point: analyzing...';

    // Notifications
    const notifs = d.notifications;
    if (notifs && notifs.alerts) {
      notifs.alerts.forEach(a => showToast(a, notifs.priority || 'normal'));
    }

    if (m.api_error) {
      showToast(`Live API issue: ${m.api_error}`, 'critical');
    }

    document.getElementById('syncStatus').textContent = `↺ ${new Date().toLocaleTimeString()}`;
  } catch(e) {
    console.error('Sync error', e);
    document.getElementById('syncStatus').textContent = '✗ ERROR';
  }
}

// ── TOOL RUNNER ──
async function runTool(tool) {
  const out = document.getElementById('toolOutput');
  document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
  if (typeof event !== 'undefined' && event && event.currentTarget) {
    event.currentTarget.classList.add('active');
  }

  out.innerHTML = `<span class="o-title">Running tool: ${tool}...</span><br><div class="spinner"></div>`;

  try {
    if (tool === 'commentary') {
      const d = await (await fetch(`/api/commentary?match_id=${encodeURIComponent(currentMatch)}`)).json();
      out.innerHTML = `<span class="o-title">🎙️ Live Commentary</span>
<span class="o-section">● MAIN COMMENTARY</span><br>
<span class="o-value">${d.commentary}</span><br><br>
<span class="o-section">● BALL-BY-BALL</span><br>
<span class="o-muted">${d.ball_by_ball || ''}</span><br><br>
<span class="o-section">● ATMOSPHERE</span><br>
<span class="o-value">${d.atmosphere || 'Stadium buzzing!'}</span>`;

    } else if (tool === 'strategy') {
      const d = await (await fetch(`/api/strategy?match_id=${encodeURIComponent(currentMatch)}`)).json();
      const fields = (d.field_placements || []).map(f => `  ▸ ${f}`).join('\n');
      out.innerHTML = `<span class="o-title">🧠 AI Strategy Advisor</span>
<span class="o-section">● MATCH PHASE: ${(d.phase||'').toUpperCase()}</span><br>
<span class="o-muted">${d.match_situation || ''}</span><br><br>
<span class="o-section">🏏 BATTING STRATEGY</span><br>
<span class="o-value">${d.batting_strategy}</span><br><br>
<span class="o-section">🎳 BOWLING STRATEGY</span><br>
<span class="o-value">${d.bowling_strategy}</span><br><br>
<span class="o-section">🎯 FIELD PLACEMENTS</span><br>
<span class="o-muted">${fields}</span>`;

    } else if (tool === 'stats') {
      const d = await (await fetch(`/api/stats/${currentTeam1}`)).json();
      const d2 = await (await fetch(`/api/stats/${currentTeam2}`)).json();
      const form1 = d.form, p1 = d.players;
      const recent1 = (form1.recent||[]).map(r => `<span class="tag tag-${r}">${r}</span>`).join('');
      const batsmen1 = (p1.top_batsmen||[]).map(b => `  ▸ ${typeof b==='object'?`${b.name} — Avg ${b.avg}, SR ${b.sr}, ${b.runs} runs`:b}`).join('\n');
      const bowlers1 = (p1.top_bowlers||[]).map(b => `  ▸ ${typeof b==='object'?`${b.name} — Eco ${b.eco}, ${b.wkts} wkts`:b}`).join('\n');
      out.innerHTML = `<span class="o-title">📊 ${currentTeam1} vs ${currentTeam2} — Pre-Match Stats</span>
<span class="o-section">● ${currentTeam1} FORM (NRR: ${form1.nrr||0}, P${form1.position||'?'})</span><br>
${recent1} | ${form1.wins}W ${form1.losses}L | Avg Score: ${form1.avg_score}<br><br>
<span class="o-section">🏏 TOP BATSMEN</span><br>
<span class="o-muted">${batsmen1}</span><br><br>
<span class="o-section">🎳 KEY BOWLERS</span><br>
<span class="o-muted">${bowlers1}</span><br><br>
<span class="o-section">⭐ IMPACT PLAYERS</span><br>
<span class="o-value">${(p1.impact_players||[]).join('<br>')}</span>`;

    } else if (tool === 'h2h') {
      const d = await (await fetch(`/api/h2h/${currentTeam1}/${currentTeam2}`)).json();
      const results = (d.last_5_results||[]).map(r => `<span class="tag tag-${r.includes('W')?'W':'L'}">${r}</span>`).join(' ');
      out.innerHTML = `<span class="o-title">⚔️ ${currentTeam1} vs ${currentTeam2} Head-to-Head</span>
<span class="o-section">● ${d.rivalry_label||'RIVALRY'}</span><br><br>
<span class="o-section">TOTAL MATCHES</span><br>
<span class="o-value" style="font-size:32px;font-family:var(--font-display)">${d.total_matches||0}</span><br><br>
<span class="o-section">WIN RECORD</span><br>
<span style="color:#00BFFF">${currentTeam1}: ${d.team1_wins} wins</span> &nbsp;|&nbsp; <span style="color:#FDB913">${currentTeam2}: ${d.team2_wins} wins</span><br><br>
<span class="o-section">LAST 5 RESULTS</span><br>
${results}<br><br>
<span class="o-section">HIGHEST SCORES</span><br>
<span class="o-muted">${d.highest_score||'N/A'}</span>`;

    } else if (tool === 'venue') {
      const venue = lastData?.match?.venue || 'Wankhede';
      const d = await (await fetch(`/api/venue?venue=${encodeURIComponent(venue)}`)).json();
      const w = d.weather || {};
      out.innerHTML = `<span class="o-title">🏟️ Pitch & Weather — ${venue}</span>
<span class="o-section">● PITCH REPORT</span><br>
<span class="o-value">${d.pitch_type}</span><br><br>
<span class="o-section">☁️ WEATHER</span><br>
<span class="o-value">${w.condition||'Clear'} · ${w.temp||'29°C'} · Humidity: ${w.humidity||'65%'}</span><br><br>
<span class="o-section">💧 DEW FACTOR</span><br>
<span class="o-value">${d.dew_factor}</span><br><br>
<span class="o-section">🪙 TOSS RECOMMENDATION</span><br>
<span style="color:var(--gold); font-weight:700">${d.toss_recommendation}</span><br><br>
<span class="o-section">📐 BOUNDARY SIZES</span><br>
<span class="o-muted">${d.boundary_sizes||'Standard'}</span><br>
<span class="o-section">📈 AVG FIRST INNINGS</span><br>
<span class="o-value" style="font-size:28px;font-family:var(--font-display)">${d.avg_first_innings_score||175}</span>`;

    } else if (tool === 'postmatch') {
      const d = await (await fetch(`/api/post-match?match_id=${encodeURIComponent(currentMatch)}`)).json();
      const best = (d.best_players||[]).map(b => `  🏅 ${b}`).join('\n');
      out.innerHTML = `<span class="o-title">🏆 Post-Match Report</span>
<span class="o-section" style="font-size:20px;font-family:var(--font-display)">🎉 ${d.verdict||''}</span><br><br>
<span class="o-section">● MATCH NARRATIVE</span><br>
<span class="o-value">${d.highlights}</span><br><br>
<span class="o-section">📌 TURNING POINT</span><br>
<span class="o-value">${d.turning_point}</span><br><br>
<span class="o-section">🏅 BEST PERFORMERS</span><br>
<span class="o-muted">${best}</span><br><br>
<span class="o-section">⭐ MATCH RATING</span><br>
<span style="color:var(--gold);font-family:var(--font-display);font-size:28px">${d.match_rating||'N/A'}</span>`;
    } else if (tool === 'history') {
      const teamFilter = document.getElementById('previousTeamFilter')?.value || '';
      const d = await (await fetch(`/api/previous-stats?team=${encodeURIComponent(teamFilter)}`)).json();
      const rows = (d.matches || []).map((m, idx) => {
        const scores = (m.score_summary || []).join(' | ');
        return `<span class="o-section">${idx + 1}. ${m.match}</span><br>
<span class="o-muted">${m.date || ''} · ${m.venue || ''}</span><br>
<span class="o-value">${m.status || 'Completed'}</span><br>
<span class="o-muted">${scores || 'Score unavailable'}</span><br><br>`;
      }).join('');
      out.innerHTML = `<span class="o-title">🕘 Previous Match Stats</span>
    <span class="o-muted">Filter: ${(teamFilter || 'ALL')} · Source: ${(d.source || 'unknown').toUpperCase()}${d.api_error ? ` · API: ${d.api_error}` : ''}</span><br><br>
${rows || '<span class="o-muted">No previous matches found.</span>'}`;
    }
    else if (tool === 'fullAnalysis') {
      const d = await (await fetch(`/api/agent/analysis?query=${encodeURIComponent('Full match analysis')}`)).json();
      const wp = d.win_probability || {};
      const insights = d.key_insights || {};
      const strat = d.strategy || {};
      const comm = d.commentary || {};
      out.innerHTML = `<span class="o-title">⚡ Full Analysis</span>
<span class="o-section">● WIN PROBABILITY</span><br>
<span class="o-value">${wp.probability_team1||'-'}% / ${wp.probability_team2||'-'}% · Confidence: ${(wp.confidence||'N/A')}</span><br><br>
<span class="o-section">● TURNING POINT</span><br>
<span class="o-value">${(insights.turning_points || ['N/A'])[0]}</span><br><br>
<span class="o-section">● STRATEGY</span><br>
<span class="o-muted">Bat: ${strat.batting_strategy||'N/A'}</span><br>
<span class="o-muted">Bowl: ${strat.bowling_strategy||'N/A'}</span><br><br>
<span class="o-section">● COMMENTARY</span><br>
<span class="o-value">${comm.commentary || 'N/A'}</span>`;
    }
  } catch(e) {
    out.innerHTML = `<span class="o-title" style="color:var(--red)">Error</span><br><span class="o-muted">${e.message}</span>`;
  }
}

// ── INIT ──
syncDashboard();
setInterval(syncDashboard, 12000);
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
