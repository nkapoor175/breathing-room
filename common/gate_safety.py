from common.contracts import Plan, Venue

def validate_gate_safety(plan: Plan, venue: Venue) -> None:
    """Reject gate closures that disconnect zones from an existing outside route."""
    zone_ids = {zone.id for zone in venue.zones}
    links = venue.links

    # Find external endpoints, such as "outside".
    external_nodes = {
        endpoint
        for link in links
        for endpoint in (link.from_zone, link.to_zone)
        if endpoint not in zone_ids
    }

    if not external_nodes:
        return

    closed_by_plan = {
        action.link
        for action in plan.actions
        if action.type == "gate" and action.state == "closed"
    }

    def reachable_zone_ids(excluded_links: set[str]) -> set[str]:
        adjacency: dict[str, set[str]] = {}

        for link in links:
            if link.state != "open" or link.id in excluded_links:
                continue

            adjacency.setdefault(link.from_zone, set()).add(link.to_zone)
            adjacency.setdefault(link.to_zone, set()).add(link.from_zone)

        reached = set(external_nodes)
        pending = list(external_nodes)

        while pending:
            node = pending.pop()
            for neighbour in adjacency.get(node, set()):
                if neighbour not in reached:
                    reached.add(neighbour)
                    pending.append(neighbour)

        return reached & zone_ids

    baseline_reachable = reachable_zone_ids(set())
    planned_reachable = reachable_zone_ids(closed_by_plan)

    disconnected = baseline_reachable - planned_reachable

    if disconnected:
        raise ValueError(
            "Gate closure would disconnect these zones from an existing "
            f"outside route: {sorted(disconnected)}"
        )
