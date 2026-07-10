def validate_schedule(plan: dict):
    # Validate the structure of the elevation schedule in the plan
    schedule = plan.get("elevation_schedule", [])
    valid_schedule = []
    for item in schedule:
        step_id = item.get("step_id")
        declared_tier = item.get("declared_tier", 0)
        declared_effects = item.get("declared_effects", {})
        valid_schedule.append({
            "step_id": step_id,
            "declared_tier": declared_tier,
            "declared_effects": declared_effects
        })
    return valid_schedule
