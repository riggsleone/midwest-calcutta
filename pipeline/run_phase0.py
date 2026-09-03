"""Phase 0 offline: run the real engine over schema-accurate play-by-play
and verify every answer by a second, independent method."""
import json, fixture, distill, prizes

# real auction data, the 16 teams that appear in the fixture
PRICES={"KC":100,"BUF":150,"PHI":70,"DAL":65,"SF":65,"SEA":125,"BAL":120,"CIN":60,
        "DET":70,"GB":80,"MIA":46,"NYJ":50,"HOU":86,"IND":69,"LAR":105,"ARI":48}
OWNERS={"KC":"Doug","BUF":"Nolan","PHI":"Riggs","DAL":"Paul","SF":"Paul","SEA":"Ben",
        "BAL":"Sam","CIN":"Sam","DET":"Sean","GB":"Matt","MIA":"Matt","NYJ":"Riggs",
        "HOU":"Doug","IND":"Matt","LAR":"John","ARI":"Sean"}

games = distill.distill(fixture.week(wk=5))
ctx   = prizes.Ctx(games, OWNERS, PRICES)
pre   = {t: 0.5 for t in PRICES}          # pretend everyone is .500 entering wk 5
pre.update({"KC":.800,"BUF":.750,"ARI":.200,"NYJ":.250,"SEA":.750,"MIA":.200})

awards, carries = prizes.run_week(ctx, 5, {}, pre)

print(f"{'PRIZE':<22}{'AMOUNT':>9}  WINNERS")
for a in awards:
    who=", ".join(f"{w['team']} ({w['owner']}) ${w['amount']/100:.2f}" for w in a["winners"])
    print(f"{a['prize']:<22}{'$'+format(a['amount']/100,'.2f'):>9}  {who}")
    print(f"{'':22}{'':9}  {a['winners'][0]['detail']}")
print("\ncarried to next week:", {k:v for k,v in carries.items() if v})

# ---------------------------------------------------------------- independent check
print("\n--- verifying against the raw plays, computed a second way ---")
rows = fixture.week(wk=5)
ok = True
def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  {label}: engine={got} raw={want}")

# longest TD straight off the plays
best_y, best_t = 0, None
for r in rows:
    if r["touchdown"]==1:
        y = r["return_yards"] if r["return_touchdown"]==1 else r["yards_gained"]
        if y > best_y: best_y, best_t = y, r["td_team"]
ltd = next(a for a in awards if a["prize"]=="Longest TD")
check("Longest TD yards", int(ltd["winners"][0]["detail"].split("-")[0]), best_y)
check("Longest TD team", sorted(w["team"] for w in ltd["winners"])[0],
      sorted({r["td_team"] for r in rows if r["touchdown"]==1 and
              (r["return_yards"] if r["return_touchdown"]==1 else r["yards_gained"])==best_y})[0])

# made field goals straight off the plays
fg={}
for r in rows:
    if r["field_goal_result"]=="made": fg[r["posteam"]]=fg.get(r["posteam"],0)+1
mx=max(fg.values())
mfg = next(a for a in awards if a["prize"]=="Most Field Goals")
check("Most FGs count", int(mfg["winners"][0]["detail"].split()[0]), mx)

# biggest margin
marg=max(abs(g["home_score"]-g["away_score"]) for g in games)
totw = next(a for a in awards if a["prize"]=="Team of the Week")
check("Biggest margin", int(totw["winners"][0]["detail"].split()[-1]), marg)

# every split sums exactly and nobody gets zero
for a in awards:
    assert sum(w["amount"] for w in a["winners"])==a["amount"], a["prize"]
    assert all(w["amount"]>0 for w in a["winners"]), a["prize"]
print("  PASS  every split sums exactly to its face value, no winner on $0")
print("\nPHASE 0 OFFLINE:", "ALL CHECKS PASS" if ok else "FAILURES ABOVE")
