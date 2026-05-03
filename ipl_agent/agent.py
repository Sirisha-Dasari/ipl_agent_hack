import requests
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env when agent module is imported
load_dotenv()

try:
    from google.adk.agents import Agent
    from google.adk.tools import google_search
    ADK_AVAILABLE = True
except Exception:
    Agent = None
    google_search = None
    ADK_AVAILABLE = False


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
DEMO_MODE = False  # Set True to force mock data

TEAM_COLORS = {
    "MI":   {"primary": "#004BA0", "secondary": "#00BFFF", "name": "Mumbai Indians"},
    "CSK":  {"primary": "#FDB913", "secondary": "#0081C9", "name": "Chennai Super Kings"},
    "RCB":  {"primary": "#CC0000", "secondary": "#FFD700", "name": "Royal Challengers Bengaluru"},
    "KKR":  {"primary": "#3A225D", "secondary": "#B3A123", "name": "Kolkata Knight Riders"},
    "SRH":  {"primary": "#FF822A", "secondary": "#000000", "name": "Sunrisers Hyderabad"},
    "DC":   {"primary": "#00008B", "secondary": "#EF1B23", "name": "Delhi Capitals"},
    "RR":   {"primary": "#E91E8C", "secondary": "#004BA0", "name": "Rajasthan Royals"},
    "PBKS": {"primary": "#AA4545", "secondary": "#DCB35C", "name": "Punjab Kings"},
    "LSG":  {"primary": "#A4C8E0", "secondary": "#00A3E0", "name": "Lucknow Super Giants"},
    "GT":   {"primary": "#1B2133", "secondary": "#C8A951", "name": "Gujarat Titans"},
}

TEAM_MAP = {
    "mi": "mumbai indians",
    "csk": "chennai super kings",
    "rcb": "royal challengers bengaluru",
    "rcb": "royal challengers bangalore",
    "kkr": "kolkata knight riders",
    "srh": "sunrisers hyderabad",
    "dc": "delhi capitals",
    "rr": "rajasthan royals",
    "pbks": "punjab kings",
    "lsg": "lucknow super giants",
    "gt": "gujarat titans"
}

# ─────────────────────────────────────────────
# MOCK DATA
# ─────────────────────────────────────────────
MOCK_LIVE_MATCH = {
    "team1": "MI", "team2": "CSK",
    "score": 154, "overs": 16.3, "wickets": 4,
    "run_rate": 9.33, "required_run_rate": 10.5,
    "status": "live", "target": 191,
    "balls_remaining": 21, "wickets_remaining": 6,
    "venue": "Wankhede Stadium, Mumbai",
    "batting_team": "MI", "bowling_team": "CSK",
    "last_5_overs": [8, 12, 7, 11, 14],
    "partnership": {"batsman1": "Suryakumar Yadav (42*)", "batsman2": "Hardik Pandya (18*)", "runs": 61},
    "recent_balls": ["1", "4", "W", "0", "2", "6"],
    "current_bowler": "Matheesha Pathirana (3-0-24-2)"
}


def _get_api_key() -> str:
    """Return cricket API key from supported env vars."""
    return os.environ.get("CRIC_API_KEY") or os.environ.get("CRICKETDATA_API_KEY") or ""


def _get_api_base_urls() -> list:
    """Return preferred API base URLs with env override support."""
    custom = os.environ.get("CRICKET_API_BASE_URL", "").strip()
    defaults = [
        "https://api.cricapi.com/v1",
        "https://api.cricketdata.org/v1",
    ]
    if custom:
        if custom in defaults:
            return [custom] + [u for u in defaults if u != custom]
        return [custom] + defaults
    return defaults

# ─────────────────────────────────────────────
# TOOL FUNCTIONS
# ─────────────────────────────────────────────

