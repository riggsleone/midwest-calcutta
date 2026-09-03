"""Download nflverse play-by-play. Standard library only, no pip install,
so the scheduled job has no dependencies to break."""
import csv, gzip, io, urllib.request, sys

BASE = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}"
CANDIDATES = ["{b}.csv.gz", "{b}.csv"]

def fetch_pbp(season, cols, timeout=180):
    """Stream the season's play-by-play, keeping only the columns we need."""
    last = None
    for pat in CANDIDATES:
        url = pat.format(b=BASE.format(season=season))
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"calcutta-pipeline"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            if url.endswith(".gz"):
                raw = gzip.decompress(raw)
            text = io.StringIO(raw.decode("utf-8", "replace"))
            rd = csv.DictReader(text)
            keep = [c for c in cols if c in (rd.fieldnames or [])]
            missing = [c for c in cols if c not in (rd.fieldnames or [])]
            rows = [{c: row.get(c, "") for c in keep} for row in rd]
            return rows, url, missing
        except Exception as e:
            last = f"{url} -> {type(e).__name__}: {e}"
    raise RuntimeError(f"could not fetch play-by-play for {season}. last attempt: {last}")
