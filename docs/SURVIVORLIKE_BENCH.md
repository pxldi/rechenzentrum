# Survivorlike benches on the node

Long headless Godot jobs for the survivorlike game (balance benches, later
autopilot training) run in namespace `survivorlike-bench`, so they stop taking
RAM on the desktop. The jobs only measure. They never change the game's numbers.

Pieces:

- `images/survivorlike-bench`: Ubuntu 26.04, Godot 4.7.2, python3 with numpy,
  git. `bench-job` is the entrypoint.
- `kubernetes/apps/survivorlike-bench/bench.yaml`: a suspended CronJob that
  serves as the Job template, the results volume, a reader pod to copy results
  from, a quota of one bench at a time, and egress to GitHub on 443.
- `scripts/survivorlike-bench`: start, watch, list, fetch and stop runs from the
  desktop with kubectl.

## What a run does

1. Fetches the game at the given ref, shallow, with a read-only deploy key
   (`game-deploy-key`, SOPS) over `ssh.github.com:443`. The ref must be pushed.
2. Runs `godot --headless --path game --import` (under a minute in the local test).
3. Checks that the native library loaded (`HordeSim`, `ChipSim`). Without it
   Godot runs the horde in GDScript, slower and without an error, so the run
   stops instead.
4. Works the queue with the game's own `tools/night_bench.py --no-wait`.

## Queue

The format is `night_bench.py`'s, the same as the desktop's night queue:

```json
[
  {"name": "essences",
   "cmd": ["tools/weapon_bench.py", "--weapons", "staff", "--stages", "5",
           "--essence", "all", "--start", "360", "--seconds", "150",
           "--seeds", "7,11,23", "--sure", "--jobs", "4"]},
  {"name": "bosses",
   "cmd": ["tools/run_bench.py", "--seeds", "7,11", "--extra=--focus_boss",
           "-j", "4", "--out", "{out}/bosses"]}
]
```

- Every entry must set `--jobs` (`-j` for `run_bench.py`) to 1 to 4. The run
  refuses the queue otherwise. The scripts' default reads free memory and CPU
  count from `/proc`, which in a pod describe the whole node and would start
  more runs than the pod's 6 GiB hold.
- `{out}` in any argument becomes the run's results folder, for scripts with
  their own `--out` (`run_bench.py`, `pilot_train.py`).
- `"mem"` is ignored here; the pod's limits replace `heavy`.

## Start, watch, fetch

```bash
scripts/survivorlike-bench start main queue.json
```

```bash
scripts/survivorlike-bench logs bench-1109-2010-main
```

```bash
scripts/survivorlike-bench fetch bench-1109-2010-main
```

`start` prints the run's name. `start <ref> <queue> <name>` picks the name
yourself. `UNTIL=07:30 scripts/survivorlike-bench start ...` stops the queue
at that Berlin time; otherwise the Job stops after 24 hours at the latest.
`fetch` copies to `~/bench_results/survivorlike/rechenzentrum/<name>`. `list`
shows every run on the volume, `status` the Jobs, pods and quota, `stop`
deletes a Job (its results stay), `delete` removes a run's results.

A run's folder holds `job.log`, `queue.json`, `import.log`,
`native_check.log`, `run.json` (ref, commit, start, end, exit code) and
night_bench's `<date>/<name>.md`, `.json`, `.err` and `summary.md`.

Results stay on the volume (20 GiB) until `delete` removes them. They are not
in Velero's backups: they can be rerun and are fetched to the desktop.

## Size and limits

Measured on 2026-11-09: the node has 11 cores and 28 GiB for pods. Over seven
days CPU was 1.6 cores busy at the 95th percentile. Available memory was 9 to
10 GiB from 5 Nov on, and fell to 2 GiB on 3 to 5 Nov, while the GTNH server
still ran. There is no swap.

So one bench pod runs four Godot runs: CPU request 2 and limit 4, memory
request 4 GiB and limit 6 GiB. A local test with four runs peaked at 4.7 GB.
The pod runs in `rechenzentrum-bulk`, the lowest priority class. Its memory
request is below its use on purpose: under memory pressure the kubelet and
the kernel then pick it first, before any house service. A bench that is
evicted is started again; there is nothing to debug.

A ResourceQuota allows one bench pod at a time. A second `start` creates its
Job, and its pod starts when the first run ends.

## Autopilot training

`tools/pilot_train.py` (branch `rl-pilot`) needs only numpy, which the image
has. Push the branch, then queue it like a bench:

```json
[{"name": "pilot", "cmd": ["tools/pilot_train.py", "--generations", "20",
  "--jobs", "4", "--out", "{out}/pilot"]}]
```

A queue stops within 24 hours, since `night_bench.py --until` is a time of
day. A longer training continues in a new run with `pilot_train.py --resume`.