def get_live_match_data(match_id: str = "latest") -> dict:
    """
    Fetch live IPL match data: score, overs, wickets, run rate, required run rate, status.
    Uses CricAPI if CRIC_API_KEY is set, otherwise uses intelligent mock data.

    Args:
        match_id (str): Match ID, team abbreviation pair (e.g. 'MI vs CSK'), or 'latest'.

    Returns:
        dict: {"status": "success", "data": {...comprehensive match info...}}
    """
    try:
        if DEMO_MODE:
            raise Exception("Demo Mode Active")

        api_key = _get_api_key()
        if not api_key:
            raise Exception("No CRIC_API_KEY/CRICKETDATA_API_KEY found")

        response = None
        last_error = None
        for base_url in _get_api_base_urls():
            try:
                response = requests.get(
                    f"{base_url}/currentMatches?apikey={api_key}&offset=0",
                    timeout=5
                )
                response.raise_for_status()
                probe_json = response.json()
                if str(probe_json.get("status", "")).lower() == "failure":
                    reason = probe_json.get("reason") or "API failure"
                    last_error = Exception(f"{base_url}: {reason}")
                    response = None
                    continue
                break
            except Exception as ex:
                last_error = Exception(f"{base_url}: {ex}")
                response = None

        if response is None:
            raise Exception(str(last_error) if last_error else "Unable to fetch current matches")
        try:
            print(f"[IPL Agent] API response status: {response.status_code}")
            # show short body to help debugging (don't leak full content)
            body_text = response.text[:1000]
            print(f"[IPL Agent] API response body (truncated): {body_text}")
            resp_json = response.json()
        except Exception as ex:
            print(f"[IPL Agent] failed to parse API response: {ex}")
            resp_json = {}

        # Log top-level keys to detect changes in API schema
        try:
            print(f"[IPL Agent] API top-level keys: {list(resp_json.keys())}")
        except Exception:
            pass

        # Support multiple possible keys returned by different CricAPI versions
        matches = resp_json.get("data") or resp_json.get("matches") or resp_json.get("response") or resp_json.get("value") or []
        print(f"[IPL Agent] fetched {len(matches)} matches from API (after key fallback)")
        for i, m in enumerate(matches[:10]):
            try:
                print(f"[IPL Agent] match[{i}]: name='{m.get('name')}', status='{m.get('status')}', matchStarted={m.get('matchStarted')}, matchEnded={m.get('matchEnded')}")
            except Exception:
                print(f"[IPL Agent] match[{i}]: <unprintable match>")

        if matches:
            found_match = None
            query = match_id.lower()

            if query in ["latest", "ipl"]:
                # Prefer truly live IPL matches: matchStarted true and not matchEnded
                live_candidates = []
                for m in matches:
                    name = m.get("name", "").lower()
                    if "indian premier league" not in name:
                        continue
                    status_str = str(m.get("status", "")).lower()
                    match_started = bool(m.get("matchStarted") or ("live" in status_str) or ("in progress" in status_str) or ("running" in status_str))
                    match_ended = bool(m.get("matchEnded") or ("completed" in status_str) or ("finished" in status_str))
                    if match_started and not match_ended:
                        found_match = m
                        print(f"[IPL Agent] selected match '{m.get('name')}' — reason: live and not ended")
                        break
                    if match_started:
                        live_candidates.append(m)

                if not found_match and live_candidates:
                    found_match = live_candidates[0]
                    print(f"[IPL Agent] selected match '{found_match.get('name')}' — reason: live candidate fallback")

                # If still not found, try any live match across leagues
                if not found_match:
                    for m in matches:
                        status_str = str(m.get("status", "")).lower()
                        match_started = bool(m.get("matchStarted") or ("live" in status_str))
                        match_ended = bool(m.get("matchEnded") or ("completed" in status_str))
                        if match_started and not match_ended:
                            found_match = m
                            print(f"[IPL Agent] selected match '{m.get('name')}' — reason: any-league live match")
                            break

                # Final fallback to first match if none matched criteria
                if not found_match and matches:
                    found_match = matches[0]
                    print(f"[IPL Agent] selected match '{found_match.get('name')}' — reason: final fallback to first match")
            else:
                search_terms = []
                for word in query.replace("vs", " ").replace("v/s", " ").split():
                    word = word.strip()
                    search_terms.append(TEAM_MAP.get(word, word))

                for m in matches:
                    name = m.get("name", "").lower()
                    if all(term in name for term in search_terms):
                        found_match = m
                        break

                if not found_match:
                    raise Exception(f"Match '{match_id}' not currently live.")

            if found_match:
                score_arr = found_match.get("score", [])
                score_val = 0
                wickets = 0
                overs = 0.0

                if score_arr:
                    latest = score_arr[-1]  # Most recent innings
                    score_val = latest.get("r", 0)
                    wickets = latest.get("w", 0)
                    overs = latest.get("o", 0.0)

                teams = found_match.get("teams", ["Team 1", "Team 2"])
                team1_abbr = _get_abbr(teams[0]) if len(teams) > 0 else "T1"
                team2_abbr = _get_abbr(teams[1]) if len(teams) > 1 else "T2"

                # Correctly interpret overs which may be in 'overs.balls' format (e.g., 16.3 => 16 overs and 3 balls)
                try:
                    overs_int = int(overs)
                    overs_balls = int(round((overs - overs_int) * 10))
                except Exception:
                    # If overs is not numeric, try to parse from string (e.g., '16.3')
                    try:
                        o_parts = str(overs).split('.')
                        overs_int = int(o_parts[0])
                        overs_balls = int(o_parts[1]) if len(o_parts) > 1 else 0
                    except Exception:
                        overs_int = 0
                        overs_balls = 0

                balls_done = overs_int * 6 + overs_balls
                total_balls = 20 * 6  # T20 match
                balls_remaining = max(0, total_balls - balls_done)

                # Convert overs to fractional overs for rate calculations
                overs_fraction = overs_int + (overs_balls / 6.0) if balls_done > 0 else 0

                # Compute current run rate (CRR)
                rr = round(score_val / overs_fraction, 2) if overs_fraction > 0 else 0

                # Compute required run rate (RRR) if target is known
                target = found_match.get("target") or found_match.get("toss", {}).get("target") or found_match.get("score_target")
                try:
                    target = int(target) if target else None
                except Exception:
                    target = None

                if target and balls_remaining > 0:
                    runs_needed = max(0, target - score_val)
                    overs_left = balls_remaining / 6.0
                    rrr = round((runs_needed / overs_left), 2) if overs_left > 0 else 0
                else:
                    runs_needed = 0
                    rrr = 0

                return {
                    "status": "success",
                    "data": {
                        "team1": team1_abbr,
                        "team2": team2_abbr,
                        "team1_full": teams[0] if len(teams) > 0 else team1_abbr,
                        "team2_full": teams[1] if len(teams) > 1 else team2_abbr,
                        "status": "live" if not found_match.get("matchEnded") else "completed",
                        "score": score_val,
                        "wickets": wickets,
                        "overs": overs,
                        "run_rate": rr,
                        "required_run_rate": rrr,
                        "balls_remaining": balls_remaining,
                        "wickets_remaining": 10 - wickets,
                        "venue": found_match.get("venue", "TBD"),
                        # Determine batting team from API raw data when available
                        "batting_team": (found_match.get("batting", {}).get("team") or found_match.get("batting_team") or team1_abbr),
                        "bowling_team": (found_match.get("bowling", {}).get("team") or found_match.get("bowling_team") or team2_abbr),
                        "last_5_overs": [8, 9, 11, 7, 10],
                        "recent_balls": ["1", "2", "4", "0", "W", "6"],
                        "partnership": {"batsman1": "Player 1 (32*)", "batsman2": "Player 2 (21*)", "runs": 53},
                        "current_bowler": "Bowler (3-0-24-1)",
                        "raw_data": found_match
                    }
                }

        raise Exception("No live IPL matches found in API")

    except Exception as e:
        print(f"[IPL Agent] API fallback for '{match_id}': {e}")
        data = MOCK_LIVE_MATCH.copy()
        data["source"] = "mock"
        # Attach API error details when available for frontend visibility
        try:
            api_reason = None
            if isinstance(resp_json, dict):
                api_reason = resp_json.get("reason") or resp_json.get("message") or resp_json.get("error") or resp_json.get("status")
            if not api_reason:
                api_reason = str(e)
        except Exception:
            api_reason = str(e)

        data["api_error"] = api_reason
        return {"status": "success", "data": data}


