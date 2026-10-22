"""Operation Quiet Ledger: live AI security tabletop.

Participants: open the join link (?s=<session code>), read the briefing, answer each situation.
Facilitator: open ?admin and enter ADMIN_PASSWORD to see the gap analysis, Cisco mapping and responses.
"""
import hmac
import html
import io
from urllib.parse import urlencode, urlsplit, urlunsplit

import altair as alt
import pandas as pd
import qrcode
import streamlit as st

import store
from content import (AGENTS, ARCH_DOT, BY_ID, CAP_ORDER, CAPS, CISCO, DETECT, FIRST, GROUND_RULES,
                     INJECT_IDS, INJECTS, MODULES, NOT_EXERCISED, OBS, OWNER, ROLES, SCENARIO, SOURCES,
                     SUBTITLE, SYSTEM, TITLE)
from scoring import LEVEL_WORD, aggregate, level, sample_answers

st.set_page_config(page_title=TITLE, page_icon=":material/shield:", layout="centered")

COLORS = {"good": "#1D8A57", "warn": "#B57A06", "crit": "#C23D2C", "na": "#98A4B1"}
SOFT = {"good": "#DDF2E7", "warn": "#FBEFD3", "crit": "#F9E1DD", "na": "#ECEFF2"}

st.html("""<style>
h1,h2,h3{font-family:'Archivo','Source Sans Pro',sans-serif;letter-spacing:-.01em}
.ql-tag{font:500 .78rem ui-monospace,Menlo,monospace;color:#566576;letter-spacing:.06em;text-transform:uppercase}
.block-container{padding-top:2.2rem}
</style>""")


def esc(s):
    return html.escape(str(s), quote=True)


def pct(v):
    return "–" if v is None or pd.isna(v) else f"{round(v)}%"


# =====================================================================
# Participant side
# =====================================================================
def briefing(full=True):
    st.markdown("#### Ground rules")
    for i, r in enumerate(GROUND_RULES, 1):
        st.markdown(f"{i}. {r}")
    st.markdown("#### Scenario")
    st.write(SCENARIO)
    if full:
        st.markdown("#### System under test")
        st.write(SYSTEM)
        st.dataframe(pd.DataFrame(AGENTS, columns=["Agent", "Job", "Can act on"]), hide_index=True, width="stretch")
        st.graphviz_chart(ARCH_DOT, width="stretch")
        st.caption("Highlighted boxes are the control points the situations test: the model gateway, the agent registry and intake.")
        st.markdown("#### Taxonomy")
        st.write("Every situation is tagged with Cisco's Integrated AI Security and Safety Framework: 19 attacker "
                 "objectives (OB-001 to OB-019), 40 techniques and 111 subtechniques across the AI lifecycle. "
                 "This exercise touches 15 of the 19 objectives.")


def join_form(code):
    with st.form("join"):
        st.markdown("#### Join the exercise")
        role = st.selectbox("Your role in this exercise", ROLES, index=None, placeholder="Choose your role")
        name = st.text_input("Your name (optional)", max_chars=120)
        org = st.text_input("Your team or organization (optional)", max_chars=160)
        if st.form_submit_button("Start the situations", type="primary"):
            if not role:
                st.error("Choose your role to start.")
                return
            pid = store.add_participant(code, name, role, org)
            st.query_params["p"] = pid
            st.session_state.pid = pid
            st.rerun()


def unlocked(sess, iid):
    if sess["mode"] != "led":
        return True
    return INJECT_IDS.index(iid) <= INJECT_IDS.index(sess["current_inject"])


@st.fragment(run_every=4)
def led_watcher(code):
    """Reruns the page when the facilitator moves the exercise on."""
    s = store.get_session(code)
    if not s:
        return
    snap = (s["mode"], s["current_inject"], tuple(s["revealed"]), s["is_open"])
    prev = st.session_state.get("_snap")
    st.session_state._snap = snap
    if prev is not None and prev != snap:
        if s["mode"] == "led" and (prev[1] != snap[1] or prev[0] != snap[0]):
            st.session_state.sel = s["current_inject"]
        st.rerun(scope="app")


def good_block(inj):
    with st.container(border=True):
        st.markdown("**What good looks like**")
        df = pd.DataFrame([(CAPS[c], sig, resp) for c, sig, resp in inj["good"]],
                          columns=["Capability", "Expected signal", "Expected response"])
        st.dataframe(df, hide_index=True, width="stretch")
        st.markdown("**Discuss:** " + " ".join(inj["disc"]))
        st.markdown("**Gap probe:** " + inj["probe"])


