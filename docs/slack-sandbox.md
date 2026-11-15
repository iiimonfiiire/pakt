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

The simulator matches Slack on these points:

- Bearer auth and scopes.
- `{"ok": false, "error": ...}` error bodies.
- Newest-first history with cursor pagination.
- Threads with `reply_count`.
- Form or JSON request bodies.

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

1. Create a free Slack workspace for testing. Add a Slack app with these bot scopes:
   - `channels:history`, `channels:read`, `channels:manage`, and `channels:join`
   - `chat:write`, `chat:write.customize`, and `chat:write.public`
   - `reactions:write` and `users:read`
2. Install the app, then set these in `.env`:

   ```text
   SLACK_API_BASE=https://slack.com/api
   SLACK_BOT_TOKEN=<the bot token>
   ```

3. Seed it with the same fixture:

   ```bash
   pakt-sandbox slack seed
   ```

   The seeder creates missing channels and posts every fixture message through the Web API. With `chat:write.customize`, each message shows its fixture author's name. Run the seeder once, because it does not deduplicate messages.

To let the coworker bots chat in the real workspace, see [Coworker bots in real Slack](#coworker-bots-in-real-slack).

Never point a connector at a workspace that holds real company data.

## Test against it

`evals/tests/test_slack_sim.py` starts the simulator on a free port and shows the pattern. Use `serve("127.0.0.1", 0)` in a thread, read the port from `server.server_address`, and call the API.

## Coworker bots

Four AI coworkers chat in the simulator: a product manager, an engineer, a support agent, and a technical writer. Each posts as its own user with its own token.

They read recent channel history, then reply or start threads. A bot may answer `PASS` to stay quiet. Their chatter gives a connector live, messy content to read.

1. Start the simulator and open `http://127.0.0.1:8765/` to watch the feed.
2. Run the office in a second terminal:

   ```bash
   pakt-sandbox slack office --interval 5
   ```

   Add `--turns 20` to stop after 20 turns. Press Ctrl-C to stop otherwise.

### Choose a model

The bots call an [Ollama](https://ollama.com) server. Any pulled model works.

```bash
pakt-sandbox slack office --model llama3.2:1b --ollama http://127.0.0.1:11434
```

You can also set `OLLAMA_MODEL` and `OLLAMA_BASE`.

A remote or home server that runs Ollama is fine. Ollama listens on localhost only by default, so tunnel to it:

```bash
ssh -N -L 11434:127.0.0.1:11434 <user>@<server>
```

Small models on a CPU-only machine answer in several seconds. Use the 1B model for lively chat. Use the 3B model for better replies at a slower pace. A failed or slow turn is logged, and the next turn runs.

Each turn sends channel text to the model server. Use a server you control.

### Coworker bots in real Slack

A real Slack app has one bot token. Add `--single-token` and every coworker posts through it, each under its own display name, such as "Riley (PM)".

```bash
pakt-sandbox slack office --single-token --interval 30
```

The command reads `SLACK_API_BASE` and `SLACK_BOT_TOKEN` from a `.env` file in the current directory. Variables already set in your shell take priority.

Notes:

- The bots join channels they are not in, and they start conversations in empty channels.
- The coworkers share one bot identity. Slack shows the custom names with an APP tag.
- Slack limits posts to about one per second per channel. A 30-second interval stays far below it.
- The simulator's feed page does not apply here. Slack is the viewer.
