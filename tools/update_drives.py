"""Finds the most dramatic late drives of the current NFL season and writes drives_auto.json.

Runs nightly from .github/workflows/drives.yml. Data: nflverse-data GitHub releases.
Usage: python tools/update_drives.py [--season 2026] [--data DIR] [--out drives_auto.json]
"""
import argparse, datetime, json, os, urllib.request
import pandas as pd

REL = "https://github.com/nflverse/nflverse-data/releases/download/"
NICK = dict(ARI="Cardinals", ATL="Falcons", BAL="Ravens", BUF="Bills", CAR="Panthers", CHI="Bears", CIN="Bengals", CLE="Browns",
            DAL="Cowboys", DEN="Broncos", DET="Lions", GB="Packers", HOU="Texans", IND="Colts", JAX="Jaguars", KC="Chiefs",
            LA="Rams", LAC="Chargers", LV="Raiders", MIA="Dolphins", MIN="Vikings", NE="Patriots", NO="Saints", NYG="Giants",
            NYJ="Jets", PHI="Eagles", PIT="Steelers", SEA="Seahawks", SF="49ers", TB="Buccaneers", TEN="Titans", WAS="Commanders")
AFC = {"BAL", "BUF", "CIN", "CLE", "DEN", "HOU", "IND", "JAX", "KC", "LAC", "LV", "MIA", "NE", "NYJ", "PIT", "TEN"}
SKILL = ("QB", "RB", "X", "Z", "SL", "TE")
OFFK = ["QB", "RB", "X", "Z", "SL", "TE", "LT", "LG", "C", "RG", "RT"]
DEFK = ["DE1", "DT1", "DT2", "DE2", "LB1", "LB2", "LB3", "CB1", "CB2", "S1", "S2"]
DPOS = {"LDE": "DE", "RDE": "DE", "LDT": "DT", "RDT": "DT", "NT": "DT", "WLB": "LB", "SLB": "LB", "MLB": "LB", "LILB": "LB",
        "RILB": "LB", "LOLB": "LB", "ROLB": "LB", "LCB": "CB", "RCB": "CB", "NB": "CB", "SS": "S", "FS": "S"}


def fetch(data, path):
    dest = os.path.join(data, os.path.basename(path))
    if not os.path.exists(dest):
        print("download", path)
        urllib.request.urlretrieve(REL + path, dest)
    return dest