def situation(inj, sess, pid, mine):
    a = mine.get(inj["id"])
    mod, stage = MODULES[inj["m"]]
    st.markdown(f"<span class='ql-tag'>Module {inj['m']} · {esc(mod)} · {esc(stage)} · {esc(inj['t'])}</span>", unsafe_allow_html=True)
    st.subheader(f"{inj['id']} · {inj['title']}", anchor=False)
    if not unlocked(sess, inj["id"]):
        st.info("The facilitator will open this situation soon.", icon=":material/lock:")
        return
    st.write(inj["text"])
    tags = " ".join(f":blue-badge[{o} {OBS[o]}]" for o in inj["ob"]) + " " + " ".join(f":gray-badge[{t}]" for t in inj["tech"])
    st.markdown(tags)

    k = inj["id"].replace(".", "_")
    with st.form(f"f_{k}"):
        act = st.text_area("1. What do you do first?", value=(a or {}).get("act") or "", max_chars=600,
                           placeholder="Who does what, in the first 15 minutes?", key=f"act_{k}")
        dkeys = list(DETECT)
        d = st.radio("2. Would your organization detect this today?", dkeys, format_func=lambda x: DETECT[x][0],
                     index=dkeys.index(a["d"]) if a else None, key=f"d_{k}")
        fkeys = list(FIRST)
        f = st.radio("3. What would catch it first?", fkeys, format_func=lambda x: FIRST[x],
                     index=fkeys.index(a["f"]) if a else None, key=f"f_{k}")
        okeys = list(OWNER)
        o = st.radio("4. Who owns the decision?", okeys, format_func=lambda x: OWNER[x][0],
                     index=okeys.index(a["o"]) if a else None, key=f"o_{k}")
        disabled = not sess["is_open"]
        if st.form_submit_button("Update answer" if a else "Submit answer", type="primary", disabled=disabled):
            if not (d and f and o):
                st.error("Answer questions 2, 3 and 4 to submit.")
            else:
                store.save_answer(pid, sess["code"], inj["id"], act, d, f, o)
                st.session_state.flash = f"Answer to {inj['id']} saved."
                nxt = next((x for x in INJECT_IDS if x not in mine and x != inj["id"] and unlocked(sess, x)), None)
                if nxt and sess["mode"] != "led":
                    st.session_state.sel_next = nxt
                st.rerun()
    if disabled:
        st.caption("Submissions are closed for this session.")
    if a and (inj["id"] in sess["revealed"] or sess["mode"] != "led"):
        good_block(inj)


def go(delta):
    i = INJECT_IDS.index(st.session_state.sel) + delta
    st.session_state.sel = INJECT_IDS[max(0, min(len(INJECT_IDS) - 1, i))]


def participant(code):
    sess = store.get_session(code)
    st.markdown(f"<span class='ql-tag'>{esc(SUBTITLE)}</span>", unsafe_allow_html=True)
    st.title(TITLE, anchor=False)
    if not sess:
        st.error("This exercise link is not valid. Ask the facilitator for the QR code again.")
        return

    pid = st.session_state.get("pid") or st.query_params.get("p")
    me = store.get_participant(pid, code) if pid else None
    if not me:
        st.markdown("##### An attacker is turning your company's AI agents against it. Would you see it, and would you stop it?")
        st.write("Over 16 situations, a financially motivated group tries to redirect supplier payments and steal "
                 "customer data through a multi-agent application. For each one, answer for your own organization "
                 "as it runs today. Your answers go to the facilitator, who builds the room's gap analysis.")
        if not sess["is_open"]:
            st.warning("This session is closed to new answers.")
            briefing()
            return
        join_form(code)
        briefing()
        return
    st.session_state.pid = me["pid"]

    led_watcher(code)
    mine = store.my_answers(me["pid"])
    if msg := st.session_state.pop("flash", None):
        st.toast(msg, icon=":material/check_circle:")

    tab_sit, tab_brief = st.tabs(["Situations", "Briefing"])
    with tab_brief:
        briefing()
    with tab_sit:
        done = len(mine)
        st.progress(done / len(INJECTS), text=f"You have answered {done} of {len(INJECTS)} situations.")
        if done == len(INJECTS):
            st.success("All 16 answered. Thank you. You can still change any answer until the facilitator closes the session.")
        if sess["mode"] == "led":
            st.caption("The facilitator opens situations one at a time. Answer the open one, then discuss as a room.")
        else:
            st.caption("Work at your own pace. After you submit, \"what good looks like\" opens for that situation.")

        if "sel_next" in st.session_state:
            st.session_state.sel = st.session_state.pop("sel_next")
        if st.session_state.get("sel") not in INJECT_IDS:
            if sess["mode"] == "led":
                st.session_state.sel = sess["current_inject"]
            else:
                st.session_state.sel = next((x for x in INJECT_IDS if x not in mine), INJECT_IDS[0])

        def label(x):
            mark = "✓ " if x in mine else ("🔒 " if not unlocked(sess, x) else "")
            return f"{mark}{x} · {BY_ID[x]['title']}"

        st.selectbox("Situation", INJECT_IDS, format_func=label, key="sel")
        situation(BY_ID[st.session_state.sel], sess, me["pid"], mine)
        c1, c2 = st.columns(2)
        c1.button("Previous", on_click=go, args=(-1,), width="stretch", disabled=st.session_state.sel == INJECT_IDS[0])
        c2.button("Next", on_click=go, args=(1,), width="stretch", disabled=st.session_state.sel == INJECT_IDS[-1])


