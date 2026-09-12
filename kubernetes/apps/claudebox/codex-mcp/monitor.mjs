#!/usr/bin/env node

import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const serverDirectory = path.dirname(fileURLToPath(import.meta.url));
const runsDirectory = path.resolve(process.env.CODEX_MCP_RUNS_DIR || path.join(serverDirectory, ".luna-runs"));
const once = process.argv.includes("--once") || !process.stdout.isTTY || !process.stdin.isTTY;
const noColor = process.argv.includes("--no-color") || !process.stdout.isTTY;
const selectedIndex = process.argv.indexOf("--run");
const requestedRun = selectedIndex >= 0 ? process.argv[selectedIndex + 1] : undefined;
const ACTIVE = new Set(["starting", "running"]);

let runs = [];
let selected = 0;
let view = requestedRun ? "detail" : "list";
let detailRunId = requestedRun;
let scrollOffset = 0;
let refreshTimer;
let rendering = false;
let closed = false;

const color = (code, text) => noColor ? String(text) : `\x1b[${code}m${text}\x1b[0m`;
const statusColor = status => {
  if (ACTIVE.has(status)) return color("33", status);
  if (status === "completed") return color("32", status);
  return color("31", status);
};
const width = () => Math.max(40, process.stdout.columns || 100);
const height = () => Math.max(12, process.stdout.rows || 30);

function truncate(value, limit) {
  const text = String(value ?? "").replaceAll(/\s+/g, " ");
  return text.length <= limit ? text : `${text.slice(0, Math.max(0, limit - 1))}…`;
}

