"""Turn a season of play-by-play into board.json, the one file the page reads.

    python build.py 2026          # the live season
    python build.py 2025 --test   # a completed season, to prove the whole run

Inputs are stored, outputs are recomputed. Every prize is derived from the
games every time, so fixing a rule fixes the whole season at once.
"""
import sys, json, os, datetime
import distill, prizes, validate, league, teams, schedule
from fetch import fetch_pbp

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
POT, BUYIN, WEEKS = 250000, 25000, 18
LAST_WEEK = 22          # Week 18, then the four postseason rounds
NOVELTY = {"Highest single-game score":10100, "The Pink Slip":10100,
           "QB Down":10100, "Bottom of the Barrel":7200}
MINI = {1:(1,6,4900), 2:(7,12,5400), 3:(13,18,6600)}
p3 = lambda v: f"{v:.3f}".lstrip("0")
def money(c):
    return "$" + (f"{c//100:,}" if c % 100 == 0 else f"{c/100:,.2f}")


MANUAL_TYPES = {"The Pink Slip", "QB Down"}

def load_void():
    """Game ids the commissioner has struck out, because the game was cancelled
    and will never have a result. Without this a single abandoned game leaves
    its week forever incomplete and freezes every prize after it."""
    path = os.path.join(DATA, "manual.json")
    if not os.path.exists(path): return []
    try:
        with open(path) as f: v = json.load(f).get("void_games", [])
    except Exception:
        return []
    return [x for x in v if isinstance(x, str) and x.strip()]


def load_manual(owners):
    """Read data/manual.json, the one file entered by hand.

    Two prizes cannot be read off a scoreboard: the first head coach fired and
    the first quarterback ruled out for the season. They are typed in here.
    Every entry is checked before a dollar moves, because a typo in a team
    abbreviation would quietly pay the wrong owner $101.
    """
    path = os.path.join(DATA, "manual.json")
    if not os.path.exists(path): return []
    try:
        with open(path) as f: raw = json.load(f)
    except json.JSONDecodeError as e:
        print(f"\nmanual.json is not valid JSON: line {e.lineno}, column {e.colno}, {e.msg}")
        print("A missing comma or quote is the usual cause. Nothing was written.")
        sys.exit(1)

    entries, errs = raw.get("entries", []), []
    if not isinstance(entries, list):
        print("\nmanual.json: 'entries' must be a list. Nothing was written."); sys.exit(1)

    seen = set()
    for i, m in enumerate(entries, 1):
        where = f"entry {i}"
        if not isinstance(m, dict):
            errs.append(f"{where}: should be an object in {{ }}"); continue
        t = m.get("type")
        if t not in MANUAL_TYPES:
            errs.append(f"{where}: type is {t!r}, must be exactly one of "
                        f"{sorted(MANUAL_TYPES)}"); continue
        m.setdefault("status", "confirmed")
        if m["status"] not in ("confirmed", "proposed"):
            errs.append(f"{where}: status is {m['status']!r}, must be 'confirmed' or 'proposed'")
        tm = m.get("team")
        if tm not in owners:
            errs.append(f"{where}: team is {tm!r}, must be one of the 32 abbreviations, "
                        f"for example {', '.join(sorted(owners)[:6])} ...")
        w = m.get("week")
        if not isinstance(w, int) or not 1 <= w <= WEEKS:
            errs.append(f"{where}: week is {w!r}, must be a whole number from 1 to {WEEKS}")
        d = m.get("date")
        # The rules turn on a date, not a week: the FIRST firing wins and only
        # same-day firings split. Without a date neither can be decided.
        try:
            datetime.date.fromisoformat(str(d))
        except (TypeError, ValueError):
            errs.append(f"{where}: date is {d!r}, must be YYYY-MM-DD, "
                        f"for example \"2026-10-13\". The rules pay the first "
                        f"trigger and split only same-day ones, so the day matters.")
        m.setdefault("detail", "Entered by hand")
        if m["status"] == "confirmed":
            if (t, tm) in seen:
                errs.append(f"{where}: {t} is confirmed twice for {tm}.")
            seen.add((t, tm))

    if errs:
        print("\nmanual.json has problems. Nothing was written.")
        for e in errs: print("  !", e)
        sys.exit(1)

    for m in entries:
        print(f"manual   {m['type']}, {m['team']}, {m['date']} "
              f"(week {m['week']}, {m['status']})")
    return entries


def records(games, upto):
    """Team records through a given week."""
    r = {a: {"w":0,"l":0,"t":0,"pf":0,"pa":0} for a in teams.TEAMS}
    for g in games:
        if g["week"] > upto: continue
        h, a = g["home"], g["away"]
        r[h]["pf"] += g["home_score"]; r[h]["pa"] += g["away_score"]
        r[a]["pf"] += g["away_score"]; r[a]["pa"] += g["home_score"]
        if   g["home_score"] > g["away_score"]: r[h]["w"]+=1; r[a]["l"]+=1
        elif g["away_score"] > g["home_score"]: r[a]["w"]+=1; r[h]["l"]+=1
        else: r[h]["t"]+=1; r[a]["t"]+=1
    return r


