# Harness Operations Guide: Monitoring Evolutionary Process Patterns

## 1. Overview
The Mories Memory System automatically extracts and analyzes "Harness Process Patterns" from agents' execution logs. This documentation focuses specifically on monitoring orchestration flow and managing failure recoveries through Retry, Fallback, and Handoff mechanisms.

## 2. Extraction Mechanism
The `extract_harness_from_log` algorithm analyzes execution flows to identify orchestration structures:
- **Tool Chain**: The sequence of tools used by an agent.
- **Data Flow**: The input, intermediate outputs, and final results.
- **Conditionals**: The logical decision-making paths, especially around failure or uncertain situations.

## 3. Monitoring Conditionals (Retry / Fallback / Handoff)

The Harness UI (`dashboard/harness.html`) distinguishes execution failures and orchestration recoveries into three main categories. Operators should regularly monitor these conditional outcomes to evaluate agent robustness.

### A. 🔄 RETRY (재시도)
- **Condition:** Tool execution fails due to temporary issues (e.g., timeout, rate limits, lock).
- **Execution Strategy:** The agent immediately retries the action or waits briefly before retrying identical parameters or slight variations.
- **Operator Action:** High frequency of `RETRY` flags indicates a flaky external API or excessive concurrent load. Consider adjusting the Circuit Breaker Threshold or tweaking concurrency settings.

### B. ⚠️ FALLBACK (대체)
- **Condition:** Tool execution definitively fails, or the intended data isn't retrieved successfully.
- **Execution Strategy:** The agent chooses a different tool, changes the methodology entirely, or switches to a cache/alternative data source.
- **Operator Action:** If an agent consistently relies on `FALLBACK`, it means the primary path is broken. Investigate the primary tool's availability or the specific parameters the agent generates.

### C. 🤝 HANDOFF (역할 전환/이관)
- **Condition:** An agent lacks permissions, capabilities, or knowledge to complete a task.
- **Execution Strategy:** The agent transfers context to another specialized agent or escalates the task.
- **Operator Action:** Check the accuracy of the agent profiles and scopes. Frequent `HANDOFF` across non-related teams implies inefficient workflow routing or missing tool provisions.

## 4. MCP Tools for Harness
Through `mcp_server/mories_mcp.py`, tools can proactively log logic transitions or report detailed stat telemetry. Developers can implement dedicated MCP tools (e.g., `get-harness-stats`, `record-harness-pattern`) allowing external operators to track and analyze these orchestration metrics directly via API.

## 5. Automation & Recovery Capabilities (Version 2)
To maximize intelligence and self-healing:
- **AI Recommendation (`recommend_harness`)**: Retrieves the most relevant harness patterns from the knowledge graph based on natural language queries, keyword matching, and execution success rates.
- **Manual Rollback (`rollback_harness`)**: Identifies structural degradation in a pattern (e.g., lower success rate after evolution) and restores its `tool_chain` back to a previously known working state via the evolution history.

The Dashboard `harness.html` provides a direct UI for these capabilities.

## 6. Summary
Monitoring the evolutionary history, analyzing conditionals, and utilizing recommendations/rollbacks are essential for maintaining the operational reliability of the AI systems utilizing the Mories framework.