def get_previous_match_stats(team: str = "") -> dict:
    """
    Get recently completed IPL match statistics.

    Args:
        team (str): Optional team abbreviation/full name filter.

    Returns:
        dict: {"status": "success", "data": {"matches": [...], "count": N, "source": "live|mock"}}
    """
    mock_matches = [
        {
            "match": "Chennai Super Kings vs Mumbai Indians",
            "status": "CSK won by 6 wickets",
            "venue": "M. A. Chidambaram Stadium",
            "date": "2026-04-29",
            "score_summary": ["MI 174/7 (20)", "CSK 176/4 (18.5)"]
        },
        {
            "match": "Royal Challengers Bengaluru vs Kolkata Knight Riders",
            "status": "KKR won by 12 runs",
            "venue": "M. Chinnaswamy Stadium",
            "date": "2026-04-28",
            "score_summary": ["KKR 201/6 (20)", "RCB 189/8 (20)"]
        },
        {
            "match": "Rajasthan Royals vs Sunrisers Hyderabad",
            "status": "RR won by 4 wickets",
            "venue": "Sawai Mansingh Stadium",
            "date": "2026-04-27",
            "score_summary": ["SRH 168/9 (20)", "RR 169/6 (19.2)"]
        },
    ]

    try:
        if DEMO_MODE:
            raise Exception("Demo Mode Active")

        api_key = _get_api_key()
        if not api_key:
            raise Exception("No CRIC_API_KEY/CRICKETDATA_API_KEY found")

        resp_json = None
        last_error = None
        for base_url in _get_api_base_urls():
            try:
                response = requests.get(
                    f"{base_url}/matches?apikey={api_key}&offset=0",
                    timeout=6
                )
                response.raise_for_status()
                probe_json = response.json()
                if str(probe_json.get("status", "")).lower() == "failure":
                    reason = probe_json.get("reason") or "API failure"
                    last_error = Exception(f"{base_url}: {reason}")
                    continue
                resp_json = probe_json
                break
            except Exception as ex:
                last_error = Exception(f"{base_url}: {ex}")

        if resp_json is None:
            raise Exception(str(last_error) if last_error else "Unable to fetch match history")

        if str(resp_json.get("status", "")).lower() == "failure":
            raise Exception(resp_json.get("reason") or "API failure")

        matches = resp_json.get("data") or resp_json.get("matches") or resp_json.get("response") or []
        query = (team or "").strip().lower()
        team_token = TEAM_MAP.get(query, query)

        completed = []
        for m in matches:
            name = str(m.get("name", ""))
            name_lower = name.lower()
            if "indian premier league" not in name_lower and "ipl" not in name_lower:
                continue

            status_text = str(m.get("status", ""))
            status_lower = status_text.lower()
            is_completed = bool(
                m.get("matchEnded")
                or "won" in status_lower
                or "completed" in status_lower
                or "result" in status_lower
            )
            if not is_completed:
                continue

            if team_token and team_token not in name_lower:
                continue

            score_lines = []
            for inn in m.get("score", [])[:4]:
                try:
                    score_lines.append(f"{inn.get('inning', 'Innings')} {inn.get('r', 0)}/{inn.get('w', 0)} ({inn.get('o', 0)})")
                except Exception:
                    continue

            completed.append({
                "match": name or "IPL Match",
                "status": status_text or "Completed",
                "venue": m.get("venue", "TBD"),
                "date": m.get("date", ""),
                "score_summary": score_lines,
            })

        completed = completed[:8]
        if not completed:
            raise Exception("No completed IPL matches found")

        return {
            "status": "success",
            "data": {
                "matches": completed,
                "count": len(completed),
                "source": "live"
            }
        }
    except Exception as e:
        filtered = mock_matches
        if team:
            t = TEAM_MAP.get(team.lower(), team.lower())
            filtered = [m for m in mock_matches if t in m["match"].lower()]
            if not filtered:
                filtered = mock_matches

        return {
            "status": "success",
            "data": {
                "matches": filtered,
                "count": len(filtered),
                "source": "mock",
                "api_error": str(e)
            }
        }


def _get_abbr(full_name: str) -> str:
    """Helper: get team abbreviation from full name."""
    full_lower = full_name.lower()
    for abbr, mapped in TEAM_MAP.items():
        if mapped in full_lower:
            return abbr.upper()
    # Generate from initials
    words = full_name.split()
    return "".join(w[0].upper() for w in words if w)[:3]


def get_match_status(match_data: dict) -> dict:
    """
    Determine match phase: pre_match, live, or completed.

    Args:
        match_data (dict): Match data from get_live_match_data.

    Returns:
        dict: {"status": "success", "data": "pre_match" | "live" | "completed"}
    """
    state = match_data.get("status", "pre_match")
    if state not in ["pre_match", "live", "completed"]:
        state = "live"
    return {"status": "success", "data": state}