def mini_season(games, owners, lo, hi):
    """Combined win percentage across every team an owner holds.

    Rule book, 4.3: a tie counts as half a win. Level owners go first to
    total wins in the segment, then to the better average point differential
    per game across their teams. Only after all three does it split.
    """
    who = sorted(set(owners.values()))
    rec = {o: {"w":0,"l":0,"t":0,"pf":0,"pa":0,"g":0} for o in who}
    for g in games:
        if not (lo <= g["week"] <= hi): continue
        for t, s, opp in ((g["home"], g["home_score"], g["away_score"]),
                          (g["away"], g["away_score"], g["home_score"])):
            o = owners.get(t)
            if not o: continue
            r = rec[o]
            r["g"] += 1; r["pf"] += s; r["pa"] += opp
            if   s > opp: r["w"] += 1
            elif s < opp: r["l"] += 1
            else:         r["t"] += 1
    pct  = {o: (rec[o]["w"] + .5*rec[o]["t"]) / max(1, rec[o]["g"]) for o in who}
    diff = {o: (rec[o]["pf"] - rec[o]["pa"]) / max(1, rec[o]["g"]) for o in who}
    # the full ordering key, best first. Rounded so float noise never decides money.
    rank = lambda o: (round(pct[o], 9), rec[o]["w"], round(diff[o], 6))
    table = [{"owner":o, "w":rec[o]["w"], "l":rec[o]["l"], "t":rec[o]["t"],
              "g":rec[o]["g"], "pct":round(pct[o],4), "diff":round(diff[o],2),
              "teams":sum(1 for t,x in owners.items() if x==o)}
             for o in sorted(who, key=rank, reverse=True)]
    return pct, table, rec, rank


def split_owner(amount, who, spent=None):
    """Owner-level split, to the cent.

    The rules give odd pennies on a team prize to the lower-priced team. There
    is no team here, so the same principle applies one level up: the odd
    pennies go to whoever spent least at auction. Alphabetical order, which
    this used to use, quietly favours whoever is early in the alphabet every
    single time."""
    spent = spent or {}
    who = sorted(who, key=lambda o: (spent.get(o, 0), o))
    base, rem = amount//len(who), amount % len(who)
    return [(o, base + (1 if i < rem else 0)) for i, o in enumerate(who)]


def settle_point(games, sched):
    """How far the board can be paid, and which week is live.

    A week is settled only when the schedule says every game is final AND we
    actually hold play-by-play for all of them. Play-by-play lags the final
    whistle by a few minutes, and paying a week we cannot fully score would
    hand somebody a prize on incomplete evidence.
    """
    have = {}
    for g in games:
        if g["final"]: have[g["week"]] = have.get(g["week"], 0) + 1
    if not sched:
        played = sorted({g["week"] for g in games})
        return (max(played) if played else 0), None
    through = 0
    for w in range(1, LAST_WEEK+1):
        st = sched["weeks"].get(w)
        if not st or not st["complete"]: break
        # A regular week also needs play-by-play, because its seven prizes are
        # scored from plays. A postseason round only needs who won, which the
        # schedule already carries, so it settles without waiting for anything.
        if w <= WEEKS and have.get(w, 0) < st["total"]: break
        through = w
    # the live week is always the one after the last settled week, and only
    # once it has actually kicked off. Between the final whistle and the next
    # kickoff there is no live week at all.
    nxt = sched["weeks"].get(through + 1)
    live = (through + 1) if (nxt and nxt["started"]) else None
    return through, live


