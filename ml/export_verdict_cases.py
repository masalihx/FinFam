"""Rule cases for checking the JavaScript verdict port against ml/verdict.py.

    .venv/bin/python ml/export_verdict_cases.py
"""
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verdict import Signals, decide  # noqa: E402

cases = []
for price, need, rb, ra, p90, low, high, behind in itertools.product(
        [15, 60, 140, 400], [False, True], [None, 0.2, 0.8], [None, 0.3, 0.5, 0.9], [None, 50, 200],
        [None, 30], [None, 120], [False, True]):
    if (rb is None) != (ra is None) or (low is None) != (high is None):
        continue
    s = Signals(price=price, category_name="Shopping", is_need=need, risk_before=rb, risk_after=ra, warn_threshold=0.44,
                usual_p90=p90, market_low=low, market_high=high, goal_name="College" if behind else None,
                goal_behind=behind, goal_delay_days=10 if behind else None)
    v = decide(s)
    cases.append({"in": {"price": price, "isNeed": need, "riskBefore": rb, "riskAfter": ra, "warnThreshold": 0.44,
                         "usualP90": p90, "marketLow": low, "marketHigh": high, "goalName": "College" if behind else None,
                         "goalBehind": behind, "goalDelayDays": 10 if behind else None, "categoryName": "Shopping"},
                  "decision": v.decision, "n_reasons": len(v.reasons)})
Path("extension/data/verdict_cases.json").write_text(json.dumps(cases))
print(len(cases), "cases")