# =====================================================================
# Facilitator side
# =====================================================================
def admin_login():
    try:
        pw = st.secrets.get("ADMIN_PASSWORD")
    except Exception:
        pw = None
    if not pw:
        st.error("The facilitator view is disabled until ADMIN_PASSWORD is set in the app's secrets.")
        return False
    if st.session_state.get("admin_ok"):
        return True
    st.title("Facilitator sign-in", anchor=False)
    with st.form("login"):
        entered = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            if hmac.compare_digest(entered.encode(), str(pw).encode()):
                st.session_state.admin_ok = True
                st.rerun()
            st.error("Wrong password.")
    return False


def base_url():
    try:
        configured = st.secrets.get("APP_URL")
    except Exception:
        configured = None
    if configured:
        return configured.rstrip("/")
    u = st.context.url or ""
    p = urlsplit(u)
    return urlunsplit((p.scheme, p.netloc, p.path, "", "")).rstrip("/")


def qr_png(url):
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=3)
    q.add_data(url)
    q.make()
    buf = io.BytesIO()
    q.make_image(fill_color="#122030", back_color="white").save(buf, "PNG")
    return buf.getvalue()


def bar_chart(df, label_col, value_col):
    df = df.copy()
    df["lv"] = df[value_col].map(level)
    df["shown"] = df[value_col].fillna(0)
    df["txt"] = df[value_col].map(pct)
    base = alt.Chart(df).encode(y=alt.Y(f"{label_col}:N", sort=None, title=None, axis=alt.Axis(labelLimit=320)))
    bars = base.mark_bar(cornerRadiusEnd=3, height=14).encode(
        x=alt.X("shown:Q", scale=alt.Scale(domain=[0, 100]), title="Readiness (%)"),
        color=alt.Color("lv:N", scale=alt.Scale(domain=list(COLORS), range=list(COLORS.values())), legend=None),
        tooltip=[label_col, "txt"])
    txt = base.mark_text(align="left", dx=4, fontSize=11).encode(x="shown:Q", text="txt:N")
    rule = alt.Chart(pd.DataFrame({"x": [40, 70]})).mark_rule(strokeDash=[3, 3], color="#A9B5C2").encode(x="x:Q")
    return (bars + txt + rule).properties(height=max(120, 26 * len(df)))


