"""The rules engine. One authoritative implementation of every prize.

All money is INTEGER CENTS. A split divides to the cent, odd pennies going to
the cheaper team first, so a tie never leaves anyone unpaid.

Every resolver has the same signature (ctx) -> list of awards. Pink Slip and
QB Down read from ctx.manual today; swapping in a detector later replaces one
function and touches nothing else.
"""
from collections import defaultdict

WEEKLY = {"Team of the Week":1100, "Stinker of the Week":800, "Price Check":800,
          "Upset of the Week":500, "Shootout":300, "Most Field Goals":200,
          "Longest TD":100}
BOUNTY_PER_WIN = 100
MINI = {1:(1,6,4900), 2:(7,12,5400), 3:(13,18,6600)}
NOVELTY = {"Highest single-game score":10100, "The Pink Slip":10100,
           "QB Down":10100, "Bottom of the Barrel":7200}

class Ctx:
    def __init__(self, games, owners, prices, manual=None):
        self.games  = games                 # distilled per-game records, final only
        self.owners = owners                # {team_abbr: owner}
        self.prices = prices                # {team_abbr: dollars paid}
        self.manual = manual or []
    def week(self, w):  return [g for g in self.games if g["week"] == w and g["final"]]
    def teams(self, g): return (g["home"], g["away"])
    def pts(self, g, t): return g["home_score"] if t == g["home"] else g["away_score"]
    def winner(self, g):
        if g["home_score"] == g["away_score"]: return None
        return g["home"] if g["home_score"] > g["away_score"] else g["away"]
    def loser(self, g):
        w = self.winner(g)
        return None if w is None else (g["away"] if w == g["home"] else g["home"])

def split(amount, teams, prices):
    """Divide to the cent. Odd pennies to the cheaper team first."""
    teams = sorted(teams, key=lambda t: (prices.get(t, 0), t))
    base, rem = amount // len(teams), amount % len(teams)
    out = [(t, base + (1 if i < rem else 0)) for i, t in enumerate(teams)]
    assert sum(a for _, a in out) == amount
    return out

def award(ctx, week, prize, amount, teams, detail):
    return {"week":week, "prize":prize, "amount":amount,
            "split": len(teams) > 1,
            "winners":[{"team":t, "owner":ctx.owners.get(t), "amount":a,
                        "detail":detail(t) if callable(detail) else detail}
                       for t, a in split(amount, teams, ctx.prices)]}

# ---------------------------------------------------------------- weekly seven
def team_of_the_week(ctx, w, carry=0):
    gs = ctx.week(w)
    if not gs: return None
    best = max(gs, key=lambda g: abs(g["home_score"]-g["away_score"]))
    m = abs(best["home_score"]-best["away_score"])
    if m == 0: return None
    wt, lt = ctx.winner(best), ctx.loser(best)
    tied = [g for g in gs if abs(g["home_score"]-g["away_score"]) == m]
    teams = [ctx.winner(g) for g in tied]
    return award(ctx, w, "Team of the Week", 1100+carry, teams,
                 lambda t: f"Beat {[ctx.loser(g) for g in tied if ctx.winner(g)==t][0]} by {m}")

def stinker(ctx, w, carry=0):
    losers = [(ctx.loser(g), ctx.pts(g, ctx.loser(g)), ctx.winner(g))
              for g in ctx.week(w) if ctx.winner(g)]     # a tie game has no loser
    if not losers: return None
    lo = min(p for _, p, _ in losers)
    teams = [t for t, p, _ in losers if p == lo]
    opp = {t: o for t, p, o in losers if p == lo}
    return award(ctx, w, "Stinker of the Week", 800+carry, teams,
                 lambda t: f"{lo} point{'' if lo==1 else 's'} in a loss to {opp[t]}")

