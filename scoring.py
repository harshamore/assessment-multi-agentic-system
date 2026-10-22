"""Readiness scoring. Per answer: 70% detection + 30% decision ownership.
Under 40 is a gap, 40-69 partial, 70+ ready."""
import random

import numpy as np
import pandas as pd

from content import BY_ID, CAP_ORDER, DETECT, INJECTS, OBS, OWNER, ROLES


def level(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "na"
    return "good" if v >= 70 else "warn" if v >= 40 else "crit"


LEVEL_WORD = {"good": "Ready", "warn": "Partial", "crit": "Gap", "na": "No answers"}


def score_rows(ans: pd.DataFrame) -> pd.DataFrame:
    if ans.empty:
        return ans.assign(score=pd.Series(dtype=float))
    a = ans.copy()
    a["score"] = a["d"].map(lambda x: DETECT.get(x, ("", 0))[1]) * 0.7 + a["o"].map(lambda x: OWNER.get(x, ("", 0))[1]) * 0.3
    a["dk"] = (a["d"] == "dk") | (a["f"] == "dk")
    return a


def aggregate(ans: pd.DataFrame):
    a = score_rows(ans)
    per = {}
    for inj in INJECTS:
        rows = a[a["inject"] == inj["id"]] if not a.empty else a
        n = len(rows)
        avg = float(rows["score"].mean()) if n else None
        spread = float(rows["score"].std(ddof=0)) if n > 1 else 0.0
        first = rows["f"].value_counts().to_dict() if n else {}
        per[inj["id"]] = dict(n=n, avg=avg, spread=spread, dk=int(rows["dk"].sum()) if n else 0, first=first)

    ob = {}
    for o in OBS:
        ids = [i["id"] for i in INJECTS if o in i["ob"]]
        vals = [per[x]["avg"] for x in ids if per[x]["n"]]
        ob[o] = dict(avg=float(np.mean(vals)) if vals else None, injects=ids)

    cap = {}
    for c in CAP_ORDER:
        ins = [i for i in INJECTS if c in i["caps"]]
        answered = [i for i in ins if per[i["id"]]["n"]]
        avg = float(np.mean([per[i["id"]]["avg"] for i in answered])) if answered else None
        gap = sum((100 - per[i["id"]]["avg"]) * (1.5 if i["primary"] == c else 1) for i in answered)
        obs = sorted({o for i in ins for o in i["ob"]})
        cap[c] = dict(avg=avg, gap=gap, injects=[i["id"] for i in ins], obs=obs)

    total = len(a)
    return dict(
        people=int(a["pid"].nunique()) if total else 0,
        answers=total,
        overall=float(a["score"].mean()) if total else None,
        dk=float(a["dk"].mean() * 100) if total else None,
        gaps=sum(1 for s in per.values() if s["n"] and s["avg"] < 40),
        per=per, ob=ob, cap=cap,
    )


def sample_answers(n_people=6, seed=7):
    """Fictional answers for previewing the dashboards. Never written to the database."""
    rnd = random.Random(seed)
    bias = {"1.1": .6, "1.2": .3, "2.1": .5, "2.2": .35, "3.1": .25, "3.2": .2, "3.3": .15, "4.1": .2,
            "4.2": .25, "5.1": .45, "5.2": .4, "6.1": .4, "6.2": .55, "7.1": .3, "7.2": .35, "7.3": .4}
    parts, rows = [], []
    for p in range(n_people):
        pid = f"sample{p}"
        parts.append(dict(pid=pid, code="sample", name=f"Example {p + 1}", role=ROLES[p], org="", created_at=0))
        for inj in INJECTS:
            b = bias[inj["id"]]
            r = rnd.random() * .6 + b * .8
            d = "stop" if r > .85 else "detect" if r > .6 else "partial" if r > .4 else ("no" if rnd.random() > .5 else "dk")
            o = "runbook" if rnd.random() < b else ("owner" if rnd.random() < .5 else "none")
            f = BY_ID[inj["id"]]["primary"] if rnd.random() < b + .2 else ("none" if rnd.random() < .5 else "dk")
            rows.append(dict(pid=pid, code="sample", inject=inj["id"], act="", d=d, f=f, o=o, at=0))
    return pd.DataFrame(parts), pd.DataFrame(rows)
