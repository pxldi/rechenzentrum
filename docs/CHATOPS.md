# ChatOps

A Telegram bot that can read the cluster, manage recipes and the calendar,
read and write the Obsidian vault, search documents and switch the lights,
built from seven pods in the `chatops` namespace:

```text
Telegram ──▶ zeroclaw ──▶ tandoor-mcp ──▶ tandoor (recipes, meal plan, shopping list)
              (agent)  ├▶ homelab-mcp ──▶ API server (read-only)
                       ├▶ calendar-mcp ─▶ nextcloud (CalDAV)
                       ├▶ vault-mcp ────▶ /data/vault ◀─ livesync-bridge ─▶ obsidian-sync (CouchDB)
                       ├▶ paperless-mcp ▶ paperless (documents)
                       ├▶ homeassistant-mcp ▶ home-assistant (states, switches)
                       └▶ files-mcp (sidecar) ▶ the workspace: what people send the bot
```

- **zeroclaw** is [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw), a
  Rust agent runtime, pinned by digest. It long-polls Telegram, so it needs no
  inbound route, and calls GPT-5.x through the Codex backend on the
  operator's ChatGPT subscription. It holds the Telegram token and its own
  Codex login and nothing else; it never sees a Tandoor token or a cluster
  credential.
- **tandoor-mcp**, **homelab-mcp**, **calendar-mcp**, **vault-mcp**,
  **paperless-mcp** and **homeassistant-mcp** are small Python MCP servers
  built from `images/homelab-mcp/` into one image (`immich_mcp` and
  `karakeep_mcp` are in the image too, built and then not wanted). Each holds the one credential
  its tools need. They speak Streamable HTTP on port 8000 and accept
  connections only from the zeroclaw pod (NetworkPolicy), which is why they
  carry no bearer token of their own.

## What the bot can do

| Server | Tools | Approval |
| --- | --- | --- |
| tandoor | `search_recipes`, `get_recipe`, `list_keywords`, `list_meal_types`, `list_meal_plan`, `leftovers`, `recipes_for_leftovers`, `log_cooked`, `list_shopping_list`, `preview_recipe_from_url` | runs on its own |
| tandoor | `create_recipe`, `update_recipe`, `add_meal_plan`, `set_pack_size`, `move_meal_plan`, `add_shopping_item`, `remove_shopping_item`, `import_recipe_from_url` | approve/deny keyboard in the chat first |
| calendar | `list_calendars`, `list_events`, `search_events` | runs on its own |
| calendar | `create_event`, `move_event`, `delete_event` | approve/deny keyboard in the chat first |
| vault | `list_notes`, `read_note`, `search_notes` (whole vault), `append_note`, `log_learned` (under `Clanky/` only) | runs on its own |
| vault | `write_note` (replaces a whole note, under `Clanky/` only) | approve/deny keyboard in the chat first |
| paperless | `search_documents`, `list_documents`, `get_document`, `get_document_page` (a page as a picture), `list_labels` | runs on its own |
| paperless | `update_document`, `create_tag` | approve/deny keyboard in the chat first |
| homeassistant | `who_is_home`, `list_entities`, `get_state` | runs on its own |
| homeassistant | `turn_on`, `turn_off` (light, switch, fan, input_boolean only) | approve/deny keyboard in the chat first |
| files | `list_received_files`, `read_pdf_text`, `render_page` | runs on its own |
| files | `send_to_paperless` | approve/deny keyboard in the chat first |
| homelab | `list_services`, `list_workloads`, `workload_status`, `pod_logs`, `events`, `flux_status`, `backups` | runs on its own |

`files-mcp` is a native sidecar in the ZeroClaw pod, on the same volume,
because Telegram attachments land in ZeroClaw's workspace and nowhere
else; it listens on the pod's loopback. The built-in `deliver_file` is on so a page picture from Paperless can be
sent into the chat; the only files in the workspace are what MCP tools
return. There is no restart, scale, reconcile or "run kubectl" tool, and the
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
| `VAULT_WRITE_ROOT` (`Clanky`) | vault-mcp | The one subfolder the write tools may touch. Reads cover the whole mirror; unset, every write is refused |
| `COUCHDB_USER`, `COUCHDB_PASSWORD`, `VAULT_PASSPHRASE` (in `secret-vault.yaml`) | vault-mcp pod (bridge) | The obsidian-sync admin, and the vault's LiveSync E2EE passphrase. The passphrase reads the whole vault; set it with `sops set` on the CLI, see the comment in the file |
| `PAPERLESS_TOKEN` (in `secret-paperless.yaml`) | paperless-mcp | `manage.py drf_create_token admin` in the paperless pod; revoke in the Django admin under Auth Tokens |
| `HASS_TOKEN` (in `secret-homeassistant.yaml`) | homeassistant-mcp | Home Assistant, user profile, Security, long-lived access token; set with `sops set`, see the comment in the file |
| `CALDAV_PASSWORD` (in `secret-caldav.yaml`) | calendar-mcp | A Nextcloud app password: `occ user:auth-tokens:add <user> --name clanky-calendar -n` in the nextcloud pod. Account-wide, not calendar-scoped; revoke under Settings, Security |

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