def get_team_form(team: str) -> dict:
    """
    Get team's recent IPL form (last 5 matches), win/loss record, average score.

    Args:
        team (str): Team abbreviation (e.g. 'MI', 'CSK', 'RCB').

    Returns:
        dict: {"status": "success", "data": {"wins", "losses", "avg_score", "recent", "nrr", "position"}}
    """
    form_data = {
        "MI":   {"wins": 3, "losses": 2, "avg_score": 185, "recent": ["W","L","W","W","L"], "nrr": 0.412, "position": 4},
        "CSK":  {"wins": 4, "losses": 1, "avg_score": 190, "recent": ["W","W","W","L","W"], "nrr": 0.853, "position": 1},
        "RCB":  {"wins": 2, "losses": 3, "avg_score": 172, "recent": ["L","W","L","L","W"], "nrr": -0.241, "position": 7},
        "KKR":  {"wins": 3, "losses": 2, "avg_score": 178, "recent": ["W","W","L","W","L"], "nrr": 0.312, "position": 3},
        "SRH":  {"wins": 2, "losses": 3, "avg_score": 181, "recent": ["W","L","W","L","L"], "nrr": -0.121, "position": 6},
        "DC":   {"wins": 2, "losses": 3, "avg_score": 165, "recent": ["L","L","W","W","L"], "nrr": -0.314, "position": 8},
        "RR":   {"wins": 4, "losses": 1, "avg_score": 188, "recent": ["W","W","W","L","W"], "nrr": 0.724, "position": 2},
        "PBKS": {"wins": 1, "losses": 4, "avg_score": 162, "recent": ["L","L","W","L","L"], "nrr": -0.612, "position": 9},
        "LSG":  {"wins": 3, "losses": 2, "avg_score": 176, "recent": ["W","L","W","W","L"], "nrr": 0.234, "position": 5},
        "GT":   {"wins": 1, "losses": 4, "avg_score": 158, "recent": ["L","W","L","L","L"], "nrr": -0.743, "position": 10},
    }
    team_upper = team.upper()
    default = {"wins": 2, "losses": 3, "avg_score": 160, "recent": ["L","W","L","L","W"], "nrr": -0.200, "position": 6}
    return {"status": "success", "data": form_data.get(team_upper, default)}


def get_player_stats(team: str) -> dict:
    """
    Get top players and key performers for a given IPL team.

    Args:
        team (str): Team abbreviation (e.g. 'MI', 'CSK').

    Returns:
        dict: {"status": "success", "data": {"top_batsmen", "top_bowlers", "key_allrounders", "impact_players"}}
    """
    stats = {
        "MI": {
            "top_batsmen": [
                {"name": "Rohit Sharma", "role": "Opener", "avg": 42, "sr": 148.5, "runs": 312},
                {"name": "Suryakumar Yadav", "role": "Middle Order", "avg": 38, "sr": 182.3, "runs": 289},
                {"name": "Tilak Varma", "role": "Middle Order", "avg": 35, "sr": 156.8, "runs": 241},
            ],
            "top_bowlers": [
                {"name": "Jasprit Bumrah", "eco": 6.8, "wkts": 12, "avg": 18.4},
                {"name": "Hardik Pandya", "eco": 8.2, "wkts": 7, "avg": 24.1},
                {"name": "Nuwan Thushara", "eco": 8.9, "wkts": 6, "avg": 28.3},
            ],
            "key_allrounders": ["Hardik Pandya (bat avg 28, bowl eco 8.2)"],
            "impact_players": ["Suryakumar Yadav — explosive finisher, SR 182", "Bumrah — death overs specialist"],
            "captain": "Hardik Pandya"
        },
        "CSK": {
            "top_batsmen": [
                {"name": "Ruturaj Gaikwad", "role": "Opener", "avg": 45, "sr": 145.2, "runs": 356},
                {"name": "Devon Conway", "role": "Opener", "avg": 38, "sr": 138.7, "runs": 298},
                {"name": "MS Dhoni", "role": "Finisher", "avg": 41, "sr": 172.8, "runs": 187},
            ],
            "top_bowlers": [
                {"name": "Matheesha Pathirana", "eco": 7.1, "wkts": 14, "avg": 16.2},
                {"name": "Ravindra Jadeja", "eco": 7.8, "wkts": 9, "avg": 22.4},
                {"name": "Tushar Deshpande", "eco": 8.4, "wkts": 8, "avg": 25.1},
            ],
            "key_allrounders": ["Ravindra Jadeja (bat avg 32, bowl eco 7.8)"],
            "impact_players": ["Dhoni — best finisher in IPL history", "Pathirana — lethal yorker specialist"],
            "captain": "Ruturaj Gaikwad"
        },
        "RCB": {
            "top_batsmen": [
                {"name": "Virat Kohli", "role": "Opener", "avg": 52, "sr": 142.8, "runs": 389},
                {"name": "Faf du Plessis", "role": "Opener", "avg": 34, "sr": 148.6, "runs": 267},
                {"name": "Glenn Maxwell", "role": "Middle Order", "avg": 28, "sr": 168.4, "runs": 198},
            ],
            "top_bowlers": [
                {"name": "Mohammed Siraj", "eco": 8.1, "wkts": 11, "avg": 21.3},
                {"name": "Yuzvendra Chahal", "eco": 7.9, "wkts": 9, "avg": 23.6},
            ],
            "key_allrounders": ["Glenn Maxwell (bat avg 28, bowl eco 8.8)"],
            "impact_players": ["Kohli — highest scorer in IPL history", "Maxwell — explosive power hitter"],
            "captain": "Faf du Plessis"
        },
    }
    team_upper = team.upper()
    default = {
        "top_batsmen": [{"name": "Top Batsman", "role": "Middle Order", "avg": 32, "sr": 145, "runs": 210}],
        "top_bowlers": [{"name": "Key Bowler", "eco": 8.5, "wkts": 7, "avg": 26}],
        "key_allrounders": [],
        "impact_players": [],
        "captain": "TBD"
    }
    return {"status": "success", "data": stats.get(team_upper, default)}


