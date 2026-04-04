def update_harness(
    self,
    harness_uuid: str,
    updates: dict
) -> dict:
    """Update harness details directly."""
    from datetime import datetime, timezone
    import json
    now = datetime.now(timezone.utc).isoformat()
    with self._driver.session() as session:
        existing = session.run("""
            MATCH (e:Entity {uuid: $uuid, memory_category: 'harness'})
            RETURN e.uuid AS uuid, e.attributes_json AS meta_json
        """, uuid=harness_uuid).single()
        if not existing:
            return {"error": f"Harness {harness_uuid} not found"}
            
        meta = self._safe_json_load(existing["meta_json"])
        
        # Apply updates mapping
        if "description" in updates:
            meta["harness"]["description"] = updates["description"]
        if "domain" in updates:
            meta["harness"]["domain"] = updates["domain"]
        if "trigger" in updates:
            meta["harness"]["trigger"] = updates["trigger"]
        if "process_type" in updates:
            meta["harness"]["process_type"] = updates["process_type"]
        if "tags" in updates:
            meta["harness"]["tags"] = updates["tags"]
        if "scope" in updates:
            meta["harness"]["scope"] = updates["scope"]
        if "tool_chain" in updates:
            meta["harness"]["tool_chain"] = updates["tool_chain"]
        if "data_flow" in updates:
            meta["harness"]["data_flow"] = updates["data_flow"]
        if "conditionals" in updates:
            meta["harness"]["conditionals"] = updates["conditionals"]
            
        session.run("""
            MATCH (e:Entity {uuid: $uuid})
            SET e.attributes_json = $meta_json,
                e.description = $desc,
                e.last_accessed = $now
        """, uuid=harness_uuid,
            meta_json=json.dumps(meta, ensure_ascii=False),
            desc=updates.get("description", meta["harness"].get("description", "")),
            now=now)
            
    return {"status": "updated", "uuid": harness_uuid}
