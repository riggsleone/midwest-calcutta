"""PHASE 0. Pull one completed week of real NFL data and try to decide every
automatable prize from it. Prints a go or no-go line per prize.

Run:  python phase0.py 2025 5
"""
import sys, json, distill, prizes, validate, league
from fetch import fetch_pbp

SEASON = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
WEEK   = int(sys.argv[2]) if len(sys.argv) > 2 else 5

_auction, PRICES, OWNERS = league.load()

print(f"PHASE 0  |  {SEASON} Week {WEEK}\n" + "="*64)

rows, url, missing = fetch_pbp(SEASON, distill.COLS)
print(f"source   {url}")
print(f"plays    {len(rows):,} rows pulled")
if missing:
    print(f"WARNING  columns not found upstream: {missing}")

games = distill.distill(rows)
season_games = len(games)
wk = [g for g in games if g["week"] == WEEK]
print(f"games    {season_games} in the season, {len(wk)} in week {WEEK}\n")

if not wk:
    print("NO GAMES for that week. Try another."); sys.exit(1)

# records entering the week, needed by Upset of the Week
pre = {}
rec = {}
for g in games:
    if g["week"] >= WEEK: continue
    for t, s, o in ((g["home"],g["home_score"],g["away_score"]),
                    (g["away"],g["away_score"],g["home_score"])):
        r = rec.setdefault(t, [0,0])
        if s > o: r[0]+=1
        elif s < o: r[1]+=1
for t,(w,l) in rec.items(): pre[t] = w/max(1,w+l)

ctx = prizes.Ctx(games, OWNERS, PRICES)
awards, carries = prizes.run_week(ctx, WEEK, {}, pre)
got = {a["prize"] for a in awards}

print(f"{'PRIZE':<22}{'RESULT':<10}WINNER AND WHY")
print("-"*78)
for name in prizes.WEEKLY:
    a = next((x for x in awards if x["prize"] == name), None)
    if a is None:
        print(f"{name:<22}{'carried':<10}no winner this week, money rolls forward")
        continue
    n = len(a["winners"])
    head = f"${a['amount']/100:.2f}" + (f"  shared {n} ways" if n > 1 else "")
    print(f"{name:<22}{'OK':<10}{head}")
    for x in a["winners"]:                       # every winner, and why
        print(f"{'':32}{x['team']:<4} {x['owner']:<7} ${x['amount']/100:>6.2f}  {x['detail']}")

errs = validate.check_awards(awards) + validate.check_league(
    sorted(PRICES), OWNERS, PRICES)
print("\n" + "-"*78)
print("VALIDATION:", "all checks pass" if not errs else "FAILURES")
for e in errs: print("  !", e)

auto = len(got)
paid = sum(a["amount"] for a in awards)
print(f"\nWeek {WEEK} paid ${paid/100:.2f} across {sum(len(a['winners']) for a in awards)} winning teams.")
print(f"RESULT: {auto} of 7 weekly prizes decided from real data.")
print("Longest TD:", "AUTOMATED" if "Longest TD" in got else "FAILED")
print("Most Field Goals:", "AUTOMATED" if "Most Field Goals" in got else "FAILED")
json.dump({"season":SEASON,"week":WEEK,"source":url,"games":len(wk),
           "awards":awards,"errors":errs},
          open(f"phase0_{SEASON}_wk{WEEK}.json","w"), indent=1)
print(f"\nwrote phase0_{SEASON}_wk{WEEK}.json")