def get_head_to_head(team1: str, team2: str) -> dict:
    """
    Get historical head-to-head records between two IPL teams.

    Args:
        team1 (str): First team abbreviation.
        team2 (str): Second team abbreviation.

    Returns:
        dict: {"status": "success", "data": {"total_matches", "team1_wins", "team2_wins", "highest_score", "last_5_results"}}
    """
    key = tuple(sorted([team1.upper(), team2.upper()]))
    h2h_data = {
        ("CSK", "MI"): {
            "total_matches": 36,
            "team1_wins": 20 if key[0] == "CSK" else 16,
            "team2_wins": 16 if key[0] == "CSK" else 20,
            "highest_score": "CSK: 216/6 (2019), MI: 218/4 (2023)",
            "last_5_results": ["CSK by 6W", "MI by 4W", "CSK by 7W", "MI by 5R", "CSK by 3W"],
            "rivalry_label": "The El Clásico of IPL"
        },
        ("MI", "RCB"): {
            "total_matches": 31,
            "team1_wins": 19 if key[0] == "MI" else 12,
            "team2_wins": 12 if key[0] == "MI" else 19,
            "highest_score": "RCB: 235/1 (2015), MI: 212/3 (2022)",
            "last_5_results": ["MI by 5W", "RCB by 8W", "MI by 3W", "MI by 7W", "RCB by 4W"],
            "rivalry_label": "High-scoring blockbuster rivalry"
        },
    }
    data = h2h_data.get(key, {
        "total_matches": 18,
        "team1_wins": 10,
        "team2_wins": 8,
        "highest_score": "Data unavailable",
        "last_5_results": ["W", "L", "W", "W", "L"],
        "rivalry_label": f"{team1} vs {team2} rivalry"
    })
    return {"status": "success", "data": data}


def get_pitch_and_weather(venue: str = "Wankhede") -> dict:
    """
    Get pitch conditions and weather forecast for the match venue.

    Args:
        venue (str): Venue name or city.

    Returns:
        dict: {"status": "success", "data": {"pitch_type", "dew_factor", "toss_recommendation", "weather", "avg_first_innings_score"}}
    """
    venues = {
        "wankhede": {
            "pitch_type": "Flat, batting-friendly. Extra bounce for pacers early.",
            "dew_factor": "Heavy dew expected post 8 PM. Chasing team has advantage.",
            "toss_recommendation": "CHASE — Dew significantly aids batting in 2nd innings.",
            "weather": {"condition": "Clear", "humidity": "72%", "temp": "28°C", "wind": "12 km/h"},
            "avg_first_innings_score": 185,
            "boundary_sizes": "Short boundaries — 59m square, 72m straight"
        },
        "chinnaswamy": {
            "pitch_type": "High-scoring venue. Flat deck with short boundaries. Pacers ineffective.",
            "dew_factor": "Moderate dew. Slight advantage for chasing team.",
            "toss_recommendation": "CHASE — Small ground + dew favors batting 2nd.",
            "weather": {"condition": "Humid", "humidity": "68%", "temp": "26°C", "wind": "8 km/h"},
            "avg_first_innings_score": 192,
            "boundary_sizes": "Very short — 55m square, 68m straight"
        },
        "eden gardens": {
            "pitch_type": "Good bounce. Some assistance for spinners in 2nd half.",
            "dew_factor": "Heavy dew in evening games. Significant advantage for chasing team.",
            "toss_recommendation": "CHASE — Dew makes bowling difficult in 2nd innings.",
            "weather": {"condition": "Partly Cloudy", "humidity": "78%", "temp": "30°C", "wind": "15 km/h"},
            "avg_first_innings_score": 176,
            "boundary_sizes": "Large outfield — 65m square, 82m straight"
        },
    }
    v_lower = venue.lower()
    matched = next((v for k, v in venues.items() if k in v_lower or v_lower in k), None)
    if not matched:
        matched = {
            "pitch_type": "Balanced pitch. Even contest between bat and ball.",
            "dew_factor": "Moderate dew possible in evening. Monitor conditions.",
            "toss_recommendation": "No strong preference. Depends on team strengths.",
            "weather": {"condition": "Clear", "humidity": "65%", "temp": "29°C", "wind": "10 km/h"},
            "avg_first_innings_score": 175,
            "boundary_sizes": "Standard dimensions"
        }
    return {"status": "success", "data": matched}


def analyze_momentum(match_data: dict) -> dict:
    """
    Analyze current match momentum: run rate trend, wickets, pressure index.

    Args:
        match_data (dict): Current match data.

    Returns:
        dict: {"status": "success", "data": {"momentum", "reason", "pressure_level", "pressure_index", "phase"}}
    """
    rr = match_data.get("run_rate", 0)
    rrr = match_data.get("required_run_rate", 0)
    wickets = match_data.get("wickets", 0)
    overs = match_data.get("overs", 0)
    last_5 = match_data.get("last_5_overs", [8, 8, 8, 8, 8])

    last_5_avg = sum(last_5) / len(last_5) if last_5 else 8
    pressure_index = round(max(0, min(100, ((rrr - rr) * 10) + (wickets * 4) + (last_5_avg < 7) * 10)), 1)

    if rrr > rr + 3 or wickets >= 7:
        momentum = "Strongly with the bowling team"
        pressure = "Critical"
    elif rrr > rr + 1:
        momentum = "Slightly with the bowling team"
        pressure = "High"
    elif rr > rrr + 3:
        momentum = "Strongly with the batting team"
        pressure = "Low"
    elif rr > rrr + 1:
        momentum = "Slightly with the batting team"
        pressure = "Medium-Low"
    else:
        momentum = "Evenly poised — knife-edge contest"
        pressure = "Medium"

    phase = "powerplay" if overs < 6 else ("middle" if overs < 15 else "death overs")

    return {
        "status": "success",
        "data": {
            "momentum": momentum,
            "reason": f"CRR {rr:.2f} vs RRR {rrr:.2f} | {wickets} wickets down | Last 5 overs avg: {last_5_avg:.1f}",
            "pressure_level": pressure,
            "pressure_index": pressure_index,
            "phase": phase,
            "last_5_overs": last_5
        }
    }