def heatmap(A):
    tiles = []
    for o, name in OBS.items():
        if o in NOT_EXERCISED:
            tiles.append(f"<div class='t off' title='{esc(NOT_EXERCISED[o])}'><b>{o}</b><span>{esc(name)}</span><i>Not exercised</i></div>")
            continue
        v = A["ob"][o]["avg"]
        lv = level(v)
        tiles.append(f"<div class='t' style='background:{SOFT[lv]};border-color:{COLORS[lv]}'><b>{o}</b><span>{esc(name)}</span>"
                     f"<em>{pct(v)}</em><i>{LEVEL_WORD[lv]} · {', '.join(A['ob'][o]['injects'])}</i></div>")
    legend = "".join(f"<span><i style='background:{COLORS[k]}'></i>{w}</span>" for k, w in
                     [("good", "Ready, 70%+"), ("warn", "Partial, 40-69%"), ("crit", "Gap, under 40%"), ("na", "No answers yet")])
    st.html(f"""<style>
.hm{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;font-family:'Source Sans Pro',system-ui,sans-serif;color:#122030}}
.hm .t{{border:1px solid;border-radius:8px;padding:9px 11px;display:flex;flex-direction:column;gap:3px;min-height:100px}}
.hm b{{font:600 .72rem ui-monospace,Menlo,monospace}} .hm span{{font-size:.82rem;font-weight:600;line-height:1.25}}
.hm em{{font-style:normal;font-weight:700;font-size:1.15rem;margin-top:auto}} .hm i{{font-style:normal;font-size:.72rem;color:#3d4a58}}
.hm .off{{background:repeating-linear-gradient(135deg,#ECEFF2 0 6px,#fff 6px 12px);border-color:#D4DBE3;color:#7d8b99}}
.lg{{display:flex;gap:14px;flex-wrap:wrap;font-size:.8rem;color:#566576;margin:4px 0 10px;font-family:system-ui,sans-serif}}
.lg i{{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}}
</style><div class='lg'>{legend}</div><div class='hm'>{''.join(tiles)}</div>""")


def data_for(code):
    if st.session_state.get("sample"):
        return sample_answers()
    return store.session_frames(code)


def gap_view(code):
    parts, ans = data_for(code)
    A = aggregate(ans)
    if st.session_state.get("sample"):
        st.warning("Showing example answers from six fictional participants. Not real data.", icon=":material/science:")
    if not A["answers"]:
        st.info("No answers yet. As participants submit, readiness by objective, situation and capability appears here.")
        return
    c = st.columns(5)
    c[0].metric("Participants", A["people"])
    c[1].metric("Answers", A["answers"])
    c[2].metric("Overall readiness", pct(A["overall"]))
    c[3].metric("Situations below 40%", A["gaps"])
    c[4].metric("Include \"don't know\"", pct(A["dk"]))

    st.subheader("Readiness by taxonomy objective", anchor=False)
    st.caption("Cisco Integrated AI Security and Safety Framework. Readiness = 70% detection + 30% decision ownership.")
    heatmap(A)

    st.subheader("Readiness by situation, weakest first", anchor=False)
    rows = []
    for inj in INJECTS:
        s = A["per"][inj["id"]]
        flags = []
        if s["spread"] >= 30:
            flags.append("room disagrees")
        if s["n"] and s["dk"] / s["n"] >= .3:
            flags.append(f"{round(s['dk'] / s['n'] * 100)}% don't know")
        rows.append({"Situation": f"{inj['id']} {inj['title']}" + (f"  [{'; '.join(flags)}]" if flags else ""), "v": s["avg"]})
    df = pd.DataFrame(rows).sort_values("v", na_position="last")
    st.altair_chart(bar_chart(df, "Situation", "v"), width="stretch")
    st.caption("\"Room disagrees\" means answers are far apart: people have different pictures of the same control.")

    st.subheader("Readiness by capability", anchor=False)
    cdf = pd.DataFrame([{"Capability": CAPS[c], "v": A["cap"][c]["avg"]} for c in CAP_ORDER]).sort_values("v", na_position="last")
    st.altair_chart(bar_chart(cdf, "Capability", "v"), width="stretch")

    st.subheader("What would catch it first: room vs. design", anchor=False)
    fr = []
    for inj in INJECTS:
        s = A["per"][inj["id"]]
        if not s["n"]:
            continue
        top = max(s["first"], key=s["first"].get)
        fr.append({"Situation": f"{inj['id']} {inj['title']}", "Room's most common answer": FIRST[top],
                   "Share": f"{round(s['first'][top] / s['n'] * 100)}%", "Designed first catch": CAPS[inj["primary"]],
                   "Match": "Yes" if top == inj["primary"] else "No"})
    st.dataframe(pd.DataFrame(fr), hide_index=True, width="stretch")