def price_check(ctx, w, carry=0):
    gaps = []
    for g in ctx.week(w):
        wt = ctx.winner(g)
        if not wt: continue
        lt = ctx.loser(g)
        if ctx.prices.get(wt,0) < ctx.prices.get(lt,0):
            gaps.append((ctx.prices[lt]-ctx.prices[wt], wt, lt))
    if not gaps: return None                              # carries to next week
    top = max(x[0] for x in gaps)
    win = [x for x in gaps if x[0] == top]
    d = {x[1]: f"${ctx.prices[x[1]]} {x[1]} beat ${ctx.prices[x[2]]} {x[2]}, a ${x[0]} gap" for x in win}
    return award(ctx, w, "Price Check", 800+carry, [x[1] for x in win], lambda t: d[t])

def upset(ctx, w, carry=0, pre=None):
    if w == 1 or not pre: return None                     # everyone is 0-0
    ups = []
    for g in ctx.week(w):
        wt = ctx.winner(g)
        if not wt: continue
        lt = ctx.loser(g)
        if pre.get(wt,0) < pre.get(lt,0):
            ups.append((round(pre[lt]-pre[wt],6), wt, lt))
    if not ups: return None
    top = max(x[0] for x in ups)
    win = [x for x in ups if x[0] == top]
    f = lambda v: f"{v:.3f}".lstrip("0")
    d = {x[1]: f"{x[1]} ({f(pre[x[1]])}) beat {x[2]} ({f(pre[x[2]])})" for x in win}
    return award(ctx, w, "Upset of the Week", 500+carry, [x[1] for x in win], lambda t: d[t])

def shootout(ctx, w, carry=0):
    gs = ctx.week(w)
    if not gs: return None
    hi = max(g["home_score"]+g["away_score"] for g in gs)
    teams, d = [], {}
    for g in gs:
        if g["home_score"]+g["away_score"] != hi: continue
        for t, o in ((g["home"],g["away"]), (g["away"],g["home"])):
            teams.append(t); d[t] = f"{hi} combined vs {o}"
    return award(ctx, w, "Shootout", 300+carry, teams, lambda t: d[t])

def most_fgs(ctx, w, carry=0):
    fg = [(g["fg"][t], g["fg_yards"][t], t) for g in ctx.week(w) for t in ctx.teams(g)]
    fg = [x for x in fg if x[0] > 0]
    if not fg: return None
    mx = max(x[0] for x in fg)
    tied = [x for x in fg if x[0] == mx]
    if len(tied) > 1:                                     # tiebreak: total FG yardage
        best_y = max(x[1] for x in tied)
        tied = [x for x in tied if x[1] == best_y]
    d = {x[2]: f"{mx} field goals made" + (f", {x[1]} yards" if len(tied)>1 else "") for x in tied}
    return award(ctx, w, "Most Field Goals", 200+carry, [x[2] for x in tied], lambda t: d[t])

def longest_td(ctx, w, carry=0):
    td = [(g["long_td"][t], t) for g in ctx.week(w) for t in ctx.teams(g) if g["long_td"][t] > 0]
    if not td: return None
    my = max(x[0] for x in td)
    teams = [t for y, t in td if y == my]
    return award(ctx, w, "Longest TD", 100+carry, teams, f"{my}-yard touchdown")

# ---------------------------------------------------------------- a whole week
def run_week(ctx, w, carries, pre):
    out, new = [], dict(carries)
    plan = [("Team of the Week", team_of_the_week), ("Stinker of the Week", stinker),
            ("Price Check", price_check), ("Upset of the Week", upset),
            ("Shootout", shootout), ("Most Field Goals", most_fgs),
            ("Longest TD", longest_td)]
    for name, fn in plan:
        c = carries.get(name, 0)
        a = fn(ctx, w, c, pre) if name == "Upset of the Week" else fn(ctx, w, c)
        if a is None:
            # only Price Check and Upset roll over, and only into themselves
            new[name] = (WEEKLY[name] + c) if name in ("Price Check","Upset of the Week") else c
        else:
            new[name] = 0
            out.append(a)
    return out, new
