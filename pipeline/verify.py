"""RULE CONFORMANCE TEST

Checks the code against the league rule book, rule by rule, and says pass or
fail on each one.

    python verify.py            # 2025, a completed season, as the test bed
    python verify.py 2025

This proves nothing about whether the NFL data is right. It proves that given
the data, the money is divided the way the rule book says it should be.
"""
import sys, json, copy, io, datetime, contextlib
import prizes, league, teams, distill, schedule, build, validate
from fetch import fetch_pbp

SEASON = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
AUCTION, PRICES, OWNERS = league.load()
UTC = datetime.timezone.utc
money = lambda c: f"${c/100:,.2f}"

RESULTS = []
def check(section, rule):
    """Decorator. The function returns a one-line note, or raises."""
    def wrap(fn):
        try:
            RESULTS.append((True, section, rule, fn() or ""))
        except AssertionError as e:
            RESULTS.append((False, section, rule, str(e) or "assertion failed"))
        except Exception as e:
            RESULTS.append((False, section, rule, f"{type(e).__name__}: {e}"))
        return fn
    return wrap

def eq(a, b, what):
    assert a == b, f"{what}: got {a}, expected {b}"

def eqm(a, b, what):
    assert a == b, f"{what}: got {money(a)}, expected {money(b)}"

# ---------------------------------------------------------------- test bed
print(f"loading {SEASON} ...", flush=True)
RAW_SCHED = schedule.fetch(SEASON)
SCHED = schedule.read(RAW_SCHED)
rows, _url, _missing = fetch_pbp(SEASON, distill.COLS)
GAMES = distill.distill(rows)
for g in GAMES:
    g["final"] = g["game_id"] in SCHED["finalIds"]

def board(games=None, manual=(), sched=None):
    with contextlib.redirect_stdout(io.StringIO()):
        return build.build_board(GAMES if games is None else games, AUCTION,
                                 PRICES, OWNERS, list(manual), SEASON,
                                 sched or SCHED)

def prize_of(b, name):
    l = next((x for x in b["ledger"] if x["prize"] == name), None)
    assert l is not None, f"{name} was never awarded"
    return l

def week(pairs, fg=None, wk=1):
    """A synthetic week, so one rule can be tested on its own."""
    fg = fg or {}
    gs = []
    for i, (h, hs, a, asc) in enumerate(pairs):
        gs.append({"game_id": f"t{i}", "season": SEASON, "week": wk,
                   "home": h, "away": a, "home_score": hs, "away_score": asc,
                   "final": True,
                   "fg": {h: fg.get(h, (0, 0))[0], a: fg.get(a, (0, 0))[0]},
                   "fg_yards": {h: fg.get(h, (0, 0))[1], a: fg.get(a, (0, 0))[1]},
                   "long_td": {h: 0, a: 0}})
    pr = dict(PRICES) | {"AAA": 10, "BBB": 20, "CCC": 30, "DDD": 40,
                         "CHEAP": 5, "PRICEY": 90}
    ow = dict(OWNERS)
    for t in ("AAA", "BBB", "CCC", "DDD", "CHEAP", "PRICEY"):
        ow[t] = "Tester"
    return prizes.Ctx(gs, ow, pr)

B = board()

# ================================================================= 2  the pot
@check("2", "The three pools are 40 / 45 / 15 per cent and total $2,500")
def _():
    post = prizes.POST_POOL
    reg  = 18 * 3800 + 27200 + sum(a for _, _, a in build.MINI.values())
    nov  = sum(prizes.NOVELTY.values())
    eqm(post, 100000, "postseason, 40%")
    eqm(reg,  112500, "regular season, 45%")
    eqm(nov,   37500, "novelty, 15%")
    eqm(post + reg + nov, 250000, "the pot")
    return "$1,000 + $1,125 + $375 = $2,500"

@check("2", "A split divides to the cent, odd pennies to the cheaper team first")
def _():
    out = prizes.split(10100, ["NYJ", "CAR", "ATL"], PRICES)
    eqm(sum(a for _, a in out), 10100, "the split")
    order = [PRICES[t] for t, _ in out]
    assert order == sorted(order), f"cheapest first, got {order}"
    assert out[0][1] >= out[-1][1], "the odd penny must go to the cheaper team"
    return "$101 three ways: " + ", ".join(f"{t} {money(a)}" for t, a in out)

# ================================================================= 4.1 weekly
@check("4.1", "The seven weekly prizes are 11/8/8/5/3/2/1, $38 a week, $684 a season")
def _():
    eqm(sum(prizes.WEEKLY.values()), 3800, "one week")
    eqm(prizes.WEEKLY["Team of the Week"], 1100, "Team of the Week")
    eqm(prizes.WEEKLY["Longest TD"], 100, "Longest TD")
    eq(len(prizes.WEEKLY), 7, "how many weekly prizes")
    eqm(18 * 3800, 68400, "the season")
    return "seven prizes, $38 a week, $684 across 18 weeks"

