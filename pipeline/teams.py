"""Reference data. Never changes, so it lives in the code rather than in
anything Riggs has to maintain. Abbreviations here are the canonical ones;
distill.ALIAS maps upstream variants onto them."""

# abbr: (full name, division, primary, secondary)
TEAMS = {
 "BUF":("Buffalo Bills","AFC East","#00338D","#C60C30"),
 "MIA":("Miami Dolphins","AFC East","#008E97","#FC4C02"),
 "NE": ("New England Patriots","AFC East","#002244","#C60C30"),
 "NYJ":("New York Jets","AFC East","#125740","#FFFFFF"),
 "BAL":("Baltimore Ravens","AFC North","#241773","#9E7C0C"),
 "CIN":("Cincinnati Bengals","AFC North","#FB4F14","#000000"),
 "CLE":("Cleveland Browns","AFC North","#311D00","#FF3C00"),
 "PIT":("Pittsburgh Steelers","AFC North","#101820","#FFB612"),
 "HOU":("Houston Texans","AFC South","#03202F","#A71930"),
 "IND":("Indianapolis Colts","AFC South","#002C5F","#A5ACAF"),
 "JAX":("Jacksonville Jaguars","AFC South","#006778","#D7A22A"),
 "TEN":("Tennessee Titans","AFC South","#0C2340","#4B92DB"),
 "DEN":("Denver Broncos","AFC West","#FB4F14","#002244"),
 "KC": ("Kansas City Chiefs","AFC West","#E31837","#FFB81C"),
 "LV": ("Las Vegas Raiders","AFC West","#000000","#A5ACAF"),
 "LAC":("Los Angeles Chargers","AFC West","#0080C6","#FFC20E"),
 "DAL":("Dallas Cowboys","NFC East","#003594","#869397"),
 "NYG":("New York Giants","NFC East","#0B2265","#A71930"),
 "PHI":("Philadelphia Eagles","NFC East","#004C54","#A5ACAF"),
 "WAS":("Washington Commanders","NFC East","#5A1414","#FFB612"),
 "CHI":("Chicago Bears","NFC North","#0B162A","#C83803"),
 "DET":("Detroit Lions","NFC North","#0076B6","#B0B7BC"),
 "GB": ("Green Bay Packers","NFC North","#203731","#FFB612"),
 "MIN":("Minnesota Vikings","NFC North","#4F2683","#FFC62F"),
 "ATL":("Atlanta Falcons","NFC South","#A71930","#000000"),
 "CAR":("Carolina Panthers","NFC South","#0085CA","#101820"),
 "NO": ("New Orleans Saints","NFC South","#D3BC8D","#101820"),
 "TB": ("Tampa Bay Buccaneers","NFC South","#D50A0A","#34302B"),
 "ARI":("Arizona Cardinals","NFC West","#97233F","#FFFFFF"),
 "LAR":("Los Angeles Rams","NFC West","#003594","#FFA300"),
 "SF": ("San Francisco 49ers","NFC West","#AA0000","#B3995D"),
 "SEA":("Seattle Seahawks","NFC West","#002244","#69BE28"),
}
assert len(TEAMS) == 32
name = lambda a: TEAMS[a][0]
div  = lambda a: TEAMS[a][1]
c1   = lambda a: TEAMS[a][2]
c2   = lambda a: TEAMS[a][3]