## The vault mirror

`vault-mcp` is a pod of two containers on one volume: [livesync-bridge]
(https://github.com/vrtmrz/livesync-bridge) (`images/livesync-bridge/`)
replicates the `second_brain` LiveSync database with `/data/vault` in both
directions, decrypting with the vault passphrase, and the MCP server reads
and writes that directory. A note the bot appends shows up in Obsidian
through the normal sync, and the vault keeps the history. The bridge config
(`vault/bridge-config.json`) carries placeholders that the pod's init
container fills from the Secret into memory. Deno's scan state is on the
volume under `bridge-state`; delete it to force a full rescan.

The claudebox pod runs a second bridge against the same database, into
`~/second_brain` on its own volume, so Claude Code sessions there see the
vault at the workstation's path. Two mirrors, one database; a note either
side writes reaches the other through CouchDB. See
`kubernetes/apps/claudebox/deployment.yaml`.

### The vault from claude.ai

A claude.ai custom connector can reach the same mirror. It runs as a third
container in the vault pod: the same `vault_mcp` module on port 8001, with
`OAUTH_ISSUER` set so every `/mcp` request needs an access token, and with
`VAULT_WRITE_ROOT=ops` so a chat can write project specs, tasks and ideas but
nothing else. The Clanky container keeps its own write root; the two never
share a port or a client.

claude.ai calls from Anthropic's servers, so the route is public: a Traefik
IngressRoute on `vault-mcp.<domain>` limited to Anthropic's egress range and
the house, forwarding to port 8001 only. The server is an OAuth resource
server (RFC 9728) and Authentik the authorization server. The client is
`authentik_provider_oauth2.vault_mcp` in `terraform/authentik/oidc-apps.tf`,
a public client with PKCE, so the pod holds no secret: it verifies tokens
against the provider's JWKS over the in-cluster Service, which is the one
egress rule the container adds. Only members of the `vault-mcp-users` group
pass the login. `images/homelab-mcp/src/oauth.py` has the four variables.

To connect: in claude.ai, Settings, Connectors, Add custom connector. URL
`https://vault-mcp.<domain>/mcp`, and under advanced settings the client id
from the tofu file with the secret left blank. The first tool call redirects
to the Authentik login. Voice mode calls the connector too (checked
2026-09-20), so a spoken question about a spec or a task gets answered from
the vault.

Shipping it is the two-PR rule below plus one step between: the code and
the tofu client merge first, the tofu apply on `main` creates the client,
and the manifests PR pins the new tag and adds the route.

## Scheduled nudges

Two agent cron jobs are declared in `config.toml` under `[cron.*]` and run
as the `haus` agent, in Europe/Berlin time:

| Job | When | What |
| --- | --- | --- |
| `planning_nudge` | 16:00 on Sunday, Tuesday and Thursday | If nothing is planned for today or tomorrow: two or three numbered recipe suggestions, leftovers first. A reply with the number plans it and puts the missing ingredients on the shopping list. |
| `evening_check` | 20:00 daily | If something is planned for today: "Hast du X gekocht?". "Ja" logs it and asks for a rating; "Nein" offers to move it to tomorrow. |

Both prompts answer `NO_REPLY` when there is nothing to say, which is the
one output the scheduler does not deliver (an empty answer would arrive as
"agent job executed"). The chat id they deliver to comes from the
`chatops-telegram-chat` Secret as an env override. `zeroclaw cron list` in
the pod shows the synced jobs; `zeroclaw cron run <id>` fires one by hand.

## Shipping a code change

The image tag is the commit that produced it (`sha-<commit>`), and the
workflow only pushes from `main`. So a change to `images/homelab-mcp/` is two
PRs: the code, then the tag bump once the build on `main` has published
it. The tag appears under `kubernetes/apps/chatops/` in every MCP container,
twice in the vault pod, and in ZeroClaw's `wait-for-mcp` init container,
which runs the same image and waits until the Services report its own build
(see `/health`). Bump them all with one `sed`; a lone bump leaves the init
container waiting two minutes and then starting the bot with a warning.
`ENABLE_IMAGE_PUBLISH` must be `true` in the repository variables or the
workflow does not run at all.

The masterplan says MCP software gets its own repository, like Schall. It is
in `images/` here for now because a new public repository is a decision, not
a side effect; `git subtree split -P images/homelab-mcp` extracts it when that
decision is made.

## Not in this cut

- Proactive messages about the cluster ("a backup failed"). Alertmanager
  already reaches the phone through Gotify; a second path needs a dedup
  story first. The two kitchen nudges below are the only scheduled messages.
- Any write to the cluster.
- A local model. Ollama on this node runs `qwen2.5:3b`, whose tool calling is
  not reliable enough to drive eight tools with an approval gate in between.