def cisco_view(code):
    parts, ans = data_for(code)
    A = aggregate(ans)
    if not A["answers"]:
        st.info("This view ranks capabilities and Cisco products by the room's gaps. It fills in once answers arrive.")
    st.caption("Capabilities ranked by how much of the room's gap they would close (gap on each situation they cover, "
               "weighted 1.5x where it is the designed first catch). **Minimum stack** = Cisco AI Defense + Splunk Agent Observability.")
    ranked = sorted(CAP_ORDER, key=lambda c: -A["cap"][c]["gap"])
    for i, c in enumerate(ranked, 1):
        s = A["cap"][c]
        lv = level(s["avg"])
        is_min, products = CISCO[c]
        with st.container(border=True):
            l, r = st.columns([2, 3])
            with l:
                st.caption(f"Priority {i}")
                st.markdown(f"**{CAPS[c]}**")
                color = {"good": "green", "warn": "orange", "crit": "red", "na": "gray"}[lv]
                st.markdown(f":{color}-badge[{LEVEL_WORD[lv]} · {pct(s['avg'])}]" + (" :blue-badge[Minimum stack]" if is_min else ""))
                st.caption("Situations " + ", ".join(s["injects"]))
            with r:
                for n, d in products:
                    st.markdown(f"**{n}**  \n{d}")
                st.markdown(" ".join(f":blue-badge[{o} {OBS[o]}]" for o in s["obs"]))

    st.subheader("By taxonomy objective", anchor=False)
    rows = []
    for o in OBS:
        if o in NOT_EXERCISED:
            continue
        v = A["ob"][o]["avg"]
        caps = [c for c in CAP_ORDER if any(o in i["ob"] and c in i["caps"] for i in INJECTS)]
        prods = sorted({p for c in caps for p, _ in CISCO[c][1] if p != "Your application team"})
        rows.append({"Objective": f"{o} {OBS[o]}", "Readiness": pct(v), "Status": LEVEL_WORD[level(v)], "_v": -1 if v is None else v,
                     "Cisco products that address it": "; ".join(prods)})
    st.dataframe(pd.DataFrame(rows).sort_values("_v").drop(columns="_v"), hide_index=True, width="stretch")
    st.markdown("**Sources:** " + " · ".join(f"[{n}]({u})" for n, u in SOURCES))


def responses_view(code):
    parts, ans = store.session_frames(code)
    if parts.empty:
        st.info("Nobody has joined this session yet.")
        return
    counts = ans.groupby("pid").size() if not ans.empty else pd.Series(dtype=int)
    p = parts.assign(answered=parts["pid"].map(counts).fillna(0).astype(int),
                     joined=pd.to_datetime(parts["created_at"], unit="s").dt.strftime("%Y-%m-%d %H:%M UTC"))
    p["name"] = p["name"].replace("", "(no name)")
    st.markdown(f"**{len(p)} joined**")
    st.dataframe(p[["name", "role", "org", "answered", "joined"]], hide_index=True, width="stretch")
    if not ans.empty:
        who = parts.set_index("pid")
        out = ans.assign(name=ans["pid"].map(who["name"]), role=ans["pid"].map(who["role"]), org=ans["pid"].map(who["org"]),
                         situation=ans["inject"].map(lambda x: f"{x} {BY_ID[x]['title']}"),
                         detect=ans["d"].map(lambda x: DETECT[x][0]), first_catch=ans["f"].map(FIRST.get),
                         owner=ans["o"].map(lambda x: OWNER[x][0]), first_action=ans["act"])
        out = out.sort_values(["inject", "role"])[["situation", "name", "role", "org", "detect", "first_catch", "owner", "first_action"]]
        st.dataframe(out, hide_index=True, width="stretch")
        st.download_button("Download all answers (CSV)", out.to_csv(index=False).encode(), f"ttx_{code}_answers.csv", "text/csv")
    with st.expander("Remove a participant"):
        opts = {r.pid: f"{r.name or '(no name)'} · {r.role} · {r.answered} answers" for r in p.itertuples()}
        victim = st.selectbox("Participant", list(opts), format_func=opts.get, index=None)
        if st.button("Remove participant and their answers", disabled=not victim):
            store.delete_participant(victim)
            st.rerun()


