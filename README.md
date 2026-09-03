# 2026 Midwest+ Calcutta

The league dashboard and the job that keeps it current.

## What is here right now

Phase 0 only: proving that every prize can be decided from real NFL data
before anything is built on top of it.

    pipeline/distill.py   raw play-by-play  ->  the facts we keep per game
    pipeline/prizes.py    the rules engine, one implementation of every prize
    pipeline/fetch.py     downloads the season's play-by-play
    pipeline/validate.py  checks that must pass before anything publishes
    pipeline/phase0.py    the Phase 0 run
    pipeline/league.py    reads the committed auction results
    pipeline/fixture.py   a fake week, so the engine can be tested offline
    data/auction_2026.json   the auction, frozen on 2 September 2026

## To run Phase 0

Go to the **Actions** tab, pick **Phase 0 - prove the data**, press
**Run workflow**, leave the season and week as they are, press the green
button. It takes about a minute. Open the finished run to read the report.

A good result decides all seven weekly prizes and says AUTOMATED for both
Longest TD and Most Field Goals.

## Money

Every amount in the code is in whole cents. A split prize divides to the
cent, with any odd pennies going to the cheaper team first, so a tie never
leaves an owner unpaid.

## Data source

Play-by-play comes from nflverse, which publishes free public files and
updates within about fifteen minutes of a game ending. NFL.com stays the
stated source of record in the league rules and settles any dispute.
