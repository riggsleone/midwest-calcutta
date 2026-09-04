"""Turn a season of play-by-play into board.json, the one file the page reads.

    python build.py 2026     # the live season
    python build.py 2025     # a completed season, to prove the whole run

Inputs are stored, outputs are recomputed. Every prize is derived from the
games every time, so fixing a rule fixes the whole season at once.
"""
import sys, json, os, datetime
import distill, prizes, validate, league, teams
from fetch import fetch_pbp

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
POT, BUYIN, WEEKS = 250000, 25000, 18
NOVELTY = {"Highest single-game score":10100, "The Pink Slip":10100,
           "QB Down":10100, "Bottom of the Barrel":7200}
MINI = {1:(1,6,4900), 2:(7,12,5400), 3:(13,18,6600)}
p3 = lambda v: f"{v:.3f}".lstrip("0")


def load_manual():
    path = os.path.join(DATA, "manual.json")
    if not os.path.exists(path): return []
    with open(path) as f: return json.load(f).get("entries", [])


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
    """Combined win percentage across every team an owner holds."""
    who = sorted(set(owners.values()))
    rec = {o: {"w":0,"l":0} for o in who}
    for g in games:
        if not (lo <= g["week"] <= hi): continue
        if g["home_score"] == g["away_score"]: continue
        w = g["home"] if g["home_score"] > g["away_score"] else g["away"]
        l = g["away"] if g["home_score"] > g["away_score"] else g["home"]
        if owners.get(w): rec[owners[w]]["w"] += 1
        if owners.get(l): rec[owners[l]]["l"] += 1
    pct = {o: rec[o]["w"]/max(1, rec[o]["w"]+rec[o]["l"]) for o in who}
    table = [{"owner":o, "w":rec[o]["w"], "l":rec[o]["l"],
              "g":rec[o]["w"]+rec[o]["l"], "pct":round(pct[o],4),
              "teams":sum(1 for t,x in owners.items() if x==o)}
             for o in sorted(who, key=lambda x:-pct[x])]
    return pct, table, rec


def split_owner(amount, who):
    """Owner-level split, to the cent, alphabetical for the odd pennies."""
    who = sorted(who)
    base, rem = amount//len(who), amount % len(who)
    return [(o, base + (1 if i < rem else 0)) for i, o in enumerate(who)]


