# ChatOps

A Telegram bot that can read the cluster and manage recipes, built from three
pods in the `chatops` namespace:

```text
Telegram ──▶ zeroclaw ──▶ tandoor-mcp ──▶ tandoor (recipes, meal plan)
              (agent)  └▶ homelab-mcp ──▶ API server (read-only)
```

- **zeroclaw** is [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw), a
  Rust agent runtime, pinned by digest. It long-polls Telegram, so it needs no
  inbound route, and calls GPT-5.x through the Codex backend on the
  operator's ChatGPT subscription. It holds the Telegram token and its own
  Codex login and nothing else; it never sees a Tandoor token or a cluster
  credential.
- **tandoor-mcp** and **homelab-mcp** are two small Python MCP servers built
  from `images/homelab-mcp/` into one image. Each holds the one credential
  its tools need. They speak Streamable HTTP on port 8000 and accept
  connections only from the zeroclaw pod (NetworkPolicy), which is why they
  carry no bearer token of their own.

## What the bot can do

| Server | Tools | Approval |
| --- | --- | --- |
| tandoor | `search_recipes`, `get_recipe`, `list_keywords`, `list_meal_types`, `list_meal_plan`, `leftovers`, `recipes_for_leftovers` | runs on its own |
| tandoor | `create_recipe`, `update_recipe`, `add_meal_plan`, `set_pack_size` | approve/deny keyboard in the chat first |
| homelab | `list_services`, `list_workloads`, `workload_status`, `pod_logs`, `events`, `flux_status`, `backups` | runs on its own |

There is no restart, scale, reconcile or "run kubectl" tool, and the
homelab ServiceAccount cannot read Secrets or ConfigMaps. The masterplan's
"later allowlisted actions" are still later. The agent's built-in shell, file,
HTTP and browser tools are switched off by `risk_profiles.haus.allowed_tools`.

## Configuration

Everything non-secret is in `kubernetes/apps/chatops/zeroclaw/config.toml`
(validated with `zeroclaw doctor` in the pinned image before it was
committed), with the persona in `SOUL.md` and the operating rules in
`AGENTS.md` beside it. The three land in one generated ConfigMap, so editing
any of them rolls the pod.

Secrets are the sops file `kubernetes/apps/chatops/secret.yaml` and reach
ZeroClaw as environment variables in its schema-mirror grammar
(`ZEROCLAW_<path with __ separators>`):

| Key | Used by | Where to get it |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | zeroclaw | @BotFather, `/newbot` |
| `TELEGRAM_PEERS` | zeroclaw | A JSON list of numeric Telegram user ids, e.g. `'["123456789"]'`. Message the bot once with the placeholder in place and it replies with your id |
| `TANDOOR_TOKEN` | tandoor-mcp | Tandoor, Settings, API, new token with scope `read write` |

The peer list is non-empty on purpose: with it set, ZeroClaw never issues a
one-time `/bind` code, and never tries to write the paired id into a
`config.toml` that is mounted read-only.

The model login is not in the Secret. ZeroClaw keeps it as an encrypted
auth profile on the `zeroclaw-data` PVC, next to the `.secret_key` that
decrypts it, and refreshes it there. Create it once after the first deploy:

```sh
kubectl -n chatops exec -it deploy/zeroclaw -- \
  zeroclaw auth login --model-provider openai-codex --device-code
kubectl -n chatops exec deploy/zeroclaw -- zeroclaw auth status
kubectl -n chatops rollout restart deploy/zeroclaw
```

Open the printed URL, sign in with the ChatGPT account and enter the code.
This is a login of its own, not an import of claudebox's `~/.codex`: Codex
refresh tokens rotate and allow one owner, so two consumers of one login log
each other out. The profile does not survive losing the PVC; log in again.
Usage draws on the plan's included Codex allowance, which ZeroClaw cannot
see; it records these calls at $0, so `[cost]` does not cap them.

Spend on metered providers is capped in `[cost]` (daily and monthly, USD). ZeroClaw's own memory
lives on the `zeroclaw-data` PVC, so what the bot is told to remember survives
a restart; the pod is `Recreate` because of it.

## Shipping a code change

The image tag is the commit that produced it (`sha-<commit>`), and the
workflow only pushes from `main`. So a change to `images/homelab-mcp/` is two
PRs: the code, then the tag bump in the two Deployments once the build on
`main` has published it. `ENABLE_IMAGE_PUBLISH` must be `true` in the
repository variables or the workflow does not run at all.

The masterplan says MCP software gets its own repository, like Schall. It is
in `images/` here for now because a new public repository is a decision, not
a side effect; `git subtree split -P images/homelab-mcp` extracts it when that
decision is made.

## Not in this cut

- Proactive messages ("a backup failed") on a schedule. Alertmanager already
  reaches the phone through Gotify; a second path needs a dedup story first.
- Any write to the cluster.
- A local model. Ollama on this node runs `qwen2.5:3b`, whose tool calling is
  not reliable enough to drive eight tools with an approval gate in between.
