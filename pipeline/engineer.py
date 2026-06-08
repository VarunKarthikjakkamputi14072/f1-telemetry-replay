"""
AI Race Engineer: make independent strategy calls and score them against reality.

A deterministic strategist (tyre-life model + pit loss + undercut logic) decides,
lap by lap, when each featured driver should box and onto what compound — without
peeking at the future. We then line those calls up against what the driver
*actually* did and grade the agreement.

An optional LLM (Groq's free Llama, OpenAI-compatible) writes the strategic
verdict when GROQ_API_KEY is set; otherwise a templated verdict is used. The
decisions themselves are always the deterministic engine's, so the feature is
fully reproducible and works with no API key.
"""
from __future__ import annotations

import json
import os
import urllib.request

# Nominal laps before each compound hits the performance cliff (rough, generic).
TYRE_LIFE = {"SOFT": 20, "MEDIUM": 30, "HARD": 44, "INTER": 25, "WET": 22}
PIT_LOSS = 22.0  # seconds lost in a typical stop (pit lane + stationary)
MIN_LAPS_TO_PIT = 6  # don't bother stopping this close to the flag
N_FEATURED = 8  # how many drivers (by finishing position) to analyse


def _next_compound(laps_left: int) -> str:
    """Quickest compound expected to reach the flag from here."""
    if laps_left <= TYRE_LIFE["SOFT"]:
        return "SOFT"
    if laps_left <= TYRE_LIFE["MEDIUM"]:
        return "MEDIUM"
    return "HARD"


def _per_lap_state(code, drivers, analytics, total_laps):
    """Reconstruct (compound, tyre_age, pos, gap_ahead) per lap for one driver."""
    pos_by_lap = {int(k): v for k, v in analytics["positionByLap"].get(code, {}).items()}
    gap_self = {g["lap"]: g["gap"] for g in analytics["gapToLeader"].get(code, [])}
    # gap of whoever is directly ahead, per lap
    gap_by_code = {c: {g["lap"]: g["gap"] for g in analytics["gapToLeader"].get(c, [])}
                   for c in analytics["positionByLap"]}
    pos_to_code = {}
    for c, laps in analytics["positionByLap"].items():
        for lap, p in laps.items():
            pos_to_code.setdefault(int(lap), {})[p] = c

    stints = analytics["stints"].get(code, [])
    compound_at = {}
    age_at = {}
    for s in stints:
        for lap in range(s["lapStart"], s["lapEnd"] + 1):
            compound_at[lap] = s["compound"]
            age_at[lap] = lap - s["lapStart"] + 1

    state = {}
    for lap in range(1, total_laps + 1):
        pos = pos_by_lap.get(lap)
        gap_ahead = None
        if pos and pos > 1:
            ahead = pos_to_code.get(lap, {}).get(pos - 1)
            if ahead is not None and lap in gap_self and lap in gap_by_code.get(ahead, {}):
                gap_ahead = round(gap_self[lap] - gap_by_code[ahead][lap], 1)
        state[lap] = {
            "compound": compound_at.get(lap),
            "age": age_at.get(lap),
            "pos": pos,
            "gapAhead": gap_ahead,
        }
    return state


def _strategise(code, state, stints, total_laps, sc_laps):
    """
    Online strategist. Walks the race lap by lap on the *starting* compound and
    decides when to box, choosing the next tyre from laps remaining. Models worn
    tyres, undercuts, and the classic "box under the safety car" cheap stop.
    Returns the recommended stops and the notable decisions (with reasons).
    """
    if not stints:
        return [], []
    compound = stints[0]["compound"]
    stint_start = 1
    stops, decisions = [], []

    for lap in range(1, total_laps + 1):
        age = lap - stint_start + 1
        laps_left = total_laps - lap
        life = TYRE_LIFE.get(compound, 28)
        st = state.get(lap, {})
        gap_ahead = st.get("gapAhead")

        worn = age >= life * 0.92 and laps_left >= MIN_LAPS_TO_PIT
        undercut = (
            gap_ahead is not None and gap_ahead < 2.0
            and age >= life * 0.55 and laps_left > MIN_LAPS_TO_PIT
        )
        # A safety car makes a stop ~10s cheaper, so it's worth taking even late
        # (fresh rubber for the restart) — this is the classic "box, box" call.
        sc_stop = lap in sc_laps and age >= max(6, life * 0.35) and laps_left >= 3

        if worn or undercut or sc_stop:
            nxt = _next_compound(laps_left)
            if sc_stop and not worn:
                reason = f"Box under safety car — cheap stop off {age}-lap {compound}"
                conf = 0.9
            elif undercut and not worn:
                reason = f"Undercut the car ahead (+{gap_ahead:.1f}s) on worn {compound}"
                conf = 0.6
            else:
                reason = f"{compound} past its {life}-lap window (lap {age} on set)"
                conf = 0.85
            stops.append({"lap": lap, "compound": nxt})
            decisions.append({
                "lap": lap, "call": "BOX", "compound": nxt,
                "reason": reason, "confidence": conf,
            })
            compound = nxt
            stint_start = lap

    return stops, decisions


def _actual_stops(stints):
    return [{"lap": s["lapStart"], "compound": s["compound"]} for s in stints[1:]]


