"""Play-by-play  ->  the compact per-game record we actually store.

Column names below are nflverse's, taken from the published play-by-play
reference. Nothing else in the pipeline touches raw play-by-play, so if the
upstream schema ever moves, this is the only file that changes.
"""
from collections import defaultdict

PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv"

# the columns we need out of ~400
COLS = ["game_id","season","week","season_type","home_team","away_team",
        "posteam","defteam","td_team","touchdown","return_touchdown",
        "yards_gained","return_yards","field_goal_result","kick_distance",
        "home_score","away_score"]

def _num(v, d=0.0):
    try:
        if v in ("", "NA", None): return d
        return float(v)
    except (TypeError, ValueError):
        return d

def _td_yards(r):
    """Yards credited to a touchdown. A return TD is measured by the return,
    everything else by the yards gained on the play."""
    if _num(r.get("return_touchdown")) == 1:
        return int(_num(r.get("return_yards")) or _num(r.get("yards_gained")))
    return int(_num(r.get("yards_gained")))

def distill(rows, season_type="REG"):
    """rows: an iterable of dicts, one per play. Returns per-game records."""
    games = {}
    for r in rows:
        if r.get("season_type") and r["season_type"] != season_type: continue
        gid = r.get("game_id")
        if not gid: continue
        g = games.get(gid)
        if g is None:
            g = games[gid] = {
                "game_id": gid,
                "season": int(_num(r.get("season"))),
                "week": int(_num(r.get("week"))),
                "home": r.get("home_team"), "away": r.get("away_team"),
                "home_score": 0, "away_score": 0,
                "fg": defaultdict(int), "fg_yards": defaultdict(int),
                "long_td": defaultdict(int),
                "plays": 0,
            }
        g["plays"] += 1

        # final score: the last non-empty score on the game's plays
        hs, as_ = _num(r.get("home_score"), None), _num(r.get("away_score"), None)
        if hs is not None: g["home_score"] = int(hs)
        if as_ is not None: g["away_score"] = int(as_)

        # made field goals, credited to the kicking (possessing) team
        if r.get("field_goal_result") == "made" and r.get("posteam"):
            g["fg"][r["posteam"]] += 1
            g["fg_yards"][r["posteam"]] += int(_num(r.get("kick_distance")))

        # longest touchdown, any type, credited to td_team
        if _num(r.get("touchdown")) == 1 and r.get("td_team"):
            y = _td_yards(r)
            t = r["td_team"]
            if y > g["long_td"][t]: g["long_td"][t] = y

    out = []
    for g in games.values():
        h, a = g["home"], g["away"]
        out.append({
            "game_id": g["game_id"], "season": g["season"], "week": g["week"],
            "home": h, "away": a,
            "home_score": g["home_score"], "away_score": g["away_score"],
            "final": True,                      # set by the caller from schedules
            "fg":       {h: g["fg"][h],       a: g["fg"][a]},
            "fg_yards": {h: g["fg_yards"][h], a: g["fg_yards"][a]},
            "long_td":  {h: g["long_td"][h],  a: g["long_td"][a]},
        })
    return sorted(out, key=lambda x: (x["week"], x["game_id"]))
