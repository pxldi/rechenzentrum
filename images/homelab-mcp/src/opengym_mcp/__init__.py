"""openGym as MCP tools: workouts set by set, history and progression per
exercise, routines, weigh-ins, and logging a workout or a weigh-in.

openGym has no API keys. The server holds a Bearer token from openGym's
device pairing flow (Settings, "Pair the mobile app", then POST
/api/pair/redeem), the way Snacky does. The token lasts 90 days; after that,
or after "sign out everywhere", every tool says to pair again.

openGym keeps a profile as one JSON document. Writes read it, change one
thing and send it back with the revision they read (PUT /api/data with
baseRev); openGym refuses a stale one with 409 and the current document, and
the change is made again on that. The phone merges what it pulls with its own
copy, so a workout logged here and one logged there both stay. Only workouts
logged here can be deleted here.

With OAUTH_ISSUER set every /mcp request needs an Authentik-issued bearer
token; that is how the copy claude.ai reaches runs. See oauth.py.
"""