def _grade(actual, ai):
    """Match AI stops to actual stops within a tolerance and score agreement."""
    used = set()
    matched = 0
    compound_ok = 0
    deltas = []
    for a in actual:
        best, bj = 6, None
        for j, p in enumerate(ai):
            if j in used:
                continue
            d = abs(p["lap"] - a["lap"])
            if d < best:
                best, bj = d, j
        if bj is not None and best <= 5:
            used.add(bj)
            matched += 1
            deltas.append(ai[bj]["lap"] - a["lap"])
            if ai[bj]["compound"] == a["compound"]:
                compound_ok += 1
    denom = max(len(actual), len(ai), 1)
    return {
        "stopsMatched": matched,
        "actualStops": len(actual),
        "aiStops": len(ai),
        "compoundMatched": compound_ok,
        "pct": round(100 * matched / denom),
        "avgLapDelta": round(sum(deltas) / len(deltas), 1) if deltas else 0,
    }


def _templated_verdict(code, actual, ai, grade, finish_pos):
    if not actual and not ai:
        return f"{code} ran to the flag with no stop — nothing to second-guess."
    if grade["stopsMatched"] == len(actual) == len(ai):
        d = grade["avgLapDelta"]
        when = "right on the money" if abs(d) <= 1 else (
            f"about {abs(d):.0f} lap(s) {'earlier' if d < 0 else 'later'}")
        return (f"The engineer agreed with {code}'s {len(actual)}-stop plan, "
                f"boxing {when}. Compounds matched on "
                f"{grade['compoundMatched']}/{grade['stopsMatched']}.")
    if grade["aiStops"] > grade["actualStops"]:
        return (f"The engineer would have stopped more often than {code} "
                f"({grade['aiStops']} vs {grade['actualStops']}), chasing fresher "
                f"rubber rather than managing one long stint.")
    return (f"The engineer would have stopped less than {code} "
            f"({grade['aiStops']} vs {grade['actualStops']}), backing the tyres "
            f"to go longer.")


def _llm_verdict(payload):
    """Ask Groq's Llama for a one-paragraph verdict. Returns None on any failure."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    prompt = (
        "You are a Formula 1 race strategist. Compare the engineer's recommended "
        "pit strategy to what the driver actually did, in 2-3 sentences. Be specific "
        "and judgemental about undercuts, tyre life and stop count. Data:\n"
        + json.dumps(payload)
    )
    body = json.dumps({
        "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4, "max_tokens": 160,
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ LLM verdict skipped: {e}")
        return None


def _safety_car_laps(drivers, events):
    """Lap numbers run (even partly) under SC or VSC, via a reference driver's laps."""
    bands = [(b["start"], b["end"]) for b in events.get("trackStatus", [])
             if b["type"] in ("SC", "VSC")]
    if not bands:
        return set()
    # Reference = the driver with the most timed laps (usually the leader).
    ref = max(drivers.values(),
              key=lambda d: sum(1 for r in d["laps"] if r["t"] is not None),
              default=None)
    if ref is None:
        return set()
    laps = [(r["lap"], r["t"]) for r in ref["laps"] if r["lap"] and r["t"]]
    laps.sort()
    sc = set()
    prev_t = laps[0][1] - 120 if laps else 0
    for lap, t in laps:
        if any(bs < t and be > prev_t for bs, be in bands):
            sc.add(lap)
        prev_t = t
    return sc


def build_engineer(drivers, total_laps, analytics, driver_meta, events):
    """Per-driver AI-vs-reality strategy comparison for the featured finishers."""
    color = {d["code"]: d for d in driver_meta}
    sc_laps = _safety_car_laps(drivers, events)

    # Featured = best finishers we have stint data for.
    def final_pos(code):
        laps = analytics["positionByLap"].get(code, {})
        if not laps:
            return 99
        return laps[max(laps, key=lambda k: int(k))]

    featured = sorted(
        (c for c in analytics["stints"] if analytics["stints"][c] and c in color),
        key=final_pos,
    )[:N_FEATURED]

    use_llm = bool(os.environ.get("GROQ_API_KEY"))
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    out = []
    for code in featured:
        stints = analytics["stints"][code]
        state = _per_lap_state(code, drivers, analytics, total_laps)
        ai_stops, decisions = _strategise(code, state, stints, total_laps, sc_laps)
        actual = _actual_stops(stints)
        grade = _grade(actual, ai_stops)
        fpos = final_pos(code)

        payload = {
            "driver": code, "finishPosition": fpos,
            "startCompound": stints[0]["compound"],
            "actualStops": actual, "engineerStops": ai_stops, "agreement": grade,
        }
        verdict = (_llm_verdict(payload) if use_llm else None) \
            or _templated_verdict(code, actual, ai_stops, grade, fpos)

        out.append({
            "code": code,
            "name": color[code]["name"],
            "team": color[code]["team"],
            "color": color[code]["color"],
            "finishPos": fpos,
            "startCompound": stints[0]["compound"],
            "actualStints": stints,
            "aiStops": ai_stops,
            "actualStops": actual,
            "decisions": decisions,
            "agreement": grade,
            "verdict": verdict,
        })

    return {
        "source": "llama" if use_llm else "heuristic",
        "model": model if use_llm else "Deterministic strategist",
        "note": "Decisions are rule-based (tyre-life + pit-loss + undercut). "
                "Set GROQ_API_KEY to add Llama-written verdicts.",
        "drivers": out,
    }