@check("4.1", "A drawn game has no loser: no Stinker, Price Check, Upset or TOTW")
def _():
    ctx = week([("AAA", 20, "BBB", 20)])
    assert prizes.stinker(ctx, 1) is None, "a draw produced a Stinker"
    assert prizes.price_check(ctx, 1) is None, "a draw produced a Price Check"
    assert prizes.upset(ctx, 2, 0, {"AAA": 0.0, "BBB": 1.0}) is None, "a draw produced an Upset"
    assert prizes.team_of_the_week(ctx, 1) is None, "a draw produced a Team of the Week"
    return "all four decline a drawn game"

@check("4.1", "Shootout pays both teams, and all four when two games tie")
def _():
    one = prizes.shootout(week([("AAA", 30, "BBB", 28), ("CCC", 10, "DDD", 7)]), 1)
    eq(len(one["winners"]), 2, "one high game pays")
    two = prizes.shootout(week([("AAA", 30, "BBB", 28), ("CCC", 29, "DDD", 29)]), 1)
    eq(len(two["winners"]), 4, "two games level on 58 pay")
    eqm(sum(w["amount"] for w in two["winners"]), 300, "the Shootout prize")
    return "2 teams normally, 4 on a tie, always $3 in total"

@check("4.1", "Most Field Goals breaks a tie on total field goal yardage")
def _():
    ctx = week([("AAA", 10, "BBB", 7), ("CCC", 10, "DDD", 7)],
               fg={"AAA": (3, 120), "CCC": (3, 90)})
    a = prizes.most_fgs(ctx, 1)
    eq(len(a["winners"]), 1, "the yardage tiebreak must separate them")
    eq(a["winners"][0]["team"], "AAA", "120 yards should beat 90")
    return "three field goals each, 120 yards beats 90"

@check("4.1", "Longest TD counts a return and credits the scoring team")
def _():
    r = {"season_type": "REG", "game_id": "g", "season": str(SEASON), "week": "1",
         "home_team": "AAA", "away_team": "BBB", "home_score": "7", "away_score": "0",
         "touchdown": "1", "return_touchdown": "1", "td_team": "AAA",
         "return_yards": "98", "yards_gained": "0", "posteam": "BBB", "defteam": "AAA"}
    g = distill.distill([r])[0]
    eq(g["long_td"]["AAA"], 98, "the 98-yard return")
    eq(g["long_td"]["BBB"], 0, "the offence")
    return "a 98-yard interception return pays the defence's owner"

@check("4.1", "Week 1 Upset never awards, and its $5 carries into Upset alone")
def _():
    ctx = week([("AAA", 30, "BBB", 3)])
    assert prizes.upset(ctx, 1, 0, {}) is None, "Week 1 must never award"
    _awards, carry = prizes.run_week(ctx, 1, {}, {})
    eqm(carry["Upset of the Week"], 500, "the carry")
    eqm(carry.get("Team of the Week", 0), 0, "no other prize may be touched")
    return "$5 carries, and only into Upset of the Week"

@check("4.1", "An unawarded Price Check carries into Price Check and nowhere else")
def _():
    ctx = week([("PRICEY", 30, "CHEAP", 3)])          # the dearer team won
    assert prizes.price_check(ctx, 5) is None, "no cheaper winner, so no award"
    _a, carry = prizes.run_week(ctx, 5, {}, {"PRICEY": 1.0, "CHEAP": 0.0})
    eqm(carry["Price Check"], 800, "the carry")
    nxt = week([("CHEAP", 30, "PRICEY", 3)], wk=6)
    a = prizes.price_check(nxt, 6, carry["Price Check"])
    eqm(a["amount"], 1600, "the following week")
    return "$8 carries, the next week pays $16"

# ================================================================= 4.2 bounty
@check("4.2", "The bounty is $1 a win, half for a tie, exactly $272 a season")
def _():
    eqm(sum(c["bounty"] for c in B["cat"].values()), 27200, "the season's bounty")
    return "$272 across 272 games"

@check("4.2", "Playoff wins pay no bounty")
def _():
    post = [g for g in SCHED["games"] if g["post"]]
    assert post, "the test season must have a postseason"
    assert all(g["week"] <= 18 for g in GAMES), "a playoff game reached the bounty"
    eqm(sum(c["bounty"] for c in B["cat"].values()), 27200, "the bounty")
    return f"{len(post)} playoff games excluded, bounty still $272"