def build_board(games, auction, prices, owners, manual, season):
    played = sorted({g["week"] for g in games})
    last = max(played) if played else 0
    ledger, carries = [], {}

    # ---- the seven weekly prizes, week by week, carries flowing forward
    for w in range(1, last+1):
        if not any(g["week"] == w for g in games): continue
        pre = {}
        r = records(games, w-1)
        for t, x in r.items():
            n = x["w"] + x["l"] + x["t"]
            if n: pre[t] = (x["w"] + 0.5*x["t"]) / n
        ctx = prizes.Ctx(games, owners, prices)
        awards, carries = prizes.run_week(ctx, w, carries, pre)
        ledger += awards

    # ---- win bounty, $1 a win, credited per team
    rec = records(games, last)
    bounty = {a: rec[a]["w"]*100 + int(rec[a]["t"]*50) for a in teams.TEAMS}

    # ---- mini-seasons, settled only once their window has completed
    ms_table = None
    for n, (lo, hi, amt) in MINI.items():
        if last < hi: continue
        pct, table, mrec = mini_season(games, owners, lo, hi)
        if n == 1: ms_table = table
        best = max(pct.values())
        win = [o for o in pct if pct[o] == best]
        ledger.append({"week":hi, "prize":f"Mini-Season {n}", "amount":amt,
            "split":len(win)>1,
            "detail":f"Weeks {lo} to {hi}, best combined win percentage, {p3(best)}",
            "winners":[{"team":None,"abbr":None,"owner":o,"amount":a,
                        "detail":f"{mrec[o]['w']}-{mrec[o]['l']} across their teams, "
                                 f"{p3(pct[o])} win percentage"}
                       for o, a in split_owner(amt, win)]})

    # ---- novelty settled at the end of the regular season
    if last >= WEEKS:
        hi_g = max(games, key=lambda g: max(g["home_score"], g["away_score"]))
        ht = hi_g["home"] if hi_g["home_score"] >= hi_g["away_score"] else hi_g["away"]
        pts = max(hi_g["home_score"], hi_g["away_score"])
        ledger.append({"week":WEEKS, "prize":"Highest single-game score",
            "amount":NOVELTY["Highest single-game score"], "split":False,
            "detail":f"{pts} points, Week {hi_g['week']}",
            "winners":[{"team":teams.name(ht),"abbr":ht,"owner":owners.get(ht),
                        "amount":NOVELTY["Highest single-game score"],
                        "detail":f"{pts} points in Week {hi_g['week']}"}]})
        bot = min(teams.TEAMS, key=lambda a:(rec[a]["w"], rec[a]["pf"]-rec[a]["pa"]))
        ledger.append({"week":WEEKS, "prize":"Bottom of the Barrel",
            "amount":NOVELTY["Bottom of the Barrel"], "split":False,
            "detail":f"{rec[bot]['w']}-{rec[bot]['l']}, worst record",
            "winners":[{"team":teams.name(bot),"abbr":bot,"owner":owners.get(bot),
                        "amount":NOVELTY["Bottom of the Barrel"],
                        "detail":f"{rec[bot]['w']}-{rec[bot]['l']}, "
                                 f"{rec[bot]['pf']-rec[bot]['pa']:+d} differential"}]})

    # ---- manual entries: Pink Slip, QB Down, corrections
    for m in manual:
        if m.get("status") == "proposed": continue      # not confirmed yet
        if m["type"] in ("The Pink Slip", "QB Down"):
            t = m["team"]
            ledger.append({"week":m.get("week", last), "prize":m["type"],
                "amount":NOVELTY[m["type"]], "split":False,
                "detail":m.get("detail",""), "manual":True,
                "winners":[{"team":teams.name(t),"abbr":t,"owner":owners.get(t),
                            "amount":NOVELTY[m["type"]],
                            "detail":m.get("detail","")}]})

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
                 "mini" if l["prize"].startswith("Mini-Season") else "novelty")
            cat[x["owner"]][k] += x["amount"]
            if x["abbr"]: earned[x["abbr"]] += x["amount"]
    for a, v in bounty.items():
        if owners.get(a): cat[owners[a]]["bounty"] += v

    won = {o: sum(cat[o].values()) for o in who}
    awarded = sum(won.values())
    weekly_left = max(0, (WEEKS - last)) * 3800
    bounty_left = max(0, 27200 - sum(bounty.values()))

    # ---- what is still to come, with live leaders where they exist
    hi_g = max(games, key=lambda g: max(g["home_score"], g["away_score"])) if games else None
    bot = min(teams.TEAMS, key=lambda a:(rec[a]["w"], rec[a]["pf"]-rec[a]["pa"])) if games else None
    ht2 = None
    if hi_g:
        ht2 = hi_g["home"] if hi_g["home_score"] >= hi_g["away_score"] else hi_g["away"]
    done_prizes = {l["prize"] for l in ledger}
    pending = []
    def pend(p, amt, when, lead, note):
        if p not in done_prizes: pending.append(
            {"prize":p,"amount":amt,"when":when,"lead":lead,"note":note})
    pend("Postseason ladder",100000,"After the Super Bowl","Not started",
         "14 teams pay, from $250 for the champion down to $25 for a wild card loss")
    for n,(lo,hi,amt) in MINI.items():
        if f"Mini-Season {n}" in done_prizes: continue
        if last >= lo:
            pct,_,mr = mini_season(games, owners, lo, min(last,hi))
            b = max(pct.values()); ldr=[o for o in pct if pct[o]==b]
            lead = (" and ".join(ldr) + f" {p3(b)}, {mr[ldr[0]]['w']}-{mr[ldr[0]]['l']}"
                    f" over Weeks {lo} to {min(last,hi)}")
        else:
            lead = "Not started"
        pend(f"Mini-Season {n}", amt, f"After Week {hi}", lead,
             f"Weeks {lo} to {hi}, best combined win percentage")
    pend("Highest single-game score",10100,"End of Week 18",
         (f"{ht2} {max(hi_g['home_score'],hi_g['away_score'])}, Week {hi_g['week']} "
          f"({owners.get(ht2)})" if ht2 else "Not started"),
         "Most points by one team in one game, full regular season")
    pend("QB Down",10100,"When triggered","Not triggered",
         "Season-ending IR or ruled out for the year. Entered by hand.")
    pend("The Pink Slip",10100,"When triggered","Not triggered",
         "First head coach fired or mutually parted with. Entered by hand.")
    pend("Bottom of the Barrel",7200,"End of Week 18",
         (f"{bot} {rec[bot]['w']}-{rec[bot]['l']} ({owners.get(bot)})" if games else "Not started"),
         "Worst regular season record, ties broken on point differential")

    in_play = 0     # set by the caller when a week is live
    board = {
      "season":season, "throughWeek":last, "isLive":False,
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
      "msTable":ms_table,
    }
    return board


def main():
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    auction, prices, owners = league.load()
    errs = validate.check_league(sorted(prices), owners, prices)
    if errs:
        print("AUCTION FAILED VALIDATION:"); [print("  !",e) for e in errs]; sys.exit(1)

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

    board = build_board(games, auction, prices, owners, load_manual(), season)

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
    print(f"  AWARDED         ${m['awarded']/100:>9,.2f}")
    print(f"  still to come   ${m['stillToCome']/100:>9,.2f}")
    print(f"  POT             ${m['pot']/100:>9,.2f}")
    assert weekly + bounty + mini + nov == m["awarded"], "categories must tie"
    assert m["awarded"] + m["inPlay"] + m["stillToCome"] == POT

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
