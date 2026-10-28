
"""Generate and rank intervention plans without executing them."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from common.contracts import (
    Plan,
    PlanCandidates,
    ScoreResult,
    Venue,
)
from common.gate_safety import validate_gate_safety
from common.llm import call_json
from imagine.fake_imagine import (
    apply_plan_to_venue,
    current_initial_counts,
    make_forecast,
    score_forecast,
    venue as active_venue,
)

router = APIRouter(prefix="/recommend", tags=["Recommendations"])


class RecommendationRequest(BaseModel):
    venue: Venue | None = None
    candidates: PlanCandidates | None = None


class RankedPlan(BaseModel):
    plan: Plan
    score: ScoreResult
    rank: int
    explanation: str


class RecommendationResponse(BaseModel):
    baseline: ScoreResult
    recommended_plan_id: str
    candidates_considered: int
    recommendations: list[RankedPlan]
    generation_source: str = "ai"


def _normalize_entry_name(value: str) -> str:
    """Normalize common punctuation mistakes in AI-generated entry names."""
    return value.strip().rstrip(" ,，;:.'\"”“‘’`").casefold()


def _validate_plan(plan: Plan, venue: Venue) -> None:
    """Reject actions that reference unavailable venue resources."""
    zone_ids = {zone.id for zone in venue.zones}
    link_ids = {link.id for link in venue.links}
    entry_lookup = {
        _normalize_entry_name(entry.name): entry
        for entry in venue.entries
    }
    entry_names = {entry.name for entry in venue.entries}
    pa_zones = set(venue.pa_zones)

    for action in plan.actions:
        if action.type == "gate":
            if action.link not in link_ids:
                raise ValueError(f"Unknown link: {action.link}")
            if action.state not in ("open", "closed"):
                raise ValueError("Gate actions must specify open or closed.")



        elif action.type == "hold_inflow":
            entry_key = (
                _normalize_entry_name(action.entry)
                if isinstance(action.entry, str)
                else ""
            )

            matched_entry = entry_lookup.get(entry_key)
            print(
                "[ENTRY DEBUG]",
                f"action_entry={action.entry!r}",
                f"entry_key={entry_key!r}",
                f"lookup_keys={list(entry_lookup.keys())!r}",
                f"matched_entry={matched_entry!r}",
                f"same_key={entry_key in entry_lookup}",
            )

            if matched_entry is None:
                raise ValueError(
                    f"Unknown entry: {action.entry!r}. "
                    f"Valid entries: {sorted(entry_names)}"
                    f"Lookup keys: {list(entry_lookup.keys())!r}. "
                    f"Valid entries: {sorted(entry_names)!r}"
                )

            # Normalize the model-generated value to the canonical venue name.
            action.entry = matched_entry.name

            if action.zone is not None and action.zone != matched_entry.zone:
                raise ValueError(
                    f"Entry {matched_entry.name!r} belongs to zone "
                    f"{matched_entry.zone!r}, not {action.zone!r}."
                )

            if (
                action.minutes is None
                or isinstance(action.minutes, bool)
                or not isinstance(action.minutes, int)
                or not 0 <= action.minutes <= 20
            ):
                raise ValueError(
                    f"Hold duration must be an integer between 0 and 20. "
                    f"Received: {action.minutes!r}"
                )


        elif action.type == "announce":
            if action.zone not in pa_zones:
                raise ValueError(
                    f"Zone {action.zone} has no configured PA system."
                )

        elif action.type == "move_officers":
            if action.from_zone not in zone_ids or action.to_zone not in zone_ids:
                raise ValueError("Officer movement references an unknown zone.")
            if action.count is None or action.count <= 0:
                raise ValueError("Officer movement count must be positive.")

    # Also validate gate action application using the existing simulator helper.

    validate_gate_safety(plan, venue)
    apply_plan_to_venue(plan, active_venue=venue)



def _score_plan(plan: Plan, venue: Venue) -> ScoreResult:
    """Score a plan against the supplied venue using the existing simulator."""
    from copy import deepcopy

    normalized_plan = deepcopy(plan)

    # Normalize hold_inflow entry names without modifying the original plan.
    for action in normalized_plan.actions:
        if action.type == "hold_inflow" and isinstance(action.entry, str):
            entry_key = _normalize_entry_name(action.entry)

            matched_entry = next(
                (
                    entry for entry in venue.entries
                    if entry.name.strip().casefold() == entry_key
                ),
                None,
            )

            if matched_entry is None:
                raise ValueError(f"Unknown entry: {action.entry!r}")

            action.entry = matched_entry.name

    planned_venue = venue.model_copy(deep=True)

    for action in normalized_plan.actions:
        if action.type == "gate":
            link = next(
                link for link in planned_venue.links
                if link.id == action.link
            )
            link.state = action.state

    hold_durations = {}
    for action in plan.actions:
        if action.type == "hold_inflow":
            hold_durations[action.zone] = action.minutes

    announce_zones = {
        action.zone
        for action in normalized_plan.actions
        if action.type == "announce" and action.zone
    }

    forecast = make_forecast(
        active_venue=planned_venue,
        initial_counts=current_initial_counts(),
        seed=42,
        hold_inflow_min=hold_durations,
        announce_zones=announce_zones,
    )
    return score_forecast(normalized_plan.plan_id, forecast)

def _generate_candidates(
    system_prompt: str,
    context: dict,
    selected_venue: Venue,
) -> tuple[PlanCandidates, list[dict]]:
    """Generate candidates, normalize hold actions, and use safe fallbacks."""

    import json
    from common.contracts import Action, Plan

    rejected = []
    prompt_context = dict(context)

    def normalize_plan(plan: Plan) -> Plan:
        """Repair incomplete hold_inflow actions using the selected venue."""
        normalized_actions = []

        entry_lookup = {
            entry.name.strip().casefold().rstrip(" ,;:.'\"”“‘’`"): entry
            for entry in selected_venue.entries
        }

        for action in plan.actions:
            if action.type != "hold_inflow":
                normalized_actions.append(action)
                continue

            raw_entry = action.entry or ""
            entry_key = (
                raw_entry.strip()
                .casefold()
                .rstrip(" ,;:.'\"”“‘’`")
            )
            entry = entry_lookup.get(entry_key)

            if entry is None:
                raise ValueError(
                    f"Unknown entry for hold_inflow action: {raw_entry!r}"
                )

            # Repair missing/invalid durations deterministically.
            minutes = action.minutes
            if (
                not isinstance(minutes, int)
                or isinstance(minutes, bool)
                or not 1 <= minutes <= 20
            ):
                minutes = {
                    "P1": 3,
                    "P2": 6,
                    "P3": 10,
                }.get(plan.plan_id, 5)

            normalized_actions.append(
                action.model_copy(
                    update={
                        "entry": entry.name,
                        "zone": entry.zone,
                        "minutes": minutes,
                    }
                )
            )

        return plan.model_copy(update={"actions": normalized_actions})

    # Try the AI twice, repairing incomplete hold actions each time.
    for attempt in range(2):
        try:
            candidates = call_json(
                role="super",
                purpose="recommend",
                system=system_prompt,
                user=json.dumps(prompt_context),
                response_model=PlanCandidates,
            )
        except Exception as exc:
            rejected.append(
                {
                    "attempt": attempt + 1,
                    "reason": f"AI generation failed: {exc}",
                }
            )
            continue


        valid_plans = []
        rejected_this_attempt = []

        for plan in candidates.plans:
            try:
                repaired_plan = normalize_plan(plan)
                _validate_plan(repaired_plan, selected_venue)
                valid_plans.append(repaired_plan)
            except (ValueError, TypeError) as exc:
                rejected_this_attempt.append(
                    {"plan_id": plan.plan_id, "reason": str(exc)}
                )

        if len(valid_plans) >= 3:
            return PlanCandidates(plans=valid_plans[:3]), rejected

        rejected.extend(rejected_this_attempt)
        prompt_context["previous_rejections"] = rejected_this_attempt
        prompt_context["retry_instruction"] = (
            "Return three valid plans. For hold_inflow actions, always include "
            "the exact entry name, its destination zone, and an integer "
            "duration from 1 to 20. Do not close a gate if that disconnects "
            "occupied zones. Use only resources present in the venue."
        )
    rejected.append({
        "source": "fallback",
        "reason": "AI generation did not produce three valid plans.",
    })
    # Reliable fallback: three different hold durations using a real entry.
    if not selected_venue.entries:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No valid entry is configured for fallback plans.",
                "rejected_candidates": rejected,
            },
        )

    entry = selected_venue.entries[0]
    fallback_plans = []

    for plan_id, minutes, strategy in [
        ("P1", 3, "Short inflow hold"),
        ("P2", 6, "Medium inflow hold"),
        ("P3", 10, "Long inflow hold"),
    ]:
        plan = Plan(
            plan_id=plan_id,
            strategy=strategy,
            actions=[
                Action(
                    type="hold_inflow",
                    entry=entry.name,
                    zone=entry.zone,
                    minutes=minutes,
                )
            ],
            why=(
                f"Temporarily holds arrivals at {entry.name} for "
                f"{minutes} minutes to reduce additional inflow."
            ),
        )

        _validate_plan(plan, selected_venue)
        fallback_plans.append(plan)

    return PlanCandidates(plans=fallback_plans), rejected

@router.post("", response_model=RecommendationResponse)
def recommend(body: RecommendationRequest):
    """Generate or rank candidates and return a recommendation only."""
    selected_venue = body.venue or active_venue
    generation_source = "user_supplied" if body.candidates is not None else "ai"

    try:
        if body.candidates is not None:
            candidates = body.candidates
        else:
            from pathlib import Path

            prompt_path = Path(__file__).parent / "prompts" / "planner.md"
            system_prompt = prompt_path.read_text(encoding="utf-8")

            context = {
                "venue": selected_venue.model_dump(by_alias=True),
                "initial_counts": current_initial_counts(),
                "forecast": make_forecast(
                    active_venue=selected_venue,
                    initial_counts=current_initial_counts(),
                    seed=42,
                ).model_dump(),
                "available_actions": [
                    "gate",
                    "hold_inflow",
                    "announce",
                    "move_officers",
                ],
            }

            candidates, generation_rejections = _generate_candidates(
                system_prompt=system_prompt,
                context=context,
                selected_venue=selected_venue,
            )
            if any(
                item.get("source") == "fallback"
                for item in generation_rejections
            ):
                generation_source = "fallback"

        if not candidates.plans:
            raise ValueError("No candidate plans were supplied.")

        baseline_forecast = make_forecast(
            active_venue=selected_venue,
            initial_counts=current_initial_counts(),
            seed=42,
        )
        baseline = score_forecast("baseline", baseline_forecast)


        scored = []
        rejected = []
        seen_plan_ids = set()

        for plan in candidates.plans:
            if plan.plan_id in seen_plan_ids:
                rejected.append({
                    "plan_id": plan.plan_id,
                    "reason": "Duplicate plan_id.",
                })
                continue

            seen_plan_ids.add(plan.plan_id)

            try:
                _validate_plan(plan, selected_venue)
                score = _score_plan(plan, selected_venue)
                scored.append((plan, score))
            except (ValueError, TypeError) as exc:
                rejected.append({
                    "plan_id": plan.plan_id,
                    "reason": str(exc),
                })

        if len(scored) < 3:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        f"Only {len(scored)} valid plans were generated; "
                        "three are required. Regenerate candidates with "
                        "distinct plan IDs and valid venue actions."
                    ),
                    "valid_candidates": len(scored),
                    "rejected_candidates": rejected,
                },
            )

        # Conservative ordering: minimize worst-zone danger probability first,
        # then prefer more time before danger is reached.
        scored.sort(
            key=lambda item: (
                item[1].max_p_danger,
                -(
                    item[1].min_minutes_to_danger
                    if item[1].min_minutes_to_danger is not None
                    else 1_000_000
                ),
            )
        )

        ranked = [
            RankedPlan(
                plan=plan,
                score=score,
                rank=index + 1,
                explanation=(
                    f"Maximum zone danger probability is "
                    f"{score.max_p_danger:.1%}."
                ),
            )
            for index, (plan, score) in enumerate(scored)
        ]

        return RecommendationResponse(
            baseline=baseline,
            recommended_plan_id=ranked[0].plan.plan_id,
            candidates_considered=len(ranked),
            recommendations=ranked,
            generation_source=generation_source,
        )

    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
