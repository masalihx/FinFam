"""Product verdict (ML part 5): Buy / Think about it / Not worth it.

Rules agreed by the team (docs/spec.md):
- "Not worth it" when at least one is true: price above the market range of similar
  items; high overspend risk; more than the family usually pays in this category;
  pushes back a goal that is already behind (wants only).
- Needs (school, medicine...) are judged by price only.
- "Reasonable price for you: up to $X" comes from the budget only: the highest price
  at which the overspend risk stays below the model's warning threshold.
The inputs are ML outputs: overspend probability (part 3), market range (part 4),
the family's usual prices (history), the category and need/want (part 1).
"""
from dataclasses import dataclass, field

RED_RISK = 0.75        # high risk (top ~20% of situations on validation months)
MIN_RISK_JUMP = 0.05   # a purchase must itself raise the risk to be blamed for it
MIN_THINK_JUMP = 0.02  # "Think about it" only if the purchase itself adds 2+ points of risk (or crosses the warning level)
MARKET_TOLERANCE = 0.10  # up to 10% above the typical range still counts as a normal price
MIN_GOAL_PRICE = 20.0  # tiny purchases do not move goals in a meaningful way


@dataclass
class Signals:
    price: float
    category_name: str
    is_need: bool
    risk_before: float = None
    risk_after: float = None
    warn_threshold: float = 0.44
    usual_p90: float = None          # 90th percentile of the family's single purchases in this category
    market_low: float = None
    market_high: float = None
    goal_name: str = None
    goal_behind: bool = False
    goal_delay_days: int = None


@dataclass
class Verdict:
    decision: str                    # buy | think | not_worth_it
    reasons: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)


def decide(s: Signals) -> Verdict:
    reasons, checks = [], {}

    over_market = s.market_high is not None and s.price > s.market_high * (1 + MARKET_TOLERANCE)
    near_market_top = s.market_low is not None and not over_market and s.price > (s.market_low + s.market_high) / 2
    checks["above_market"] = over_market
    if over_market:
        reasons.append(f"Similar items cost ${s.market_low:,.0f}–{s.market_high:,.0f}; "
                       f"this is {s.price / s.market_high - 1:.0%} above that range.")

    if s.is_need:
        checks["need"] = True
        if not over_market:
            reasons.append(f"{s.category_name} counts as a need, and the price looks normal.")
        return Verdict("not_worth_it" if over_market else ("think" if near_market_top else "buy"), reasons, checks)

    jump = (s.risk_after - s.risk_before) if s.risk_after is not None and s.risk_before is not None else 0.0
    high_risk = s.risk_after is not None and s.risk_after >= RED_RISK and jump >= MIN_RISK_JUMP
    # Judge the purchase, not the month: a category that is already likely to go over does not make
    # every small purchase "think" (v4.3; before, 158 of 200 sampled Amazon items were "think" for that reason alone).
    crosses = s.risk_before is not None and s.risk_after is not None and s.risk_before < s.warn_threshold <= s.risk_after
    some_risk = s.risk_after is not None and s.risk_after >= s.warn_threshold and (jump >= MIN_THINK_JUMP or crosses)
    already = s.risk_after is not None and s.risk_after >= s.warn_threshold and not some_risk and not high_risk
    checks["high_risk"] = high_risk
    if s.risk_after is not None and (high_risk or some_risk):
        reasons.append(f"Chance of going over your usual {s.category_name} spending this month: "
                       f"{s.risk_before:.0%} → {s.risk_after:.0%} with this purchase.")
    elif already:
        reasons.append(f"{s.category_name} is already likely to go over this month ({s.risk_after:.0%}), "
                       f"but this purchase barely changes it (+{max(0.0, jump) * 100:.0f} points).")

    above_usual = s.usual_p90 is not None and s.price > s.usual_p90
    checks["above_usual"] = above_usual
    if above_usual:
        reasons.append(f"More than your family usually pays for {s.category_name}: "
                       f"9 out of 10 of your purchases there are under ${s.usual_p90:,.0f}.")

    hurts_goal = s.goal_behind and s.price >= MIN_GOAL_PRICE
    checks["hurts_behind_goal"] = hurts_goal
    if hurts_goal:
        days = f" by about {s.goal_delay_days} days" if s.goal_delay_days else ""
        reasons.append(f"Your goal “{s.goal_name}” is already behind; this pushes it back{days}.")

    if over_market or high_risk or above_usual or hurts_goal:
        return Verdict("not_worth_it", reasons, checks)
    if some_risk or near_market_top:
        if near_market_top and not some_risk:
            reasons.append(f"The price is in the upper half of what similar items cost "
                           f"(${s.market_low:,.0f}–{s.market_high:,.0f}).")
        return Verdict("think", reasons, checks)
    if not reasons:
        reasons.append("Fits your budget and your usual prices.")
    return Verdict("buy", reasons, checks)


def reasonable_price(risk_at, threshold: float, upper: float, tol: float = 1.0):
    """Highest price with risk below `threshold`, by bisection. None if even a tiny price is too much."""
    if risk_at(1.0) >= threshold:
        return None
    lo, hi = 1.0, max(upper, 2.0)
    if risk_at(hi) < threshold:
        return hi
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if risk_at(mid) < threshold:
            lo = mid
        else:
            hi = mid
    return lo