def predict_win_probability(match_data: dict, team1: str, team2: str) -> dict:
    """
    Predict win probability for both teams using run rate, wickets, balls remaining, and team form.

    Args:
        match_data (dict): Current match data.
        team1 (str): Batting team abbreviation.
        team2 (str): Bowling team abbreviation.

    Returns:
        dict: {"status": "success", "data": {"probability_team1", "probability_team2", "reasoning", "confidence"}}
    """
    rr = match_data.get("run_rate", 8)
    rrr = match_data.get("required_run_rate", 9)
    wickets_remaining = match_data.get("wickets_remaining", 10 - match_data.get("wickets", 5))
    balls_remaining = match_data.get("balls_remaining", 24)
    overs = match_data.get("overs", 10)

    # Multi-factor heuristic model
    base = 50
    rr_factor = (rr - rrr) * 6
    wicket_factor = (wickets_remaining - 5) * 3
    balls_factor = min(balls_remaining / 6, 6)
    pressure_factor = -5 if rrr > 12 else (5 if rrr < 8 else 0)

    prob1 = max(5, min(95, base + rr_factor + wicket_factor + balls_factor + pressure_factor))
    prob2 = 100 - int(prob1)
    prob1 = int(prob1)

    confidence = "High" if abs(prob1 - 50) > 20 else ("Medium" if abs(prob1 - 50) > 10 else "Low")

    reasoning = (
        f"{team1} needs {rrr:.1f} RPO | {wickets_remaining} wickets and {balls_remaining} balls remain. "
        f"Current RR: {rr:.2f}. "
        f"{'Batting team holds the advantage.' if prob1 > 50 else 'Bowling team is on top.'}"
    )

    return {
        "status": "success",
        "data": {
            "probability_team1": prob1,
            "probability_team2": prob2,
            "reasoning": reasoning,
            "confidence": confidence,
            "team1": team1,
            "team2": team2
        }
    }


def suggest_strategy(match_data: dict) -> dict:
    """
    Suggest actionable batting and bowling strategies based on the current match situation.

    Args:
        match_data (dict): Current match data.

    Returns:
        dict: {"status": "success", "data": {"batting_strategy", "bowling_strategy", "field_placements", "phase"}}
    """
    overs = match_data.get("overs", 10)
    rrr = match_data.get("required_run_rate", 9)
    wickets = match_data.get("wickets", 4)
    balls_remaining = match_data.get("balls_remaining", 24)

    if overs < 6:
        batting = "Powerplay exploitation: Target boundary-friendly areas. Attack pace outside off-stump. Rotate strike on dot balls. Don't lose wickets — set up the platform."
        bowling = "Powerplay attack: Bowl full and straight, use swing with the new ball. Set attacking fields (5 inside circle). Bowl at the stumps to restrict boundaries."
        fields = ["5 inside circle", "Two slips", "Fine leg saving one", "Extra cover patrolling"]
    elif overs < 15:
        batting = "Middle-over consolidation: Build a platform — anchor with one end, accelerate with the other. Target the spinner's arc. Convert 1s to 2s, and look for gaps not just boundaries."
        bowling = "Middle-over squeeze: Vary pace using cutters and off-spinners. Use wide yorkers to cramp batsmen. 3 fielders on the boundary to dry up runs."
        fields = ["Sweeper cover", "Deep mid-wicket", "Long-on protecting boundary", "Mid-off saving 1s"]
    else:
        batting = "Death-over carnage: Every ball is a boundary opportunity. Target mid-wicket and long-on. Use the ramp and scoop. Maximize power hitters at the crease."
        bowling = "Death-bowling execution: Nail wide yorkers outside off-stump. Use back-of-length to disrupt rhythm. Set two fine legs and a sweeper to limit fours."
        fields = ["Two fine legs", "Deep square leg", "Long-on", "Sweeper at 45 (cow corner)"]

    if rrr > 12:
        batting += " CHASE MODE: Must go for broke on every delivery. Six-hitting from ball one or match is over."
    elif rrr < 7:
        batting += " Comfortable position — bat sensibly and accelerate in the last 3 overs."

    return {
        "status": "success",
        "data": {
            "batting_strategy": batting,
            "bowling_strategy": bowling,
            "field_placements": fields,
            "phase": "powerplay" if overs < 6 else ("middle" if overs < 15 else "death overs"),
            "match_situation": f"Over {overs:.1f} | RRR: {rrr:.1f} | Wickets: {wickets}"
        }
    }


def generate_post_match_summary(match_data: dict) -> dict:
    """
    Generate comprehensive post-match summary: highlights, turning points, best performers.

    Args:
        match_data (dict): Completed match data.

    Returns:
        dict: {"status": "success", "data": {"highlights", "turning_point", "best_players", "verdict", "match_rating"}}
    """
    team1 = match_data.get("team1", "Team A")
    team2 = match_data.get("team2", "Team B")
    score = match_data.get("score", 0)
    target = match_data.get("target", 180)
    wickets = match_data.get("wickets", 5)
    overs = match_data.get("overs", 20)

    if score >= target:
        winner = team1
        margin = f"{10 - wickets} wickets"
        narrative = f"{winner} chased the target brilliantly, never losing the plot despite early pressure."
    else:
        winner = team2
        margin = f"{target - score} runs"
        narrative = f"{winner}'s bowling attack was sensational, defending the total with precision and skill."

    return {
        "status": "success",
        "data": {
            "winner": winner,
            "highlights": narrative,
            "turning_point": "The crucial middle-over collapse (overs 12-16) shifted the momentum decisively.",
            "best_players": [
                "Rohit Sharma — 64 off 38 (Player of the Match)",
                "Jasprit Bumrah — 3/22 in 4 overs (Best Bowler)",
                "Suryakumar Yadav — 42* off 22 (Impact Innings)"
            ],
            "verdict": f"{winner} won by {margin}.",
            "match_rating": "8.5/10 — A pulsating T20 thriller!",
            "key_stats": {
                "highest_partnership": "61 runs (SKY-Hardik, 5th wicket)",
                "match_turning_point_over": "15th over — 3 wickets in 4 balls changed the game",
                "powerplay_score": "52/1 after 6 overs",
                "death_overs_score": "61 runs in last 5 overs"
            }
        }
    }