# =================================================================== 4.3 mini
@check("4.3", "Mini-seasons are $49, $54 and $66 over Weeks 1-6, 7-12 and 13-18")
def _():
    eqm(sum(a for _, _, a in build.MINI.values()), 16900, "the three titles")
    eq(build.MINI[1], (1, 6, 4900), "Mini-Season 1")
    eq(build.MINI[2], (7, 12, 5400), "Mini-Season 2")
    eq(build.MINI[3], (13, 18, 6600), "Mini-Season 3")
    return "$49 + $54 + $66 = $169"

@check("4.3", "A tie counts as half a win in a mini-season record")
def _():
    tied = [g for g in GAMES if g["home_score"] == g["away_score"]]
    assert tied, "the test season contains no drawn game to check"
    g = tied[0]
    n = 1 if g["week"] <= 6 else (2 if g["week"] <= 12 else 3)
    t = B["msTables"][f"Mini-Season {n}"]
    o = OWNERS[g["home"]]
    row = next(r for r in t["rows"] if r["owner"] == o)
    eq(row["g"], row["w"] + row["l"] + row["t"], "games played must include draws")
    assert row["t"] >= 1, "the drawn game was dropped from the record"
    return (f"{g['home']} drew in Week {g['week']}; "
            f"{o} shows {row['w']}-{row['l']}-{row['t']} over {row['g']} games")

@check("4.3", "Mini-season ties break on wins, then differential per game, then split")
def _():
    t = B["msTables"]["Mini-Season 1"]
    assert all("diff" in r for r in t["rows"]), "differential per game is not recorded"
    order = [(r["pct"], r["w"], r["diff"]) for r in t["rows"]]
    assert order == sorted(order, reverse=True), "the table is not in full tiebreak order"
    return "ranked on win %, then wins, then differential per game"

# ================================================================= 5 novelty
@check("5", "The novelty pool is $101 + $101 + $101 + $72 = $375")
def _():
    eqm(sum(prizes.NOVELTY.values()), 37500, "the novelty pool")
    eqm(prizes.NOVELTY["Bottom of the Barrel"], 7200, "Bottom of the Barrel")
    eqm(prizes.NOVELTY["The Pink Slip"], 10100, "The Pink Slip")
    return "three at $101 and one at $72"

@check("5", "Highest single-game score splits when two teams reach the same high")
def _():
    g2 = copy.deepcopy(GAMES)
    hi = max(max(g["home_score"], g["away_score"]) for g in g2)
    victim = next(g for g in g2 if max(g["home_score"], g["away_score"]) < hi)
    victim["home_score"] = hi
    l = prize_of(board(g2), "Highest single-game score")
    eq(len(l["winners"]), 2, "two teams at the same high")
    eqm(sum(w["amount"] for w in l["winners"]), 10100, "the prize")
    return f"forced a tie at {hi} points: {money(l['winners'][0]['amount'])} each"

@check("5", "Bottom of the Barrel ranks on record, then differential, then splits")
def _():
    rec = {t["abbr"]: t for t in B["teams"]}
    key = lambda a: (round((rec[a]["w"] + .5 * rec[a]["t"])
                           / max(1, rec[a]["w"] + rec[a]["l"] + rec[a]["t"]), 9),
                     rec[a]["pf"] - rec[a]["pa"])
    l = prize_of(B, "Bottom of the Barrel")
    won = l["winners"][0]["abbr"]
    assert key(won) == min(key(a) for a in rec), "the worst team did not win it"
    level = [a for a in rec if key(a) == key(won)]
    eq(len(l["winners"]), len(level), "everyone level must share")
    r = rec[won]
    return f"{won} at {r['w']}-{r['l']}, {r['pf']-r['pa']:+d} differential"

@check("5", "The Pink Slip pays the first firing; only same-day firings split")
def _():
    apart = [{"type": "The Pink Slip", "team": "NYJ", "date": "2025-10-13",
              "week": 6, "status": "confirmed", "detail": "first"},
             {"type": "The Pink Slip", "team": "CHI", "date": "2025-12-15",
              "week": 15, "status": "confirmed", "detail": "later"}]
    l1 = prize_of(board(manual=apart), "The Pink Slip")
    eq(len(l1["winners"]), 1, "a later firing must not share")
    eqm(l1["winners"][0]["amount"], 10100, "the first firing takes it all")
    same = copy.deepcopy(apart)
    same[1]["date"] = "2025-10-13"
    l2 = prize_of(board(manual=same), "The Pink Slip")
    eq(len(l2["winners"]), 2, "same-day firings must share")
    eqm(sum(w["amount"] for w in l2["winners"]), 10100, "the prize")
    return "weeks apart: $101 to the first. Same day: $50.50 each"

@check("5", "Untriggered novelty money moves onto the postseason ladder")
def _():
    eqm(board()["postFromNovelty"], 20200, "neither triggered")
    qb = [{"type": "QB Down", "team": "BAL", "date": "2025-11-02", "week": 9,
           "status": "confirmed", "detail": "x"}]
    eqm(board(manual=qb)["postFromNovelty"], 10100, "one triggered")
    both = qb + [{"type": "The Pink Slip", "team": "NYJ", "date": "2025-10-13",
                  "week": 6, "status": "confirmed", "detail": "y"}]
    eqm(board(manual=both)["postFromNovelty"], 0, "both triggered")
    return "$202, $101 or $0 depending on how many triggered"

