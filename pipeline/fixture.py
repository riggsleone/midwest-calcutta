"""A synthetic week of play-by-play in nflverse's real schema.

This exists so the engine can be proved before the pipeline has ever
downloaded anything. Same column names, same value conventions, including
the awkward ones: return TDs measured by return_yards, field goals credited
to posteam, running scores repeated on every play.
"""
import random

def week(season=2025, wk=5, pairs=None, seed=7):
    rnd = random.Random(seed)
    pairs = pairs or [("KC","BUF"),("PHI","DAL"),("SF","SEA"),("BAL","CIN"),
                      ("DET","GB"),("MIA","NYJ"),("HOU","IND"),("LAR","ARI")]
    rows=[]
    for hi,(home,away) in enumerate(pairs):
        gid=f"{season}_{wk:02d}_{away}_{home}"
        hs=as_=0
        script=[]
        for team in (home,away):
            for _ in range(rnd.randint(1,4)):
                script.append((team,"td",rnd.choice([1,3,8,14,22,35,48,63,77,91])))
            for _ in range(rnd.randint(0,3)):
                script.append((team,"fg",rnd.choice([21,28,33,39,44,50,55])))
        rnd.shuffle(script)
        for team,kind,val in script:
            opp = away if team==home else home
            ret = kind=="td" and rnd.random()<0.12       # a return TD now and then
            if kind=="td":
                if team==home: hs+=7
                else: as_+=7
            else:
                if team==home: hs+=3
                else: as_+=3
            rows.append({
              "game_id":gid,"season":season,"week":wk,"season_type":"REG",
              "home_team":home,"away_team":away,
              "posteam": (opp if ret else team), "defteam": (team if ret else opp),
              "td_team": team if kind=="td" else "",
              "touchdown": 1 if kind=="td" else 0,
              "return_touchdown": 1 if ret else 0,
              "yards_gained": 0 if ret else (val if kind=="td" else 0),
              "return_yards": val if ret else 0,
              "field_goal_result": "made" if kind=="fg" else "",
              "kick_distance": val if kind=="fg" else 0,
              "home_score":hs,"away_score":as_})
        # a couple of missed field goals, which must NOT count
        rows.append({"game_id":gid,"season":season,"week":wk,"season_type":"REG",
          "home_team":home,"away_team":away,"posteam":home,"defteam":away,
          "td_team":"","touchdown":0,"return_touchdown":0,"yards_gained":0,
          "return_yards":0,"field_goal_result":"missed","kick_distance":52,
          "home_score":hs,"away_score":as_})
    return rows
