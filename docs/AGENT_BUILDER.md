# Slack Agent Builder alignment

This project follows the official **Bolt Python Assistant** pattern recommended for Slack Agent Builder / Agents & AI Apps, aligned with:

- [Using the Assistant class (Bolt Python)](https://docs.slack.dev/tools/bolt-python/concepts/assistant)
- [slack-samples/bolt-python-assistant-template](https://github.com/slack-samples/bolt-python-assistant-template)

## How we map to Agent Builder concepts

| Slack Agent Builder concept | Our implementation |
|---------------------------|-------------------|
| Assistant surface | `manifest.json` → `assistant_view` + `assistant:write` |
| Suggested prompts | `manifest.json` → `suggested_prompts` (natural language, no slash prefix) |
| Thread lifecycle | `slack/handlers/assistant.py` → `Assistant.thread_started` |
| User messages | `Assistant.user_message` → parses `checkout-service latency spike` |
| Loading status | `set_status()` during investigation |
| RTS action token | Cached on thread start; passed to `assistant.search.context` |
| MCP tools | `mcp/github_server.py` — FastMCP stdio server for commits |

## Entry points

1. **Assistant (primary — hackathon demo):** Open Incident Commander in the Slack Assistant panel → pick a prompt or type `service description`.
2. **Slash command (fallback):** `/incident checkout-service latency spike`
3. **PagerDuty webhook:** `POST /webhooks/pagerduty`

## `slack create agent` vs this repo

The hackathon promotes `slack create agent` templates for HR/IT/Sales. This repo is a **custom Bolt + LangGraph agent** built for incident RCA — functionally equivalent to Agent Builder output but with:

- LangGraph investigation pipeline
- Multi-stage eval engine
- MCP + RTS + external integrations

If judges ask: *"We used the Bolt `Assistant` middleware and manifest scopes from Slack's assistant template, extended with domain-specific investigation logic."*

## Required manifest scopes (post-fix)

```json
"assistant:write",
"search:read.public",
"im:history"
```

Bot events: `assistant_thread_started`, `assistant_thread_context_changed`, `message.im`

After updating `manifest.json`, **reinstall the app** in your workspace.

## Demo mode

Set `DEMO_MODE=true` in `.env` so the three hackathon services use fixture evidence exclusively — prevents live APIs from breaking scripted outcomes.
