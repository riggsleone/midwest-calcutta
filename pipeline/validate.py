"""Checks that must pass before anything is published. A failure stops the
run rather than writing a wrong page over a right one."""

def check_league(teams, owners, prices, expect_spend=2336, expect_owners=10):
    errs=[]
    if len(teams) != 32: errs.append(f"expected 32 teams, got {len(teams)}")
    unknown = [t for t in teams if t not in owners]
    if unknown: errs.append(f"teams with no owner: {unknown}")
    o = sorted(set(owners.values()))
    if len(o) != expect_owners: errs.append(f"expected {expect_owners} owners, got {len(o)}: {o}")
    spend = sum(prices.get(t,0) for t in teams)
    if spend != expect_spend: errs.append(f"auction spend is ${spend}, expected ${expect_spend}")
    return errs

def check_awards(awards):
    errs=[]
    for a in awards:
        tot = sum(w["amount"] for w in a["winners"])
        if tot != a["amount"]:
            errs.append(f"{a['prize']} wk{a['week']}: winners sum {tot} != {a['amount']}")
        for w in a["winners"]:
            if w["amount"] <= 0:
                errs.append(f"{a['prize']} wk{a['week']}: {w['team']} paid {w['amount']}")
            if not w["owner"]:
                errs.append(f"{a['prize']} wk{a['week']}: {w['team']} has no owner")
    return errs

def check_frozen(previous, current, settled_weeks):
    """A week that was already settled must never change. If it does, stop."""
    errs=[]
    key = lambda a: (a["week"], a["prize"])
    prev = {key(a): a for a in previous if a["week"] in settled_weeks}
    cur  = {key(a): a for a in current  if a["week"] in settled_weeks}
    for k, p in prev.items():
        c = cur.get(k)
        if c is None:
            errs.append(f"settled award vanished: week {k[0]} {k[1]}")
        elif [(w['team'],w['amount']) for w in p['winners']] != \
             [(w['team'],w['amount']) for w in c['winners']]:
            errs.append(f"settled award CHANGED: week {k[0]} {k[1]}")
    return errs