function elapsed(run) {
  const end = run.finished_at ? Date.parse(run.finished_at) : Date.now();
  const seconds = Math.max(0, Math.floor((end - Date.parse(run.started_at)) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function shortPath(value, limit) {
  if (!value || value.length <= limit) return value || "";
  return `…${value.slice(-(limit - 1))}`;
}

async function loadRuns() {
  let names;
  try {
    names = await readdir(runsDirectory);
  } catch (error) {
    if (error.code === "ENOENT") return [];
    throw error;
  }
  const loaded = await Promise.all(names.filter(name => name.endsWith(".json")).map(async name => {
    try {
      return JSON.parse(await readFile(path.join(runsDirectory, name), "utf8"));
    } catch {
      return null;
    }
  }));
  const sorted = loaded.filter(Boolean).sort((a, b) => b.started_at.localeCompare(a.started_at));
  const active = sorted.filter(run => ACTIVE.has(run.status));
  const recentFinished = sorted.filter(run => !ACTIVE.has(run.status)).slice(0, 12);
  return [...active, ...recentFinished];
}

function wrapText(text, availableWidth, prefix = "") {
  const result = [];
  const safeWidth = Math.max(10, availableWidth - prefix.length);
  for (const originalLine of String(text ?? "").split("\n")) {
    let remaining = originalLine || " ";
    while (remaining.length > safeWidth) {
      let split = remaining.lastIndexOf(" ", safeWidth);
      if (split < Math.floor(safeWidth / 2)) split = safeWidth;
      result.push(`${prefix}${remaining.slice(0, split)}`);
      remaining = remaining.slice(split).trimStart();
    }
    result.push(`${prefix}${remaining}`);
  }
  return result;
}

function listScreen() {
  const terminalWidth = width();
  const lines = [
    `${color("1;36", "Codex Luna agents")}  ${color("2", new Date().toLocaleTimeString())}`,
    `${color("2", "↑/↓ select   Enter transcript   q quit")}  ${color("2", runsDirectory)}`,
    ""
  ];
  if (!runs.length) {
    lines.push("No Luna runs yet. Waiting for Claude Code to start one…");
    return lines;
  }
  const visibleRows = Math.max(1, height() - 5);
  const start = Math.max(0, Math.min(selected - Math.floor(visibleRows / 2), runs.length - visibleRows));
  const visible = runs.slice(start, start + visibleRows);
  for (let offset = 0; offset < visible.length; offset += 1) {
    const index = start + offset;
    const run = visible[offset];
    const pointer = index === selected ? color("1;36", "❯") : " ";
    const activeMark = ACTIVE.has(run.status) ? color("33", "●") : run.status === "completed" ? color("32", "✓") : color("31", "×");
    const meta = `${pointer} ${activeMark} ${run.run_id}  ${statusColor(run.status)}  ${elapsed(run)}  ${run.reasoning_effort}`;
    lines.push(meta);
    lines.push(`    ${truncate(run.prompt_preview, terminalWidth - 6)}`);
  }
  if (runs.length > visibleRows) lines.push(color("2", `  Showing ${start + 1}-${start + visible.length} of ${runs.length}`));
  return lines;
}

function eventLines(event, terminalWidth) {
  const at = event.at ? new Date(event.at).toLocaleTimeString() : "";
  const item = event.item || {};
  let label = event.type || "event";
  let body = "";
  let labelColor = "36";
  if (event.type === "thread.started") body = event.thread_id || "";
  else if (event.type === "turn.started") body = "Turn started";
  else if (event.type === "turn.completed") body = `Turn completed${event.usage ? ` · ${event.usage.input_tokens ?? "?"} in / ${event.usage.output_tokens ?? "?"} out` : ""}`;
  else if (event.type === "turn.failed") { body = event.error?.message || JSON.stringify(event.error || event); labelColor = "31"; }
  else if (event.type?.startsWith("item.")) {
    label = item.type || event.type;
    if (item.type === "agent_message") { body = item.text || ""; labelColor = "32"; }
    else if (item.type === "reasoning") { body = item.text || item.summary || ""; labelColor = "35"; }
    else if (item.type === "command_execution") {
      body = item.command || item.commands || "command";
      if (item.aggregated_output) body += `\n${item.aggregated_output}`;
      if (item.exit_code !== undefined) body += `\nexit ${item.exit_code}`;
      labelColor = "33";
    } else if (item.type === "file_change") {
      body = typeof item.changes === "string" ? item.changes : JSON.stringify(item.changes || item.path || item, null, 2);
      labelColor = "34";
    } else body = JSON.stringify(item, null, 2);
  } else body = JSON.stringify(event, null, 2);
  const prefix = `${color("2", at)} ${color(labelColor, label)}`;
  return [prefix, ...wrapText(body, terminalWidth, "  ")];
}

async function loadTranscript(run) {
  try {
    const content = await readFile(run.log_file, "utf8");
    return content.split("\n").filter(Boolean).map(line => {
      try { return JSON.parse(line); } catch { return { type: "raw", text: line }; }
    });
  } catch {
    return [];
  }
}

async function detailScreen(run) {
  if (!run) return [color("31", `Run not found: ${detailRunId}`), "", "Esc: back   q: quit"];
  const terminalWidth = width();
  const lines = [
    `${color("1;36", run.run_id)}  ${statusColor(run.status)}  ${elapsed(run)}  ${run.reasoning_effort}`,
    `${color("2", "Esc back   ↑/↓ scroll   PgUp/PgDn page   End follow   q quit")}`,
    `cwd:  ${shortPath(run.cwd, terminalWidth - 6)}`,
    `task: ${truncate(run.prompt_preview, terminalWidth - 6)}`,
    color("2", "─".repeat(Math.max(1, terminalWidth - 1)))
  ];
  const events = await loadTranscript(run);
  const transcript = events.flatMap(event => eventLines(event, terminalWidth));
  const available = Math.max(1, height() - lines.length - 1);
  const maxOffset = Math.max(0, transcript.length - available);
  scrollOffset = Math.min(scrollOffset, maxOffset);
  const end = transcript.length - scrollOffset;
  const start = Math.max(0, end - available);
  lines.push(...transcript.slice(start, end));
  if (!transcript.length) lines.push("Waiting for the first Codex event…");
  if (scrollOffset > 0) lines.push(color("33", `Paused ${scrollOffset} line${scrollOffset === 1 ? "" : "s"} from live output · End to follow`));
  return lines;
}

async function render() {
  if (rendering || closed) return;
  rendering = true;
  try {
    const previousId = runs[selected]?.run_id;
    runs = await loadRuns();
    if (previousId) {
      const newIndex = runs.findIndex(run => run.run_id === previousId);
      if (newIndex >= 0) selected = newIndex;
    }
    selected = Math.max(0, Math.min(selected, Math.max(0, runs.length - 1)));
    const detailRun = runs.find(run => run.run_id === detailRunId || run.run_id.startsWith(detailRunId || "__none__"));
    const lines = view === "detail" ? await detailScreen(detailRun) : listScreen();
    if (!once) process.stdout.write("\x1b[H\x1b[2J");
    process.stdout.write(`${lines.slice(0, height()).join("\n")}\n`);
  } finally {
    rendering = false;
  }
}

function close() {
  if (closed) return;
  closed = true;
  if (refreshTimer) clearInterval(refreshTimer);
  if (!once) {
    process.stdin.setRawMode(false);
    process.stdin.pause();
    process.stdout.write("\x1b[?25h\x1b[?1049l");
  }
}

function onKey(chunk) {
  const key = chunk.toString("utf8");
  if (key === "q" || key === "\u0003") {
    close();
    process.exit(0);
  }
  if (view === "list") {
    if (key.includes("\x1b[A") || key === "k") selected = Math.max(0, selected - 1);
    else if (key.includes("\x1b[B") || key === "j") selected = Math.min(Math.max(0, runs.length - 1), selected + 1);
    else if ((key === "\r" || key === "\n") && runs[selected]) {
      detailRunId = runs[selected].run_id;
      view = "detail";
      scrollOffset = 0;
    }
  } else {
    if (key === "\x1b") { view = "list"; scrollOffset = 0; }
    else if (key.includes("\x1b[A") || key === "k") scrollOffset += 1;
    else if (key.includes("\x1b[B") || key === "j") scrollOffset = Math.max(0, scrollOffset - 1);
    else if (key.includes("\x1b[5~")) scrollOffset += Math.max(1, height() - 8);
    else if (key.includes("\x1b[6~")) scrollOffset = Math.max(0, scrollOffset - Math.max(1, height() - 8));
    else if (key.includes("\x1b[F") || key.includes("\x1b[4~")) scrollOffset = 0;
  }
  void render();
}

if (once) {
  await render();
} else {
  process.stdout.write("\x1b[?1049h\x1b[?25l");
  process.stdin.setRawMode(true);
  process.stdin.resume();
  process.stdin.on("data", onKey);
  await render();
  refreshTimer = setInterval(() => void render(), 1_000);
  process.on("SIGINT", () => { close(); process.exit(0); });
  process.on("SIGTERM", () => { close(); process.exit(0); });
  process.on("exit", close);
}