def roman(n):
    out = ""
    for v, s in [(50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]:
        while n >= v:
            out += s; n -= v
    return out


def title(season, st, wk, team):
    if st == "REG":
        return f"{season} · Week {int(wk)}"
    conf = "AFC" if team in AFC else "NFC"
    return {19: f"{conf} Wild Card", 20: f"{conf} Divisional", 21: f"{conf} Championship"}.get(int(wk), f"Super Bowl {roman(season - 1965)}")


def clock(s):
    s = max(0, int(s)); return f"{s // 60}:{s % 60:02d}"


def pctl(series, higher_better=True):
    r = series.rank(pct=True)
    return r if higher_better else 1 - r + 1 / len(series)


def main():
    ap = argparse.ArgumentParser()
    today = datetime.date.today()
    ap.add_argument("--season", type=int, default=today.year if today.month >= 8 else today.year - 1)
    ap.add_argument("--data", default="/tmp/nfldata")
    ap.add_argument("--out", default="drives_auto.json")
    ap.add_argument("--keep", type=int, default=40)
    a = ap.parse_args()
    os.makedirs(a.data, exist_ok=True)
    S = a.season
    pbp = pd.read_csv(fetch(a.data, f"pbp/play_by_play_{S}.csv.gz"), low_memory=False)
    rw = pd.read_csv(fetch(a.data, f"weekly_rosters/roster_weekly_{S}.csv"), low_memory=False,
                     usecols=["gsis_id", "jersey_number", "full_name", "team", "week"])
    dc = pd.read_csv(fetch(a.data, f"depth_charts/depth_charts_{S}.csv"), low_memory=False,
                     usecols=["dt", "team", "player_name", "gsis_id", "pos_grp", "pos_abb", "pos_rank"])
    rw = rw.sort_values("week")
    num = {r.gsis_id: int(r.jersey_number) for r in rw.itertuples() if pd.notna(r.jersey_number)}
    fullname = {r.gsis_id: r.full_name for r in rw.itertuples() if pd.notna(r.full_name)}
    pbp = pbp[pbp.play_type.notna()]

    # ---- player and team ratings from this season's numbers ----
    rat = {}
    qb = pbp[pbp.qb_dropback == 1].groupby("passer_player_id").qb_epa.agg(["mean", "size"])
    qb = qb[qb["size"] >= 60]
    for pid, p in pctl(qb["mean"]).items(): rat[pid] = round(70 + 26 * p)
    rec = pbp[pbp.receiver_player_id.notna()].groupby("receiver_player_id").agg(y=("receiving_yards", "sum"), n=("play_id", "size"))
    rec = rec[rec.n >= 12]
    for pid, p in pctl(rec.y).items(): rat.setdefault(pid, round(70 + 25 * p))
    ru = pbp[(pbp.play_type == "run") & pbp.rusher_player_id.notna()].groupby("rusher_player_id").agg(y=("rushing_yards", "sum"), n=("play_id", "size"))
    ru = ru[ru.n >= 25]
    for pid, p in pctl(ru.y).items(): rat.setdefault(pid, round(70 + 22 * p))
    db = pbp[pbp.qb_dropback == 1]
    sack = db.groupby("posteam").sack.mean()
    rush = pbp[pbp.play_type == "run"].groupby("posteam").epa.mean()
    olr = ((pctl(sack, False) + pctl(rush)) / 2).rank(pct=True)
    dep = pbp[pbp.play_type.isin(["run", "pass"])].groupby("defteam").epa.mean()
    drr = pctl(dep, False)

    # ---- find late, close drives that ended in points or a near miss ----
    cands = []
    for (gid, dr), d in pbp[pbp.qtr == 4].groupby(["game_id", "fixed_drive"]):
        d = d.sort_values("play_id"); first = d.iloc[0]
        if pd.isna(first.posteam) or pd.isna(first.down) and len(d) < 2: continue
        snaps = d[d.down.notna()]
        if snaps.empty: continue
        first = snaps.iloc[0]
        t = first.game_seconds_remaining; sd = first.score_differential
        if not (15 <= t <= 240 and -8 <= sd <= 0): continue
        result = first.fixed_drive_result
        if result not in ("Touchdown", "Field goal", "Missed field goal"): continue
        if len(snaps) < 3: continue
        cands.append((gid, first))
    rows = []
    for gid, first in cands:
        g = pbp[pbp.game_id == gid].sort_values("play_id")
        team, opp, home = first.posteam, first.defteam, first.home_team
        fin = g.iloc[-1]
        pf = fin.total_home_score if team == home else fin.total_away_score
        pa = fin.total_away_score if team == home else fin.total_home_score
        ot = bool((g.qtr >= 5).any())
        d = g[(g.fixed_drive == first.fixed_drive) & (g.posteam == team)]
        fgs = d[d.play_type == "field_goal"]
        plays = d[d.play_type.isin(["pass", "run"])]
        if first.fixed_drive_result != "Touchdown":
            if fgs.empty: continue
            last = fgs.iloc[-1]
        else:
            tds = plays[plays.touchdown == 1]
            if tds.empty: continue
            last = tds.iloc[-1]
        my, op = int(first.posteam_score), int(first.defteam_score)
        after = my + (6 if last.touchdown == 1 else 3 if last.field_goal_result == "made" else 0)
        # what the real team got out of this drive, measured at the end of regulation
        reg = g[g.qtr <= 4].iloc[-1]
        rf = reg.total_home_score if team == home else reg.total_away_score
        ra = reg.total_away_score if team == home else reg.total_home_score
        res = "win" if rf > ra else "tie" if rf == ra else "loss"
        nm = lambda pid, fb: fullname.get(pid, fb) if pd.notna(pid) else fb
        left = clock(last.game_seconds_remaining)
        if last.touchdown == 1 and last.play_type == "pass":
            score = f"{nm(last.passer_player_id, last.passer_player_name)} hit {nm(last.receiver_player_id, last.receiver_player_name)} for a {int(last.yards_gained)}-yard touchdown with {left} left"
            short = f"TD with {left} left"
        elif last.touchdown == 1:
            score = f"{nm(last.rusher_player_id, last.rusher_player_name)} ran it in from {int(last.yards_gained)} yard{'s' if last.yards_gained != 1 else ''} out with {left} left"
            short = f"TD with {left} left"
        elif last.field_goal_result == "made":
            score = f"{nm(last.kicker_player_id, last.kicker_player_name)} made a {int(last.kick_distance)}-yard field goal with {left} left"
            short = f"{int(last.kick_distance)}-yd FG, {left} left"
        else:
            score = f"{nm(last.kicker_player_id, last.kicker_player_name)}'s {int(last.kick_distance or 0)}-yard try with {left} left missed"
            short = f"Missed {int(last.kick_distance or 0)}-yd FG"
        if ot and res == "tie":
            short += ", " + ("won in OT" if pf > pa else "lost in OT" if pf < pa else "game ended tied")
        elif res == "loss" and after >= op:
            short += ", but lost"
        lead = f"Down {op - my} with {clock(first.game_seconds_remaining)} left" if op > my else f"Tied with {clock(first.game_seconds_remaining)} left"
        spot = int(100 - first.yardline_100)
        text = (f"{lead} at {'their own' if spot < 50 else 'the'} {spot if spot <= 50 else 100 - spot}, the {NICK.get(team, team)} went {len(d[d.down.notna()])} plays. "
                f"{score[0].upper() + score[1:]}. Final{' in overtime' if ot else ''}: {NICK.get(team, team)} {int(pf)}, {NICK.get(opp, opp)} {int(pa)}.")
        wp = first.wp if pd.notna(first.wp) else .3
        drama = (1 - wp) + (0.35 if first.season_type == "POST" else 0) + (0.2 if res == "win" and last.game_seconds_remaining <= 10 else 0) + (0.15 if ot else 0)
        roof, temp, wind, wx = first.roof, first.temp, first.wind, str(first.weather or "")
        w = "dome" if roof in ("dome", "closed") else "snow" if "snow" in wx.lower() else "cold" if pd.notna(temp) and temp < 36 else "wind" if pd.notna(wind) and wind >= 15 else "clear"
        rows.append(dict(gid=gid, team=team, opp=opp, wk=int(first.week), st=first.season_type, date=first.game_date, my=my, op=op,
                         t=int(first.game_seconds_remaining), yl=spot, to=int(first.posteam_timeouts_remaining), w=w, res=res, short=short,
                         text=text, drama=drama, coach=first.home_coach if team == home else first.away_coach))
    if not rows:
        print("no drives found"); return
    df = pd.DataFrame(rows).sort_values("drama", ascending=False)
    # best 3 per week (one per game), newest weeks first
    df = df.drop_duplicates("gid").groupby("wk").head(3).sort_values(["wk", "drama"], ascending=[False, False])

    # ---- lineups from that week's depth chart ----
    dc["d"] = dc.dt.str[:10]

    def depth(team, date):
        s = dc[(dc.team == team) & (dc.d <= date)]
        if s.empty: s = dc[dc.team == team]
        s = s[(s.d == s.d.max()) & s.player_name.notna() & (s.pos_rank == 1)]
        return s

    def tri(r): return [fullname.get(r.gsis_id, r.player_name), num.get(r.gsis_id)]

    def lineup(team, opp, date, gid):
        o, dfn = {}, {}
        s = depth(team, date); off = s[s.pos_grp.str.contains("WR")]
        for k, p in [("QB", "QB"), ("RB", "RB"), ("TE", "TE"), ("LT", "LT"), ("LG", "LG"), ("C", "C"), ("RG", "RG"), ("RT", "RT")]:
            r = off[off.pos_abb == p]
            if len(r): o[k] = (tri(r.iloc[0]), r.iloc[0].gsis_id)
        wrs = dc[(dc.team == team) & (dc.d == s.d.max()) & (dc.pos_abb == "WR") & dc.player_name.notna()].sort_values("pos_rank").drop_duplicates("player_name")
        for k, (_, r) in zip(["X", "Z", "SL"], wrs.head(3).iterrows()): o[k] = (tri(r), r.gsis_id)
        q = pbp[(pbp.game_id == gid) & (pbp.posteam == team) & pbp.passer_player_id.notna()]
        if len(q):
            qid = q.passer_player_id.value_counts().index[0]
            o["QB"] = ([fullname.get(qid, q[q.passer_player_id == qid].passer_player_name.iloc[0]), num.get(qid)], qid)
        ds = depth(opp, date); ds = ds[ds.pos_grp.str.contains(" D")]
        groups = {"DE": [], "DT": [], "LB": [], "CB": [], "S": []}
        for r in ds.itertuples():
            g = DPOS.get(r.pos_abb)
            if g and tri(r)[0] not in [x[0] for x in groups[g]]: groups[g].append(tri(r))
        if len(groups["DT"]) < 2: groups["DT"] += groups["LB"][3:]  # 3-4 fronts: extra backer plays the 2nd tackle spot
        for ks, g in [(["DE1", "DE2"], "DE"), (["DT1", "DT2"], "DT"), (["LB1", "LB2", "LB3"], "LB"), (["CB1", "CB2"], "CB"), (["S1", "S2"], "S")]:
            for k, v in zip(ks, groups[g]): dfn[k] = v
        out = {}
        for k in OFFK:
            if k in o:
                (n, j), pid = o[k]
                out[k] = [n, j] + ([rat.get(pid, 74)] if k in SKILL else [])
        for k in DEFK:
            if k in dfn: out[k] = dfn[k]
        return out

    drives = []
    for r in df.itertuples():
        did = ("a" + r.gid.replace("_", "") + r.team).lower()
        drives.append(dict(
            id=did, game=title(S, r.st, r.wk, r.team), date=datetime.date.fromisoformat(r.date).strftime("%b %-d, %Y"),
            team=NICK.get(r.team, r.team), opp=NICK.get(r.opp, r.opp), my=r.my, op=r.op, t=r.t, yl=r.yl, to=r.to, w=r.w,
            late=r.t <= 150, week=r.wk, real=dict(res=r.res, short=r.short, text=r.text),
            roster=lineup(r.team, r.opp, r.date, r.gid), coach=r.coach,
            tr=dict(ol=round(72 + 16 * float(olr.get(r.team, .5))), dr=round(72 + 18 * float(drr.get(r.opp, .5))))))
    # keep earlier entries that dropped out of this season's file (e.g. last season's playoffs)
    old, prev = [], {}
    if os.path.exists(a.out):
        try: prev = json.load(open(a.out)); old = prev.get("drives", [])
        except Exception: pass
    ids = {d["id"] for d in drives}
    drives += [d for d in old if d["id"] not in ids]
    drives = drives[: a.keep]
    clean = json.loads(json.dumps(drives, default=lambda x: x.item() if hasattr(x, "item") else str(x)))
    if clean == old:
        print("no changes"); return
    json.dump(dict(updated=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), season=S, drives=drives),
              open(a.out, "w"), indent=0, ensure_ascii=False, default=lambda x: x.item() if hasattr(x, "item") else str(x))
    for d in drives[:12]:
        print(d["id"], d["game"], d["team"], "vs", d["opp"], f'{d["my"]}-{d["op"]}', clock(d["t"]), d["real"]["short"], "|", d["real"]["text"][:110])
    print(len(drives), "drives written to", a.out)


if __name__ == "__main__":
    main()