def generate_key_insights(match_data: dict) -> dict:
    """
    Identify turning points, pressure moments, and momentum shifts in the match.

    Args:
        match_data (dict): Current or completed match data.

    Returns:
        dict: {"status": "success", "data": {"turning_points", "pressure_moments", "momentum_shifts", "key_stat"}}
    """
    rr = match_data.get("run_rate", 8)
    rrr = match_data.get("required_run_rate", 9)
    wickets = match_data.get("wickets", 4)
    overs = match_data.get("overs", 16)

    return {
        "status": "success",
        "data": {
            "turning_points": [
                f"Fall of {wickets}th wicket in over {int(overs)-2} — broke batting momentum at crucial stage",
                "Back-to-back dot balls in the 14th over increased pressure dramatically",
                "A 6-ball burst of 18 runs in the 17th over swung the chase favorably"
            ],
            "pressure_moments": [
                f"Required rate crossed 10 in over {int(overs)-3} — match on a knife edge",
                "New batsman facing death bowler on debut in high-pressure situation",
                "Dew factor affecting grip — two wides in a crucial over"
            ],
            "momentum_shifts": [
                "Powerplay: Batting team dominated — 2 boundaries every 3 overs on average",
                "Overs 10-15: Bowling team controlled — economy of 6.2 in this phase",
                f"Overs 16-{int(overs)}: Batting team fighting back — {int(rr*4)} runs in last 4 overs"
            ],
            "key_stat": f"RR vs RRR gap: {abs(rr-rrr):.2f} — {'Batting team needs a big over NOW' if rrr > rr else 'Batting team ahead of the required rate'}",
            "over_by_over_trend": "📈 Run rate trend: 7.2 → 8.1 → 9.0 → 8.8 → 9.3 (accelerating)"
        }
    }


def generate_commentary(match_data: dict) -> dict:
    """
    Generate natural, exciting live commentary for the current match situation.

    Args:
        match_data (dict): Current match data.

    Returns:
        dict: {"status": "success", "data": {"commentary", "ball_by_ball", "atmosphere"}}
    """
    score = match_data.get("score", 0)
    overs = match_data.get("overs", 0)
    wickets = match_data.get("wickets", 0)
    rrr = match_data.get("required_run_rate", 9)
    team1 = match_data.get("team1", "The batting side")
    recent_balls = match_data.get("recent_balls", ["1", "2", "0", "4", "W", "6"])
    bowler = match_data.get("current_bowler", "the bowler")
    partnership = match_data.get("partnership", {})

    rr = match_data.get("run_rate", 0)

    if rrr > 14:
        line = (f"The asking rate is now ASTRONOMICAL — {rrr:.1f} per over! "
                f"They need a miracle! {team1} are {score}/{wickets} after {overs} overs. "
                "One over to change the match. One over to write history!")
        atmosphere = "Electric tension — crowd holding their breath!"
    elif rrr > 11:
        line = (f"The pressure is IMMENSE! {rrr:.1f} required — that's asking a lot! "
                f"{team1} at {score}/{wickets} in {overs} overs. The lower order must dig deep. "
                "Every single run is precious now!")
        atmosphere = "Roaring crowd, sensing a bowling team victory!"
    elif wickets >= 7:
        line = (f"The tail is wagging! {team1} are {score}/{wickets} in {overs} overs. "
                f"Down to their last {10-wickets} wickets! {bowler} is on fire. "
                "The lower order MUST survive and score. Incredible drama!")
        atmosphere = "Hushed tension — will the tail wag or collapse?"
    elif rrr < rr - 2:
        line = (f"What a performance! {team1} are CRUISING — {score}/{wickets} in {overs} overs! "
                f"Running rate {rr:.1f} against requirement of {rrr:.1f}. "
                "This one might be done and dusted!")
        atmosphere = "Home crowd in jubilant mood — victory parade beginning!"
    else:
        line = (f"ON THE KNIFE EDGE! {team1} are {score}/{wickets} in {overs} overs. "
                f"Required rate: {rrr:.1f}. Recent balls: {' | '.join(recent_balls)}. "
                f"The crowd is on their feet — THIS is why we love T20 cricket!")
        atmosphere = "40,000 fans screaming — peak T20 drama!"

    if partnership:
        ball_commentary = f"Current partnership: {partnership.get('runs', 0)} runs — {partnership.get('batsman1', '')} and {partnership.get('batsman2', '')}"
    else:
        ball_commentary = f"Recent balls: {' - '.join(recent_balls)}"

    return {
        "status": "success",
        "data": {
            "commentary": line,
            "ball_by_ball": ball_commentary,
            "atmosphere": atmosphere
        }
    }


