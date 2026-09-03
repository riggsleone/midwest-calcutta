"""Reads the league's own data. Today that is the frozen auction committed
alongside the code. Manual entries plug in here later without changing
anything downstream."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
AUCTION = os.path.join(HERE, "..", "data", "auction_2026.json")

def load(path=AUCTION):
    with open(path) as f: d = json.load(f)
    prices = {t["abbr"]: t["price_cents"]//100 for t in d["teams"]}
    owners = {t["abbr"]: t["owner"] for t in d["teams"]}
    return d, prices, owners
