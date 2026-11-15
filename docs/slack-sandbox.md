# Slack sandbox

A simulated Slack workspace for building and testing PAKT connectors without a live workspace. It has two targets that speak the same Slack Web API, so connector code does not change between them.

| Target | Use it for |
|---|---|
| Local simulator | Development and CI. Offline, free, deterministic. |
| Real sandbox workspace | Final checks against real Slack behavior. |

## Run the simulator

```bash
pip install -e ".[dev]"
pakt-sandbox slack serve
```

The simulator listens on `http://127.0.0.1:8765/api`. Set these in your connector's `.env`:

```text
SLACK_API_BASE=http://127.0.0.1:8765/api
SLACK_BOT_TOKEN=xoxb-sim-bot
```

`xoxb-sim-readonly` has no `chat:write` scope. Use it to test scope errors.

## Seed data

The fixture, `pakt_sandbox/slack_sim/fixtures/workspace.json`, has four channels, five users, and threads of realistic, rule-breaking content:

- `#releases` – a messy announcement and a draft changelog with a thread.
- `#support-answers` – an answer that needs a KB article, and an engineer correcting a fact.
- `#docs-feedback` – reader feedback and a blaming error message.
- `#general` – empty, for connector output.

The simulator loads the fixture on start. Edit the fixture to stage your own scenarios.

## Supported methods

`auth.test`, `conversations.list`, `conversations.info`, `conversations.history`, `conversations.replies`, `conversations.create`, `users.list`, `users.info`, `chat.postMessage`, `chat.update`, and `reactions.add`.

The simulator matches Slack on these points: bearer auth, scopes, `{"ok": false, "error": ...}` bodies, newest-first history, cursor pagination, threads with `reply_count`, and form or JSON request bodies.

It does not cover Events API delivery, file uploads, Block Kit validation, or OAuth.

## Inject faults

Admin endpoints live under `/_sim/` and exist only in the simulator.

```bash
# Rate-limit the next two history calls, with Retry-After: 5
curl -X POST localhost:8765/_sim/fault -d '{"method":"conversations.history","mode":"rate_limit","count":2,"retry_after":5}'

# Return 500 on the next call to any method
curl -X POST localhost:8765/_sim/fault -d '{"mode":"server_error"}'

# List every call received, or restore the fixture
curl -X POST localhost:8765/_sim/calls
curl -X POST localhost:8765/_sim/reset
```

## Use a real sandbox workspace

1. Create a free Slack workspace for testing, and a Slack app with the bot scopes `channels:history`, `channels:read`, `channels:manage`, `chat:write`, `reactions:write`, and `users:read`.
2. Install the app, then set `SLACK_API_BASE=https://slack.com/api` and `SLACK_BOT_TOKEN` to the bot token in `.env`.
3. Seed it with the same fixture:

   ```bash
   pakt-sandbox slack seed
   ```

   The seeder creates missing channels and posts every fixture message through the Web API. Run it once, because it does not deduplicate messages.

Never point a connector at a workspace that holds real company data.

## Test against it

`evals/tests/test_slack_sim.py` starts the simulator on a free port and shows the pattern. Use `serve("127.0.0.1", 0)` in a thread, read the port from `server.server_address`, and call the API.