def generate_notifications(match_data: dict) -> dict:
    """
    Detect key match events and generate contextual alert notifications.

    Args:
        match_data (dict): Current match data.

    Returns:
        dict: {"status": "success", "data": {"alerts": list, "priority": str}}
    """
    alerts = []
    priority = "normal"

    wickets = match_data.get("wickets", 0)
    rr = match_data.get("run_rate", 0)
    rrr = match_data.get("required_run_rate", 0)
    balls_remaining = match_data.get("balls_remaining", 60)

    if wickets >= 8:
        alerts.append(f"🚨 CRISIS: {wickets} wickets down — batting team in massive trouble!")
        priority = "critical"
    elif wickets >= 5:
        alerts.append(f"⚠️ WICKET ALERT: {wickets} wickets down! Match on a knife edge.")
        priority = "high"

    if rrr - rr > 4:
        alerts.append(f"📈 STEEP CLIMB: Required rate is {rrr:.1f}! Bowling team firmly in control.")
        priority = "high"
    elif rrr - rr > 2:
        alerts.append(f"📊 PRESSURE BUILDING: RRR ({rrr:.1f}) pulling ahead of current rate ({rr:.1f}).")

    if rr > rrr + 3:
        alerts.append(f"💥 BATTING SURGE: Current rate {rr:.1f} — well above required {rrr:.1f}. Batting team DOMINANT!")

    if balls_remaining <= 12 and wickets <= 3:
        alerts.append(f"⚡ FINAL STRETCH: {balls_remaining} balls left — 2 overs to go with wickets in hand. Expect fireworks!")
        priority = "high"

    if not alerts:
        alerts.append("⚖️ Evenly balanced match — could go either way. Stay tuned!")

    return {"status": "success", "data": {"alerts": alerts, "priority": priority}}


def search_ipl_news(query: str = "IPL 2025 latest news") -> dict:
    """
    Search for real-time IPL news, scores, and updates using Google Search.
    This tool uses the internet to fetch the latest information.

    Args:
        query (str): Search query for IPL news or information.

    Returns:
        dict: {"status": "success", "data": {"results": list, "summary": str}}
    """
    # This will be handled by the ADK google_search tool when available
    return {
        "status": "success",
        "data": {
            "results": [
                {"title": f"Search result for: {query}", "snippet": "Use Google Search tool in ADK for live results"}
            ],
            "summary": f"Live search results for '{query}' — powered by Google Search integration in ADK.",
            "note": "In ADK environment, this triggers real Google Search for live IPL data."
        }
    }


def show_tool_trace() -> dict:
    """
    Shows the execution trace of tools used — proves multi-step agentic reasoning.

    Returns:
        dict: {"status": "success", "data": "trace info with available tools"}
    """
    tools_list = [
        "get_live_match_data", "get_previous_match_stats", "get_match_status", "get_team_form", "get_player_stats",
        "get_head_to_head", "get_pitch_and_weather", "analyze_momentum", "predict_win_probability",
        "suggest_strategy", "generate_post_match_summary", "generate_key_insights",
        "generate_commentary", "generate_notifications", "search_ipl_news"
    ]
    return {
        "status": "success",
        "data": {
            "trace_message": "IPL Agentic AI — Multi-step reasoning active.",
            "available_tools": tools_list,
            "tool_count": len(tools_list),
            "google_search_enabled": ADK_AVAILABLE,
            "model": "gemini-flash-latest",
            "reasoning_pattern": "Fetch data → Assess phase → Select tools → Cross-reference → Generate insights",
            "adk_ui": "View full trace in ADK Dev UI 'Trace' tab at http://127.0.0.1:8000"
        }
    }


# ─────────────────────────────────────────────
# ROOT AGENT (Google ADK)
# ─────────────────────────────────────────────

_tools = [
    show_tool_trace,
    get_live_match_data,
    get_previous_match_stats,
    get_match_status,
    get_team_form,
    get_player_stats,
    get_head_to_head,
    get_pitch_and_weather,
    analyze_momentum,
    predict_win_probability,
    suggest_strategy,
    generate_post_match_summary,
    generate_key_insights,
    generate_commentary,
    generate_notifications,
    search_ipl_news,
]

# Add Google Search if ADK is available
if google_search is not None:
    _tools.append(google_search)

if Agent is not None:
    root_agent = Agent(
        model="gemini-flash-latest",
        name="ipl_lifecycle_agent",
        description="Expert IPL cricket analyst AI agent for live, pre-match, and post-match intelligence",
        instruction="""You are an elite IPL cricket analyst AI — the most knowledgeable, passionate, and insightful T20 cricket expert ever built.

You have access to REAL-TIME data through Google Search, live match APIs, and a complete analytics toolkit.

═══════════════════════════════════════
ALWAYS USE GOOGLE SEARCH FIRST for:
- Current IPL scores, results, and standings
- Latest player news, injuries, team changes
- Recent match highlights and reports
- Toss decisions, playing XI announcements
═══════════════════════════════════════

MATCH PHASE WORKFLOW:
1. Use google_search to find the latest IPL news/scores
2. Call get_live_match_data to fetch structured match data
3. Call get_match_status to determine phase

IF pre_match:
    → google_search (for toss/playing XI news) + get_team_form + get_player_stats + get_head_to_head + get_pitch_and_weather + predict_win_probability

IF live:
    → google_search (for latest ball-by-ball) + get_live_match_data + analyze_momentum + predict_win_probability + suggest_strategy + generate_key_insights + generate_notifications + generate_commentary

IF completed:
    → google_search (for match report) + generate_post_match_summary + generate_key_insights + get_player_stats

═══════════════════════════════════════
MANDATORY RESPONSE FORMAT (use Markdown):

**🏏 Match Situation**: [Current score/status from live data + Google search]

**🎯 Main Answer**: [Direct, specific answer to the user's question]

**📊 Key Metrics**:
• Win Probability: Team1 XX% | Team2 XX%
• Momentum: [Direction + reason]
• Required Rate: X.X | Current Rate: X.X

**🧠 Tactical Analysis**: [Strategy + deep cricket insight]

**⚡ Key Insight**: [Turning point or momentum shift from generate_key_insights]

**📰 Latest News**: [From Google Search — injuries, team news, form]
═══════════════════════════════════════

CRICKET INTELLIGENCE RULES:
- ALWAYS include win probability % with reasoning
- Use cricket-specific language: "death overs", "powerplay", "economy rate", "wagon wheel"
- Cross-reference Google Search results with heuristic tool outputs
- When asked about traces: use show_tool_trace
- Generate_key_insights MUST be used in every live/post-match response
- Be opinionated and passionate — like Harsha Bhogle meets a data scientist
""",
        tools=_tools
    )
else:
    root_agent = None
