"""The schedule, which is what tells us when a week is live.

Play-by-play alone cannot answer this. It updates while games are still being
played, so a team leading at halftime looks exactly like a team that won. The
schedule is the only thing that says how many games a week is supposed to have
and which of them are actually over.

The rule Riggs set: a week goes live at the opening kickoff and closes the
instant its last game is final. Nothing between the final whistle and the next
kickoff is live.

Source: nflverse/nfldata games.csv, the same project behind the play-by-play.
Standard library only, so the scheduled job has nothing to install.
"""
import csv, io, urllib.request, datetime

URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                      # no tzdata: fall back to Eastern Daylight
    ET = datetime.timezone(datetime.timedelta(hours=-4))


def _kick(day, time_):
    """Kickoff as an aware UTC datetime. gametime is Eastern."""
    if not day: return None
    try:
        h, m = (time_ or "13:00").split(":")[:2]
        naive = datetime.datetime.strptime(day, "%Y-%m-%d").replace(
            hour=int(h), minute=int(m))
        return naive.replace(tzinfo=ET).astimezone(datetime.timezone.utc)
    except Exception:
        return None


def fetch(season, timeout=120):
    """Every regular season game for one season, with kickoff and final flag."""
    req = urllib.request.Request(URL, headers={"User-Agent": "calcutta-pipeline"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    rd = csv.DictReader(io.StringIO(raw.decode("utf-8", "replace")))
    out = []
    for row in rd:
        if row.get("season") != str(season):      continue
        if (row.get("game_type") or "") != "REG": continue
        # a game is over when the schedule carries its result, not before
        done = (row.get("result") or "").strip() != ""
        out.append({"game_id": row["game_id"], "week": int(row["week"]),
                    "kick": _kick(row.get("gameday"), row.get("gametime")),
                    "final": done})
    return out


def week_state(sched, now=None):
    """Per week: how many games, how many final, and whether it has kicked off."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    weeks = {}
    for g in sched:
        w = weeks.setdefault(g["week"], {"total": 0, "final": 0, "kick": None})
        w["total"] += 1
        if g["final"]: w["final"] += 1
        if g["kick"] and (w["kick"] is None or g["kick"] < w["kick"]):
            w["kick"] = g["kick"]
    for w in weeks.values():
        w["started"] = bool(w["kick"] and now >= w["kick"])
        w["complete"] = w["total"] > 0 and w["final"] == w["total"]
    return weeks


def rewind(sched, now):
    """For replay only. Pretend a completed season is only played up to `now`,
    so the live-week behaviour can be checked against a real Sunday afternoon
    instead of waiting for one. A game counts as over three hours after kickoff.
    """
    RUN = datetime.timedelta(hours=3, minutes=15)
    return [dict(g, final=bool(g["final"] and g["kick"] and g["kick"] + RUN <= now))
            for g in sched]


def read(sched, now=None):
    """Boil the schedule down to the three things the board needs.

    through   the last week where every game is final, so it can be paid
    live      the earliest week that has kicked off and is not finished, or None
    next_kick the next kickoff still ahead of us, or None
    """
    weeks = week_state(sched, now)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    done = [w for w, s in weeks.items() if s["complete"]]
    through = max(done) if done else 0
    live = min([w for w, s in weeks.items()
                if s["started"] and not s["complete"]], default=None)
    ahead = [g["kick"] for g in sched if g["kick"] and g["kick"] > now]
    return {"weeks": weeks, "through": through, "live": live,
            "finalIds": {g["game_id"] for g in sched if g["final"]},
            "nextKick": min(ahead) if ahead else None}
