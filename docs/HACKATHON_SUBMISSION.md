# Hackathon submission checklist

Track: **New Slack Agent** · [Slack Agent Builder Challenge 2026](https://slackhack.devpost.com)

## Before you submit (manual — ~2 hours)

### 1. Reinstall the Slack app after manifest changes

The manifest now includes `im:history` and `message.im` for Assistant-first demos.

```bash
# At api.slack.com → your app → App Manifest → paste manifest.json → Save → Reinstall
```

### 2. Enable demo mode in production sandbox

```bash
# .env
DEMO_MODE=true
```

This forces predictable fixture evidence for `checkout-service`, `payment-service`, and `auth-service` so live GitHub/Datadog cannot break demo scenarios.

### 3. Record the demo video (~3 minutes)

**Primary path (show Assistant + RTS):**

1. Open **Incident Commander** in the Slack Assistant panel (not slash command first).
2. Click suggested prompt **Redis pool exhaustion** or type `checkout-service latency spike`.
3. Narrate: loading status → MCP GitHub evidence → **Real-Time Search** prior incidents.
4. Show RCA card in `#incidents` with confidence breakdown → Approve.
5. Repeat in Assistant: **Flaky test false alarm** → show blocked before human review.

**Fallback path:** `/incident checkout-service latency spike` if Assistant is unavailable.

Upload to YouTube or Loom. Paste the link in `readme.md` and Devpost.

### 4. Judge sandbox access

- [ ] Create or use a dedicated workspace URL (not localhost).
- [ ] Invite `slackhack@salesforce.com` and `testing@devpost.com`.
- [ ] Bot invited to `#incidents`.
- [ ] Seed 1–2 prior incident messages in `#incidents` mentioning `SCRUM-1` for RTS/history demos.
- [ ] Update `readme.md` sandbox URL placeholder.
- [ ] Deploy app (Railway/Fly/Docker) or keep Socket Mode running during judging window.

### 5. Devpost submission

Copy the pitch from `readme.md` → **Hackathon Submission → Devpost pitch**.

Highlight all three required technologies:

| Technology | What to show judges |
|------------|---------------------|
| **Slack AI / Assistant** | Assistant panel, suggested prompts, `set_status` loading |
| **Real-Time Search** | Logs: `rts_search_completed source=assistant.search.context` |
| **MCP** | Logs: GitHub commits via `mcp/github_server.py`; mention in video |

### 6. Optional polish

- [ ] Export architecture diagram PNG for Devpost gallery.
- [ ] Set `LOG_LEVEL=info` (not debug) in sandbox.
- [ ] Confirm `slack_socket_ready` in logs before live demo.

## What we fixed in code (gap closure)

| Gap | Fix |
|-----|-----|
| Slash-first demo | Bolt `Assistant` middleware — `handlers/assistant.py` |
| RTS not exercised | `action_token` passed from Assistant → `assistant.search.context` |
| Agent Builder alignment | Same pattern as [bolt-python-assistant-template](https://github.com/slack-samples/bolt-python-assistant-template) — see `docs/AGENT_BUILDER.md` |
| Demo reliability | `DEMO_MODE=true` uses fixtures only for known services |
| Submission ops | This checklist + updated README demo script |

## Verification commands

```bash
pytest tests/test_incident_parse.py tests/test_collector.py tests/test_rts.py -v
curl http://localhost:8000/health
# Look for: db, socket_mode connected, then trigger Assistant demo
```