def build_board(games, auction, prices, owners, manual, season, sched=None):
    through, live_w = settle_point(games, sched)
    last = through
    settled = [g for g in games if g["final"] and g["week"] <= through]
    ledger, carries = [], {}

    # ---- the seven weekly prizes, week by week, carries flowing forward
    for w in range(1, last+1):
        if not any(g["week"] == w for g in settled): continue
        pre = {}
        r = records(settled, w-1)
        for t, x in r.items():
            n = x["w"] + x["l"] + x["t"]
            if n: pre[t] = (x["w"] + 0.5*x["t"]) / n
        ctx = prizes.Ctx(settled, owners, prices)
        awards, carries = prizes.run_week(ctx, w, carries, pre)
        ledger += awards

    # ---- win bounty, $1 a win, credited per team
    rec = records(settled, last)
    bounty = {a: rec[a]["w"]*100 + int(rec[a]["t"]*50) for a in teams.TEAMS}

    # ---- mini-seasons, settled only once their window has completed
    ms_tables = {}
    for n, (lo, hi, amt) in MINI.items():
        if last < hi: continue
        pct, table, mrec, rank = mini_season(settled, owners, lo, hi)
        ms_tables[f"Mini-Season {n}"] = {"n":n,"lo":lo,"hi":hi,"final":True,"rows":table}
        best = max(rank(o) for o in pct)
        win = [o for o in pct if rank(o) == best]
        def rc(o):
            r = mrec[o]
            return f"{r['w']}-{r['l']}" + (f"-{r['t']}" if r["t"] else "")
        ledger.append({"week":hi, "prize":f"Mini-Season {n}", "amount":amt,
            "split":len(win)>1,
            "detail":f"Weeks {lo} to {hi}, best combined win percentage, {p3(pct[win[0]])}",
            "winners":[{"team":None,"abbr":None,"owner":o,"amount":a,
                        "detail":f"{rc(o)} across their teams, "
                                 f"{p3(pct[o])} win percentage"}
                       for o, a in split_owner(amt, win, auction["spent_cents"])]})

    # ---- novelty settled at the end of the regular season
    if last >= WEEKS:
        # "Most points scored by one team in one game across the full regular
        # season. If two teams reach the same high, they split the prize."
        # Two teams can hit the same number in different games, so this is a
        # search over every team-game, not over games.
        best, when = {}, {}
        for g in settled:
            for t, sc in ((g["home"], g["home_score"]), (g["away"], g["away_score"])):
                if sc > best.get(t, -1): best[t], when[t] = sc, g["week"]
        hi = max(best.values())
        hot = sorted([t for t, sc in best.items() if sc == hi])
        amt = NOVELTY["Highest single-game score"]
        ledger.append({"week":WEEKS, "prize":"Highest single-game score",
            "amount":amt, "split":len(hot) > 1,
            "detail":f"{hi} points" + (f", Week {when[hot[0]]}" if len(hot)==1 else ""),
            "winners":[{"team":teams.name(t),"abbr":t,"owner":owners.get(t),"amount":a,
                        "detail":f"{hi} points in Week {when[t]}"}
                       for t, a in prizes.split(amt, hot, prices)]})

        # "Owner of the team with the worst regular season record. Ties are
        # broken by worst point differential across the full season. If still
        # tied, the prize splits evenly." Record is win percentage, so a tie
        # counts as half a win. Doubled to keep it in whole numbers.
        # Record means win percentage. Teams can finish on different numbers of
        # games if one is cancelled, and a 2-15 team is worse than a 2-14 one.
        key = lambda a: (round((rec[a]["w"] + .5*rec[a]["t"])
                               / max(1, rec[a]["w"]+rec[a]["l"]+rec[a]["t"]), 9),
                         rec[a]["pf"] - rec[a]["pa"])
        worst = min(key(a) for a in teams.TEAMS)
        bots = sorted([a for a in teams.TEAMS if key(a) == worst])
        amt = NOVELTY["Bottom of the Barrel"]
        wl = lambda a: (f"{rec[a]['w']}-{rec[a]['l']}"
                        + (f"-{rec[a]['t']}" if rec[a]["t"] else ""))
        ledger.append({"week":WEEKS, "prize":"Bottom of the Barrel",
            "amount":amt, "split":len(bots) > 1,
            "detail":f"{wl(bots[0])}, worst record",
            "winners":[{"team":teams.name(a),"abbr":a,"owner":owners.get(a),"amount":x,
                        "detail":f"{wl(a)}, {rec[a]['pf']-rec[a]['pa']:+d} differential"}
                       for a, x in prizes.split(amt, bots, prices)]})

    # ---- manual entries: Pink Slip, QB Down, corrections
    # "First head coach fired... Same-day firings split the prize." So the
    # EARLIEST date wins outright, and only entries sharing that exact date
    # divide it. A firing in Week 15 does not share in a Week 2 firing's money.
    by_type = {}
    for m in manual:
        if m.get("status") == "proposed": continue      # not confirmed yet
        if m["type"] in ("The Pink Slip", "QB Down"):
            by_type.setdefault(m["type"], []).append(m)
    for ptype, ms in by_type.items():
        first = min(m["date"] for m in ms)
        won   = [m for m in ms if m["date"] == first]
        later = [m for m in ms if m["date"] != first]
        if later:
            print(f"note     {ptype}: {len(later)} later entr"
                  f"{'y' if len(later)==1 else 'ies'} recorded but not paid. "
                  f"{first} was first.")
        amt = NOVELTY[ptype]
        why = {m["team"]: m.get("detail", "") for m in won}
        ledger.append({"week":min(m["week"] for m in won), "prize":ptype,
            "amount":amt, "split":len(won) > 1, "manual":True,
            "detail":won[0].get("detail",""),
            "winners":[{"team":teams.name(t),"abbr":t,"owner":owners.get(t),
                        "amount":a, "detail":why[t]}
                       for t, a in prizes.split(amt, [m["team"] for m in won], prices)]})

    # ---- novelty windows close at the end of Week 18. Rules, Section 5:
    # "If a prize has not been triggered by then, its money moves to the
    # postseason pool and is paid out on the ladder percentages." Only the two
    # trigger-based prizes can go unclaimed; the other two always resolve.
    # This must run AFTER the manual entries above, or a Pink Slip that was
    # entered by hand would still be treated as untriggered and its $101 would
    # be paid twice.
    TRIGGERED = {"The Pink Slip", "QB Down"}
    have_prizes = {l["prize"] for l in ledger}
    rolled = weekly_stranded = 0
    if last >= WEEKS:
        rolled = sum(NOVELTY[p] for p in sorted(TRIGGERED) if p not in have_prizes)
        # The seven weekly prizes are worth exactly $38 a week, $684 over the
        # season. Price Check and Upset carry into the next week's own prize,
        # but Week 18 has no next week, and a prize that simply cannot be
        # awarded is not carried at all. Either way the rules require that
        # "every pool ties exactly to the pot", so whatever the weekly
        # scoreboard did not pay follows the novelty money onto the ladder.
        weekly_paid = sum(l["amount"] for l in ledger if l["prize"] in prizes.WEEKLY)
        weekly_stranded = max(0, WEEKS * 3800 - weekly_paid)
        # The bounty is $1 a win over 272 games. A cancelled game is never
        # played and never pays, so that dollar follows the same route.
        weekly_stranded += max(0, 27200 - sum(bounty.values()))
    post_pool = prizes.POST_POOL + rolled + weekly_stranded
    tier = prizes.ladder(post_pool)

    # ---- the postseason ladder, settled a round at a time
    post_rounds, post_awards = ([], [])
    if sched:
        post_rounds, post_awards = prizes.postseason(sched["games"], owners, post_pool)
        ledger += [a for a in post_awards if a["week"] <= through]

    # ---- fill in full names on weekly awards, which carry abbreviations
    for l in ledger:
        for x in l["winners"]:
            if x.get("abbr") is None and x.get("team") in teams.TEAMS:
                x["abbr"] = x["team"]; x["team"] = teams.name(x["abbr"])

    # ---- roll everything up
    who = sorted(set(owners.values()))
    cat = {o: {"weekly":0,"bounty":0,"mini":0,"novelty":0,"post":0} for o in who}
    earned = {a: bounty[a] for a in teams.TEAMS}
    WEEKLY = set(prizes.WEEKLY)
    for l in ledger:
        for x in l["winners"]:
            if not x["owner"]: continue
            k = ("weekly" if l["prize"] in WEEKLY else
                 "post" if l["prize"] == prizes.POST_PRIZE else
                 "mini" if l["prize"].startswith("Mini-Season") else "novelty")
            cat[x["owner"]][k] += x["amount"]
            if x["abbr"]: earned[x["abbr"]] += x["amount"]
    for a, v in bounty.items():
        if owners.get(a): cat[owners[a]]["bounty"] += v

    won = {o: sum(cat[o].values()) for o in who}
    awarded = sum(won.values())

    # ---- the live week, if one is in progress
    # Leaders only, computed from the games already final. Nothing here is paid
    # and nothing here counts in the standings until the last game goes final.
    live, in_play, dead_amt = None, 0, 0
    if live_w and live_w > WEEKS:
        # A live playoff round. There are no weekly prizes here; the money on
        # the table is the ladder for this round, and it pays when the round
        # is over, the same as a regular week.
        r = next((x for x in post_rounds if x["week"] == live_w), None)
        if r:
            live = {"week":live_w, "started":True, "post":True,
                    "round":r["code"], "label":r["label"],
                    "gamesTotal":r["gamesTotal"], "gamesFinal":r["gamesFinal"],
                    "bounty":0, "prizes":[]}
            in_play = r["amount"]
    elif live_w:
        pre = {}
        r0 = records(settled, live_w-1)
        for t, x in r0.items():
            n = x["w"] + x["l"] + x["t"]
            if n: pre[t] = (x["w"] + 0.5*x["t"]) / n
        lg = [g for g in games if g["week"] == live_w and g["final"]]
        lctx = prizes.Ctx(lg, owners, prices)
        lawards, _ = prizes.run_week(lctx, live_w, carries, pre)
        by = {a["prize"]: a for a in lawards}
        plist = []
        for name, face in prizes.WEEKLY.items():
            a = by.get(name)
            # Week 1 Upset cannot be won, because every team goes in 0-0.
            # Showing it as money in play would overstate the bar by $5.
            dead = (name == "Upset of the Week" and live_w == 1)
            plist.append({"prize":name,
                "amount": a["amount"] if a else face + carries.get(name, 0),
                "carry": dead,
                "note": ("Nobody can win this in Week 1, because every team "
                         "starts 0-0. It carries into Week 2.") if dead else None,
                "leaders":[{"abbr":x["team"], "owner":x["owner"], "why":x["detail"]}
                           for x in (a["winners"] if a else [])]})
        lbounty = 0
        for g in lg:
            for t, s, o in ((g["home"],g["home_score"],g["away_score"]),
                            (g["away"],g["away_score"],g["home_score"])):
                if not owners.get(t): continue
                if   s > o:  lbounty += prizes.BOUNTY_PER_WIN
                elif s == o: lbounty += prizes.BOUNTY_PER_WIN // 2
        st = sched["weeks"][live_w]
        live = {"week":live_w, "started":True, "gamesTotal":st["total"],
                "gamesFinal":len(lg), "bounty":lbounty, "prizes":plist}
        in_play = sum(p["amount"] for p in plist if not p["carry"]) + lbounty
        dead_amt = sum(p["amount"] for p in plist if p["carry"])

    # weeks not yet started, plus any carry that is not already in play
    # Once Week 18 is done, anything the scoreboard did not pay has already
    # been swept onto the ladder above. Claiming it here as well would count
    # the same dollars twice and the pot would stop tying.
    from_wk = min(WEEKS, live_w if live_w else last)
    if last >= WEEKS:
        weekly_left = bounty_left = 0
    else:
        weekly_left = (max(0, WEEKS - from_wk) * 3800
                       + (dead_amt if live_w else sum(carries.values())))
        bounty_left = max(0, 27200 - sum(bounty.values()) - (live["bounty"] if live else 0))

    # ---- what is still to come, with live leaders where they exist
    lead_hi = lead_bot = "Not started"
    if settled:
        _b = {}
        for g in settled:
            for t, sc in ((g["home"], g["home_score"]), (g["away"], g["away_score"])):
                _b[t] = max(_b.get(t, -1), sc)
        _h = max(_b.values())
        _t = sorted([t for t, sc in _b.items() if sc == _h])
        lead_hi = (", ".join(f"{t} ({owners.get(t)})" for t in _t) + f", {_h} points")
        _k = lambda a: (round((rec[a]["w"] + .5*rec[a]["t"])
                              / max(1, rec[a]["w"]+rec[a]["l"]+rec[a]["t"]), 9),
                        rec[a]["pf"] - rec[a]["pa"])
        _w = min(_k(a) for a in teams.TEAMS)
        _bt = sorted([a for a in teams.TEAMS if _k(a) == _w])
        lead_bot = (", ".join(f"{a} ({owners.get(a)})" for a in _bt)
                    + f", {rec[_bt[0]]['w']}-{rec[_bt[0]]['l']}")
    done_prizes = {l["prize"] for l in ledger}
    pending = []
    def pend(p, amt, when, lead, note):
        if p not in done_prizes: pending.append(
            {"prize":p,"amount":amt,"when":when,"lead":lead,"note":note})
    # The ladder pays a round at a time, so it is both awarded and pending at
    # once. Pend whatever is left of the pool rather than the whole thing.
    post_paid = sum(a["amount"] for a in ledger if a["prize"] == prizes.POST_PRIZE)
    post_left = post_pool - post_paid - (in_play if (live_w and live_w > WEEKS) else 0)
    extra = rolled + weekly_stranded
    bits = []
    if rolled: bits.append(f"${rolled/100:,.0f} from novelty prizes that were never triggered")
    if weekly_stranded: bits.append(f"${weekly_stranded/100:,.2f} of weekly prize money "
                                    f"that could not be awarded")
    rolled_note = ("" if not extra else
        " Includes " + " and ".join(bits) + ", paid out on the same ladder percentages.")
    if post_left > 0:
        nextr = next((r for r in post_rounds if not r["settled"]), None)
        if post_paid or (live_w and live_w > WEEKS):
            lead = (f"{nextr['label']} round next" if nextr
                    else f"${post_paid/100:,.0f} paid so far")
        elif post_rounds:
            lead = "Bracket set, Wild Card round next"
        else:
            lead = "Not started"
        pending.append({"prize":"Postseason ladder", "amount":post_left,
            "when":"Round by round", "lead":lead,
            "note":(f"14 teams pay, from {money(tier['champion'])} for the champion "
                    f"down to {money(tier[19])} for a wild card loss." + rolled_note)})
    for n,(lo,hi,amt) in MINI.items():
        if f"Mini-Season {n}" in done_prizes: continue
        if last >= lo:
            thru = min(last, hi)
            pct, table, mr, rank = mini_season(settled, owners, lo, thru)
            ms_tables[f"Mini-Season {n}"] = {"n":n,"lo":lo,"hi":hi,"thru":thru,
                                             "final":False,"rows":table}
            b = max(rank(o) for o in pct); ldr = [o for o in pct if rank(o) == b]
            lead = (" and ".join(ldr) + f" {p3(pct[ldr[0]])}, {mr[ldr[0]]['w']}-{mr[ldr[0]]['l']}"
                    f" over Weeks {lo} to {thru}")
        else:
            lead = "Not started"
        pend(f"Mini-Season {n}", amt, f"After Week {hi}", lead,
             f"Weeks {lo} to {hi}, best combined win percentage")
    pend("Highest single-game score",10100,"End of Week 18", lead_hi,
         "Most points by one team in one game, full regular season. A tie splits it.")
    if last < WEEKS:            # after Week 18 the window is shut and the
        pend("QB Down",10100,"When triggered","Not triggered",   # money has moved
             "Season-ending IR or ruled out for the year. Entered by hand.")
        pend("The Pink Slip",10100,"When triggered","Not triggered",
             "First head coach fired or mutually parted with. Entered by hand.")
    pend("Bottom of the Barrel",7200,"End of Week 18", lead_bot,
         "Worst regular season record, ties broken on point differential")

    board = {
      "season":season, "throughWeek":last, "isLive":bool(live),
      "liveWeek":live,
      "nextKick":(sched["nextKick"].strftime("%Y-%m-%dT%H:%M:%SZ")
                  if sched and sched.get("nextKick") else None),
      "generated":datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
      "meta":{"pot":POT,"buyIn":BUYIN,"awarded":awarded,"inPlay":in_play,
              "stillToCome":POT-awarded-in_play,
              "auctionSpend":auction["spend_cents"],
              "forfeited":auction["forfeited_cents"],
              "weeklyLeft":weekly_left,"bountyLeft":bounty_left},
      "owners":[{"name":o,"spent":auction["spent_cents"][o],"won":won[o],
                 "teams":sorted([a for a,x in owners.items() if x==o],
                                key=lambda a:-prices[a])} for o in who],
      "cat":cat,
      "teams":[{"name":teams.name(a),"abbr":a,"div":teams.div(a),
                "price":prices[a]*100,"owner":owners[a],
                "c1":teams.c1(a),"c2":teams.c2(a),
                "w":rec[a]["w"],"l":rec[a]["l"],"t":rec[a]["t"],
                "pf":rec[a]["pf"],"pa":rec[a]["pa"],"earned":earned[a]}
               for a in teams.TEAMS],
      "ledger":sorted(ledger, key=lambda l:(l["week"], l["prize"])),
      "pending":pending,
      "msTables":ms_tables,
      "post":post_rounds,
      "postPool":post_pool, "postRolled":rolled + weekly_stranded,
      "postFromNovelty":rolled, "postFromWeekly":weekly_stranded, "postTiers":
        {str(k): v for k, v in tier.items()},
    }
    return board