# ============================================================== 3 postseason
@check("3", "The ladder is 25 / 14 / 10 / 6.5 / 2.5 per cent across 14 teams")
def _():
    t = prizes.ladder(100000)
    eqm(t["champion"], 25000, "champion, 25%")
    eqm(t[22], 14000, "runner-up, 14%")
    eqm(t[21], 10000, "conference loser, 10%")
    eqm(t[20],  6500, "divisional loser, 6.5%")
    eqm(t[19],  2500, "wild card loser, 2.5%")
    eqm(t[19]*6 + t[20]*4 + t[21]*2 + t[22] + t["champion"], 100000, "the pool")
    return "$250 / $140 / $100 / $65 / $25 = $1,000 over 14 teams"

@check("3", "The ladder still ties exactly when extra money is rolled into it")
def _():
    for pool in (100000, 110100, 120200, 123456):
        t = prizes.ladder(pool)
        eqm(t[19]*6 + t[20]*4 + t[21]*2 + t[22] + t["champion"], pool,
            f"a pool of {money(pool)}")
    return "ties at $1,000, $1,101, $1,202 and $1,234.56"

@check("3", "A playoff round pays only once every game in it is final")
def _():
    part = [dict(g, final=(g["final"] and g["type"] != "WC")) for g in RAW_SCHED]
    s2 = schedule.read(part)
    rounds, awards = prizes.postseason(s2["games"], OWNERS, 100000)
    wc = next(r for r in rounds if r["code"] == "WC")
    assert not wc["settled"], "an unfinished round settled"
    assert not any(a["week"] == 19 for a in awards), "an unfinished round paid out"
    return "wild card round unfinished: nothing paid"

# ================================================================ the pot ties
def reconcile(b, label):
    m = b["meta"]
    total = (m["awarded"] + m["inPlay"] + m["weeklyLeft"] + m["bountyLeft"]
             + sum(p["amount"] for p in b["pending"]))
    assert total == m["pot"], f"{label}: itemised {money(total)}, pot {money(m['pot'])}"
    assert m["awarded"] + m["inPlay"] <= m["pot"], f"{label}: overpaid"

@check("2", "Every dollar has a destination at every point in the season")
def _():
    stamps = ("2025-09-09T12:00:00", "2025-10-05T20:30:00", "2025-11-25T12:00:00",
              "2026-01-06T12:00:00", "2026-01-13T12:00:00", "2026-02-10T12:00:00")
    for s in stamps:
        now = datetime.datetime.fromisoformat(s).replace(tzinfo=UTC)
        sch = schedule.read(schedule.rewind(RAW_SCHED, now), now)
        reconcile(board(sched=sch), s)
    return f"reconciles at {len(stamps)} points from Week 1 to the Super Bowl"

@check("2", "Weekly money that cannot be awarded is swept onto the ladder")
def _():
    keep = prizes.price_check
    prizes.price_check = lambda ctx, w, carry=0: None
    try:
        b = board()
    finally:
        prizes.price_check = keep
    eqm(b["postFromWeekly"], 14400, "a season in which Price Check never awards")
    reconcile(b, "swept")
    return "$144 reaches the ladder instead of vanishing"

@check("", "No award pays $0, and no award pays a team nobody owns")
def _():
    errs = validate.check_awards(B["ledger"])
    assert not errs, "; ".join(errs[:3])
    return f"{len(B['ledger'])} awards checked"

@check("", "A settled week cannot change without being caught")
def _():
    b2 = copy.deepcopy(B)
    next(l for l in b2["ledger"] if l["prize"] == "Longest TD")["winners"][0]["amount"] = 999
    errs = validate.check_frozen(b2["ledger"], B["ledger"], set(range(1, 19)))
    assert errs, "a tampered week went undetected"
    return errs[0]

# ==================================================================== report
print()
print(f"RULE CONFORMANCE  |  {SEASON} season  |  {len(RESULTS)} checks")
print("=" * 92)
sec = None
for ok, s, rule, note in RESULTS:
    if s != sec:
        print(f"\n  {'Section ' + s if s else 'General'}")
        sec = s
    print(f"    {'PASS' if ok else 'FAIL'}  {rule}")
    if note:
        print(f"          {note}")
bad = [r for r in RESULTS if not r[0]]
print()
print("=" * 92)
print(f"{len(RESULTS) - len(bad)} of {len(RESULTS)} checks pass."
      + ("" if not bad else f"  {len(bad)} FAILED."))
sys.exit(1 if bad else 0)
