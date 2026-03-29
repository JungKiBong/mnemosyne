# Mories GitOps & HITL Integration Test Scenarios

## Overview
This document outlines the test cases designed to verify the Phase 3 (Automated GitOps Webhook) and Phase 5 (Manual Fallback) functionalities for the Mories Knowledge Graph Memory Control architecture.

## Scenarios

### Scenario 1: Create Staging Entities (Isolation Phase)
- **Objective:** Simulate an AI agent attempting to ingest new knowledge into the Mories system.
- **Action:** Inject 2 `(:StagingEntity)` nodes into the graph. They should NOT have the `(:Entity)` label, preventing them from being queried as active memory.
- **Expected Outcome:** 2 nodes created with the label `StagingEntity`.

### Scenario 2: Automated GitOps Promotion (Phase 3)
- **Objective:** Validate that a simulated GitHub Pull Request Merge event triggers the promotion of staging memories.
- **Action:** Execute `POST /api/gateway/github-merge` with a mockup payload containing `action: "closed"` and `merged: true`.
- **Expected Outcome:**
  - The API responds with success and counts the promoted entities.
  - The `StagingEntity` label is removed, and replaced with `Entity`.
  - A `MemoryRevision` node is created and attached via `HAS_REVISION`.

### Scenario 3: Manual Fallback Promotion (Phase 5)
- **Objective:** Verify the emergency override endpoint for when Git servers are down.
- **Action:** 
  - Inject 1 new `(:StagingEntity)` into the graph.
  - Execute `POST /api/gateway/staging/approve` passing the new node's ID.
- **Expected Outcome:**
  - The API processes the array of node IDs and promotes them.
  - A `MemoryRevision` node is generated with the reason "Manual Staging Approval".

### Scenario 4: Verify Audit Trail
- **Objective:** Ensure memory persistence securely tracks who and what modified the graph.
- **Action:** Query for `MemoryRevision` nodes.
- **Expected Outcome:** Revisions matching the GitOps PR reference and Manual Fallback exist and point to the newly promoted entities.