def facilitator_view(sess):
    code = sess["code"]
    link = f"{base_url()}/?{urlencode({'s': code})}"
    with st.container(border=True):
        l, r = st.columns([1, 2])
        png = qr_png(link)
        l.image(png, width=220)
        with r:
            st.markdown("**Participants scan this to join.** No sign-in needed.")
            st.code(link, language=None)
            st.download_button("Download QR code (PNG)", png, f"ttx_{code}_qr.png", "image/png")
    with st.container(border=True):
        st.markdown("**Pace**")
        mode = st.segmented_control("Mode", ["self", "led"], default=sess["mode"], key=f"mode_{code}",
                                    format_func={"self": "Self-paced: all situations open", "led": "Facilitator-led: one at a time"}.get)
        if mode and mode != sess["mode"]:
            store.update_session(code, mode=mode)
            st.rerun()
        cur = INJECT_IDS.index(sess["current_inject"])
        c1, c2, c3 = st.columns([3, 1, 1])
        pick = c1.selectbox("Open up to", INJECT_IDS, index=cur, format_func=lambda x: f"{x} · {BY_ID[x]['title']}", key=f"cur_{code}_{cur}")
        if pick != sess["current_inject"]:
            store.update_session(code, current_inject=pick)
            st.rerun()
        if c2.button("Previous", disabled=cur == 0, width="stretch"):
            store.update_session(code, current_inject=INJECT_IDS[cur - 1])
            st.rerun()
        if c3.button("Next", type="primary", disabled=cur == len(INJECT_IDS) - 1, width="stretch"):
            store.update_session(code, current_inject=INJECT_IDS[cur + 1], mode="led")
            st.rerun()
        b1, b2, b3 = st.columns(3)
        if b1.button(f"Reveal answers for {sess['current_inject']}", width="stretch"):
            store.update_session(code, revealed=sess["revealed"] + [sess["current_inject"]])
            st.rerun()
        if b2.button("Reveal all", width="stretch"):
            store.update_session(code, revealed=INJECT_IDS)
            st.rerun()
        if b3.button("Hide all", width="stretch"):
            store.update_session(code, revealed=[])
            st.rerun()
        st.caption(f"Revealed: {', '.join(sess['revealed']) or 'none'}. In self-paced mode, each participant sees "
                   "\"what good looks like\" after they submit, regardless of this setting.")
    with st.container(border=True):
        st.markdown("**Submissions**")
        open_ = st.toggle("Accept answers", value=sess["is_open"], key=f"open_{code}")
        if open_ != sess["is_open"]:
            store.update_session(code, is_open=open_)
            st.rerun()
        with st.expander("Reset or delete this session"):
            sure = st.checkbox("I understand this permanently deletes every answer in this session")
            d1, d2 = st.columns(2)
            if d1.button("Clear all answers", disabled=not sure, width="stretch"):
                store.reset_session(code)
                st.rerun()
            if d2.button("Delete session", disabled=not sure or code == "main", width="stretch"):
                store.delete_session(code)
                st.session_state.admin_code = "main"
                st.rerun()


def admin():
    if not admin_login():
        return
    sessions = store.list_sessions()
    codes = [s["code"] for s in sessions]
    names = {s["code"]: f"{s['name']} ({s['code']})" for s in sessions}
    with st.sidebar:
        st.markdown(f"**{TITLE}**  \nFacilitator")
        if st.session_state.get("admin_code") not in codes:
            st.session_state.admin_code = codes[0]
        st.selectbox("Session", codes, format_func=names.get, key="admin_code")
        with st.form("newsess", clear_on_submit=True):
            nm = st.text_input("New session name", placeholder="e.g. Acme Bank, 4 Nov")
            if st.form_submit_button("Create session") and nm.strip():
                st.session_state.admin_code = store.create_session(nm)
                st.rerun()
        st.toggle("Auto-refresh dashboards", value=True, key="auto")
        st.toggle("Preview with example answers", key="sample", help="Fictional answers, never saved.")
        if not store.persistent():
            st.warning("No DATABASE_URL set: answers are kept in a local SQLite file that Streamlit Cloud wipes on restart.")
        if st.button("Sign out"):
            st.session_state.admin_ok = False
            st.rerun()

    sess = store.get_session(st.session_state.admin_code)
    st.title(sess["name"], anchor=False)
    t1, t2, t3, t4 = st.tabs(["Facilitator", "Gap analysis", "Closing the gaps", "Responses"])
    every = 10 if st.session_state.get("auto") else None

    @st.fragment(run_every=every)
    def live_gaps():
        gap_view(sess["code"])

    @st.fragment(run_every=every)
    def live_cisco():
        cisco_view(sess["code"])

    @st.fragment(run_every=every)
    def live_resp():
        responses_view(sess["code"])

    with t1:
        facilitator_view(sess)
    with t2:
        live_gaps()
    with t3:
        live_cisco()
    with t4:
        live_resp()


# =====================================================================
if "admin" in st.query_params:
    admin()
else:
    participant(st.query_params.get("s", "main"))