def load_prev(season):
    """The board as it was last written, for the freeze check and the skip."""
    path = os.path.join(DATA, "board.json")
    if not os.path.exists(path): return None
    try:
        b = json.load(open(path))
        return b if b.get("season") == season else None
    except Exception:
        return None


def quiet(sched, prev):
    """True when nothing can possibly have changed since the last write.

    No week is in progress, and the schedule has not finished a week beyond
    the one the board already covers. Lets the scheduled job run often and
    cheaply without downloading a season of play-by-play every time.
    """
    if prev.get("isLive"): return False
    done = [w for w, st in sched["weeks"].items() if st["complete"]]
    if (max(done) if done else 0) > prev.get("throughWeek", 0): return False
    nxt = sched["weeks"].get(prev.get("throughWeek", 0) + 1)
    if nxt and nxt["started"]: return False
    # The front of the page shows the next kickoff, so a kickoff that has moved
    # or that the stored board never had is reason enough to rebuild. A kickoff
    # only passes when a game starts, and a started game means the week is
    # live, which is already not quiet. So this costs no extra runs.
    kick = (sched["nextKick"].strftime("%Y-%m-%dT%H:%M:%SZ")
            if sched.get("nextKick") else None)
    return kick == prev.get("nextKick")


def main():
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    auction, prices, owners = league.load()
    errs = validate.check_league(sorted(prices), owners, prices)
    if errs:
        print("AUCTION FAILED VALIDATION:"); [print("  !",e) for e in errs]; sys.exit(1)

    force = os.environ.get("CALCUTTA_FORCE") == "1"
    prev = load_prev(season)

    # The schedule comes first, and it is small. It says how many games a week
    # is supposed to have and which are actually over. Without it we cannot tell
    # a halftime lead from a win, so a failure here means nothing new gets paid.
    try:
        # CALCUTTA_NOW lets us replay any moment of any season to check the
        # live-week behaviour without waiting for a Sunday.
        fake = os.environ.get("CALCUTTA_NOW")
        now = (datetime.datetime.fromisoformat(fake).replace(
                   tzinfo=datetime.timezone.utc) if fake else None)
        raw = schedule.fetch(season)
        if now: raw = schedule.rewind(raw, now)
        void = load_void()
        if void: print(f"void     {len(void)} game(s) struck out: {', '.join(void)}")
        sched = schedule.read(raw, now, void)
        print(f"schedule {len(sched['finalIds'])} of "
              f"{sum(s['total'] for s in sched['weeks'].values())} games final")
        if sched["nextKick"]:
            print(f"next kick {sched['nextKick'].astimezone(schedule.ET):%a %b %-d, %-I:%M%p ET}")
    except Exception as e:
        # Without the schedule we cannot tell a finished week from a half
        # played one. Play-by-play alone would let the board settle Week 7 off
        # the one o'clock games and pay Team of the Week to a side that is
        # about to be beaten by a four twenty-five blowout. Stop instead.
        print(f"\nschedule unavailable ({type(e).__name__}: {e}).")
        print("Without it a half-played week cannot be told from a finished one,")
        print("so nothing was written. The board stands as it was. Try again shortly.")
        sys.exit(1)

    # Nothing is live and nothing new has finished since the board was last
    # written, so there is no reason to pull a hundred megabytes of play-by-play.
    if sched and prev and not force and quiet(sched, prev):
        print(f"\nnothing to do. No game is in progress and the board is already "
              f"current through Week {prev['throughWeek']}.")
        return

    try:
        rows, url, missing = fetch_pbp(season, distill.COLS)
        games = distill.distill(rows)
    except Exception as e:
        # Before Week 1 there is no file to fetch. That is Week 0, not an error.
        print(f"no play-by-play for {season} yet ({type(e).__name__}). Building the pre-season board.")
        rows, url, games = [], None, []
    if games and url: print(f"source   {url}\nplays    {len(rows):,}")
    seen = {t for g in games for t in (g["home"], g["away"])}
    unknown = sorted(seen - set(owners))
    if unknown:
        print(f"UNKNOWN TEAM ABBREVIATIONS: {unknown}"); sys.exit(1)
    for g in games:
        g["final"] = (g["game_id"] in sched["finalIds"]) if sched else True

    board = build_board(games, auction, prices, owners, load_manual(owners), season, sched)

    # A week that has been settled must never quietly change. If an upstream
    # correction moves one, stop and say so rather than restating the board
    # under everybody without telling them.
    if prev and prev.get("season") == season and prev.get("ledger"):
        weeks = set(range(1, min(prev["throughWeek"], board["throughWeek"]) + 1))
        ferrs = validate.check_frozen(prev["ledger"], board["ledger"], weeks)
        if ferrs and not force:
            print("\nA SETTLED WEEK CHANGED. Nothing was written.")
            for e in ferrs: print("  !", e)
            print("\nThis usually means a stat correction upstream. Review it, then")
            print("re-run with 'Allow a settled week to change' ticked to accept it.")
            sys.exit(1)
        if ferrs:
            print("\nACCEPTING a change to settled weeks, because it was forced:")
            for e in ferrs: print("  !", e)
    if board["isLive"]:
        lw = board["liveWeek"]
        print(f"LIVE     week {lw['week']}, {lw['gamesFinal']} of {lw['gamesTotal']} final, "
              f"${board['meta']['inPlay']/100:,.2f} in play")

    errs = validate.check_awards(board["ledger"])
    if errs:
        print("AWARD VALIDATION FAILED:"); [print("  !",e) for e in errs]; sys.exit(1)

    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA,"games.json"),"w") as f:
        json.dump({"season":season,"source":url,"games":games}, f, separators=(",",":"))
    with open(os.path.join(DATA,"board.json"),"w") as f:
        json.dump(board, f, separators=(",",":"))

    m = board["meta"]
    L = board["ledger"]
    print(f"\nseason {season}  |  {len(games)} games  |  through week {board['throughWeek']}"
          f"  |  {len(L)} awards")

    # ---- where the money went, by category
    def tot(pred): return sum(l["amount"] for l in L if pred(l))
    weekly = tot(lambda l: l["prize"] in prizes.WEEKLY)
    mini   = tot(lambda l: l["prize"].startswith("Mini-Season"))
    nov    = tot(lambda l: l["prize"] in NOVELTY)
    bounty = sum(c["bounty"] for c in board["cat"].values())
    print("\nWHERE THE POT WENT")
    print(f"  weekly prizes   ${weekly/100:>9,.2f}   {sum(1 for l in L if l['prize'] in prizes.WEEKLY)} awards")
    print(f"  win bounty      ${bounty/100:>9,.2f}   $1 a win")
    print(f"  mini-seasons    ${mini/100:>9,.2f}")
    print(f"  novelty         ${nov/100:>9,.2f}")
    if tot(lambda l: l["prize"] == prizes.POST_PRIZE):
        print(f"  postseason      ${tot(lambda l: l['prize'] == prizes.POST_PRIZE)/100:>9,.2f}")
    print(f"  AWARDED         ${m['awarded']/100:>9,.2f}")
    if m["inPlay"]:
        print(f"  in play now     ${m['inPlay']/100:>9,.2f}   week {board['liveWeek']['week']}, not yet paid")
    print(f"  still to come   ${m['stillToCome']/100:>9,.2f}")
    print(f"  POT             ${m['pot']/100:>9,.2f}")
    post = tot(lambda l: l["prize"] == prizes.POST_PRIZE)
    assert weekly + bounty + mini + nov + post == m["awarded"], "categories must tie"
    assert m["awarded"] + m["inPlay"] + m["stillToCome"] == POT
    # stillToCome is a residual, so it goes negative rather than failing when
    # something is paid twice. Check the pot itself.
    if m["awarded"] + m["inPlay"] > POT:
        print(f"\nOVERPAID. ${(m['awarded']+m['inPlay'])/100:,.2f} committed "
              f"against a ${POT/100:,.2f} pot. Nothing written.")
        sys.exit(1)

    # ---- the prizes people will ask about by name
    named = [l for l in L if l["prize"] not in prizes.WEEKLY]
    if named:
        print("\nTHE BIG ONES")
        for l in sorted(named, key=lambda x: (x["week"], x["prize"])):
            who = ", ".join(f"{x['owner']} ${x['amount']/100:,.2f}" for x in l["winners"])
            print(f"  wk{l['week']:<3}{l['prize']:<28}{who}")
            print(f"      {'':28}{l['winners'][0]['detail']}")

    # ---- how many times each weekly prize actually paid
    print("\nWEEKLY PRIZES, TIMES PAID OUT OF 18")
    for p in prizes.WEEKLY:
        n = sum(1 for l in L if l["prize"] == p)
        amt = tot(lambda l, p=p: l["prize"] == p)
        flag = "" if n == 18 else f"   <- {18-n} week(s) carried"
        print(f"  {p:<24}{n:>3}   ${amt/100:>7,.2f}{flag}")

    if board["isLive"]:
        lw = board["liveWeek"]
        print(f"\nWEEK {lw['week']} LEADING, NOTHING PAID YET")
        for p in lw["prizes"]:
            who = (", ".join(f"{x['abbr']} {x['owner']}" for x in p["leaders"])
                   or ("carries into next week" if p["carry"] else "nothing qualifies yet"))
            print(f"  {p['prize']:<24}${p['amount']/100:>7,.2f}   {who}")
        print(f"  {'win bounty so far':<24}${lw['bounty']/100:>7,.2f}")

    if board["post"]:
        print("\nPOSTSEASON LADDER")
        for r in board["post"]:
            state = ("settled" if r["settled"] else
                     f"{r['gamesFinal']} of {r['gamesTotal']} final")
            print(f"  {r['label']:<14}${r['paid']/100:>8,.2f}   {state}")
        print(f"  {'ladder paid':<14}${sum(r['paid'] for r in board['post'])/100:>8,.2f}"
              f"   of ${board['postPool']/100:,.2f}")
    if board["postRolled"]:
        print(f"\nNOVELTY ROLLED INTO THE POSTSEASON POOL  ${board['postRolled']/100:,.2f}")
        print("  never triggered by the end of Week 18, so it pays on the ladder instead")
        t = board["postTiers"]
        print(f"  champion ${int(t['champion'])/100:,.2f}   runner-up ${int(t['22'])/100:,.2f}"
              f"   conference ${int(t['21'])/100:,.2f}   divisional ${int(t['20'])/100:,.2f}"
              f"   wild card ${int(t['19'])/100:,.2f}")

    print("\nSTILL TO COME")
    for p in board["pending"]:
        print(f"  {p['prize']:<28}${p['amount']/100:>9,.2f}   {p['lead']}")
    if m["weeklyLeft"]: print(f"  {'weekly prizes not yet played':<28}${m['weeklyLeft']/100:>9,.2f}")
    if m["bountyLeft"]: print(f"  {'win bounty not yet played':<28}${m['bountyLeft']/100:>9,.2f}")

    print("\nSTANDINGS")
    for i, o in enumerate(sorted(board["owners"], key=lambda x:-x["won"]), 1):
        c = board["cat"][o["name"]]
        print(f"  {i:>2}. {o['name']:<7} ${o['won']/100:>8,.2f}   "
              f"weekly ${c['weekly']/100:>6,.2f}  bounty ${c['bounty']/100:>6,.2f}  "
              f"mini ${c['mini']/100:>5,.2f}  novelty ${c['novelty']/100:>6,.2f}")

if __name__ == "__main__":
    main()
