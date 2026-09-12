#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createWriteStream } from "node:fs";
import { access, mkdir, stat, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import path from "node:path";

const SERVER_NAME = "codex-luna-mcp";
const SERVER_VERSION = "0.1.0";
const MODEL = "gpt-5.6-luna";
const MAX_PROMPT_CHARS = 200_000;
const MAX_CAPTURE_CHARS = 2_000_000;
const activeRequests = new Map();
const serverDirectory = path.dirname(fileURLToPath(import.meta.url));
const runsDirectory = path.resolve(process.env.CODEX_MCP_RUNS_DIR || path.join(serverDirectory, ".luna-runs"));

const effortValues = ["none", "low", "medium", "high", "xhigh", "max"];
const sandboxValues = ["read-only", "workspace-write"];

const commonProperties = {
  prompt: {
    type: "string",
    minLength: 1,
    maxLength: MAX_PROMPT_CHARS,
    description: "A complete, self-contained task for the Luna coding agent."
  },
  cwd: {
    type: "string",
    description: "Working directory for the agent. Defaults to the MCP server's configured working directory."
  },
  reasoning_effort: {
    type: "string",
    enum: effortValues,
    default: "medium",
    description: "Luna reasoning effort."
  },
  sandbox: {
    type: "string",
    enum: sandboxValues,
    default: "workspace-write",
    description: "Filesystem access granted to the agent."
  },
  timeout_seconds: {
    type: "integer",
    minimum: 10,
    maximum: 3600,
    default: 900,
    description: "Maximum runtime before the agent is stopped."
  }
};

export const tools = [
  {
    name: "run_luna_agent",
    description: "Run one autonomous Codex coding subagent using GPT-5.6 Luna and return its final answer and usage metadata.",
    inputSchema: {
      type: "object",
      properties: commonProperties,
      required: ["prompt"],
      additionalProperties: false
    },
    annotations: {
      title: "Run Luna agent",
      readOnlyHint: false,
      destructiveHint: false,
      openWorldHint: true
    }
  },
  {
    name: "run_luna_agents",
    description: "Run up to eight independent GPT-5.6 Luna coding subagents, with bounded parallelism, and return all results in input order.",
    inputSchema: {
      type: "object",
      properties: {
        tasks: {
          type: "array",
          minItems: 1,
          maxItems: 8,
          items: {
            type: "object",
            properties: {
              prompt: commonProperties.prompt,
              cwd: commonProperties.cwd
            },
            required: ["prompt"],
            additionalProperties: false
          }
        },
        reasoning_effort: commonProperties.reasoning_effort,
        sandbox: commonProperties.sandbox,
        timeout_seconds: commonProperties.timeout_seconds,
        max_parallel: {
          type: "integer",
          minimum: 1,
          maximum: 4,
          default: 4,
          description: "Maximum number of agents running at once."
        }
      },
      required: ["tasks"],
      additionalProperties: false
    },
    annotations: {
      title: "Run Luna agents in parallel",
      readOnlyHint: false,
      destructiveHint: false,
      openWorldHint: true
    }
  }
];

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function rpcError(id, code, message, data) {
  send({ jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) } });
}

function assertObject(value, name) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${name} must be an object`);
  }
}

export function validateOptions(args) {
  assertObject(args, "arguments");
  if (typeof args.prompt !== "string" || args.prompt.trim() === "") {
    throw new Error("prompt must be a non-empty string");
  }
  if (args.prompt.length > MAX_PROMPT_CHARS) {
    throw new Error(`prompt exceeds ${MAX_PROMPT_CHARS} characters`);
  }
  if (args.cwd !== undefined && (typeof args.cwd !== "string" || args.cwd.trim() === "")) {
    throw new Error("cwd must be a non-empty string when provided");
  }
  const reasoningEffort = args.reasoning_effort ?? "medium";
  const sandbox = args.sandbox ?? "workspace-write";
  const timeoutSeconds = args.timeout_seconds ?? 900;
  if (!effortValues.includes(reasoningEffort)) {
    throw new Error(`reasoning_effort must be one of: ${effortValues.join(", ")}`);
  }
  if (!sandboxValues.includes(sandbox)) {
    throw new Error(`sandbox must be one of: ${sandboxValues.join(", ")}`);
  }
  if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 10 || timeoutSeconds > 3600) {
    throw new Error("timeout_seconds must be an integer from 10 to 3600");
  }
  return { reasoningEffort, sandbox, timeoutSeconds };
}

async function resolveCwd(input) {
  const base = process.env.CODEX_MCP_DEFAULT_CWD || process.cwd();
  const resolved = path.resolve(input || base);
  await access(resolved);
  const details = await stat(resolved);
  if (!details.isDirectory()) throw new Error(`cwd is not a directory: ${resolved}`);
  return resolved;
}

function appendLimited(current, addition) {
  if (current.length >= MAX_CAPTURE_CHARS) return current;
  return current + addition.slice(0, MAX_CAPTURE_CHARS - current.length);
}

function truncate(value, limit = 500) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length <= limit ? text : `${text.slice(0, limit - 1)}…`;
}

function summarizeEvent(event) {
  if (event.type === "thread.started") return `thread ${event.thread_id || "started"}`;
  if (event.type === "turn.started") return "turn started";
  if (event.type === "turn.completed") return "turn completed";
  if (event.type === "turn.failed") return truncate(event.error?.message || event.error || "turn failed");
  if (event.type === "item.started" || event.type === "item.completed" || event.type === "item.updated") {
    const item = event.item || {};
    if (item.type === "agent_message") return truncate(item.text || "agent message");
    if (item.type === "reasoning") return truncate(item.text || item.summary || "reasoning");
    if (item.type === "command_execution") {
      const command = item.command || item.commands || "command";
      const suffix = item.exit_code === undefined ? "" : ` (exit ${item.exit_code})`;
      return `${truncate(command)}${suffix}`;
    }
    if (item.type === "file_change") return truncate(item.changes || item.path || "file change");
    return truncate(item.type || item);
  }
  return truncate(event.type || event);
}

async function createRunMonitor({ prompt, cwd, reasoningEffort, sandbox }) {
  await mkdir(runsDirectory, { recursive: true });
  const runId = `${new Date().toISOString().replaceAll(/[-:.TZ]/g, "").slice(0, 14)}-${randomUUID().slice(0, 8)}`;
  const statusPath = path.join(runsDirectory, `${runId}.json`);
  const logPath = path.join(runsDirectory, `${runId}.jsonl`);
  const log = createWriteStream(logPath, { flags: "a" });
  log.on("error", () => {});
  const status = {
    run_id: runId,
    status: "starting",
    model: MODEL,
    cwd,
    reasoning_effort: reasoningEffort,
    sandbox,
    prompt_preview: truncate(prompt.replaceAll(/\s+/g, " ").trim(), 300),
    started_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    event_count: 0,
    recent_events: [],
    log_file: logPath
  };
  let writes = Promise.resolve();
  function save() {
    status.updated_at = new Date().toISOString();
    const snapshot = `${JSON.stringify(status, null, 2)}\n`;
    writes = writes.then(() => writeFile(statusPath, snapshot)).catch(() => {});
    return writes;
  }
  function record(event) {
    const at = new Date().toISOString();
    log.write(`${JSON.stringify({ at, ...event })}\n`);
    status.status = status.status === "starting" ? "running" : status.status;
    status.event_count += 1;
    if (event.type === "thread.started" && event.thread_id) status.thread_id = event.thread_id;
    if (event.usage) status.usage = event.usage;
    status.recent_events.push({ at, type: event.type || "event", summary: summarizeEvent(event) });
    status.recent_events = status.recent_events.slice(-8);
    void save();
  }
  async function finish(finalStatus, details = {}) {
    Object.assign(status, details, { status: finalStatus, finished_at: new Date().toISOString() });
    await save();
    await new Promise(resolve => log.end(resolve));
  }
  await save();
  return { runId, statusPath, logPath, status, record, finish };
}

export function parseCodexEvent(event, state) {
  state.events += 1;
  if (event.type === "thread.started" && typeof event.thread_id === "string") {
    state.threadId = event.thread_id;
  }
  if (event.type === "item.completed" && event.item?.type === "agent_message" && typeof event.item.text === "string") {
    state.finalText = event.item.text;
  }
  if (event.type === "turn.completed" && event.usage) state.usage = event.usage;
  if (event.type === "turn.failed") state.failure = event.error || event;
}

export function buildCodexArgs({ cwd, reasoningEffort, sandbox }) {
  const args = [
    "exec",
    "--json",
    "--color", "never",
    "--ephemeral",
    "--skip-git-repo-check",
    "--model", MODEL,
    "--cd", cwd,
    "--config", `model_reasoning_effort=\"${reasoningEffort}\"`,
  ];
  if (sandbox === "workspace-write") {
    args.push("--approve-for-me");
  } else {
    args.push("--sandbox", "read-only");
  }
  args.push("-");
  return args;
}

export async function runAgent(rawArgs, signal) {
  const { reasoningEffort, sandbox, timeoutSeconds } = validateOptions(rawArgs);
  const cwd = await resolveCwd(rawArgs.cwd);
  const codexBin = process.env.CODEX_MCP_CODEX_BIN || "codex";
  const childArgs = buildCodexArgs({ cwd, reasoningEffort, sandbox });
  const monitor = await createRunMonitor({ prompt: rawArgs.prompt, cwd, reasoningEffort, sandbox });

  const startedAt = Date.now();
  const state = { events: 0, finalText: "", threadId: undefined, usage: undefined, failure: undefined };
  let stderr = "";
  let nonJsonOutput = "";
  let stdoutBuffer = "";
  let timedOut = false;

  let child;
  try {
    child = spawn(codexBin, childArgs, {
      cwd,
      env: process.env,
      stdio: ["pipe", "pipe", "pipe"],
      signal
    });
  } catch (error) {
    await monitor.finish(signal?.aborted ? "cancelled" : "failed", { error: truncate(error.message) });
    throw error;
  }

  const timer = setTimeout(() => {
    timedOut = true;
    child.kill("SIGTERM");
    setTimeout(() => child.kill("SIGKILL"), 5_000).unref();
  }, timeoutSeconds * 1_000);
  timer.unref();

  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdin.on("error", () => {});
  child.stdout.on("data", chunk => {
    stdoutBuffer += chunk;
    const lines = stdoutBuffer.split("\n");
    stdoutBuffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const event = JSON.parse(line);
        parseCodexEvent(event, state);
        monitor.record(event);
      } catch {
        nonJsonOutput = appendLimited(nonJsonOutput, `${line}\n`);
      }
    }
  });
  child.stderr.on("data", chunk => {
    stderr = appendLimited(stderr, chunk);
  });

  child.stdin.end(rawArgs.prompt);

  let outcome;
  try {
    outcome = await new Promise((resolve, reject) => {
      child.once("error", reject);
      child.once("close", (code, closeSignal) => resolve({ code, closeSignal }));
    });
  } catch (error) {
    await monitor.finish(signal?.aborted ? "cancelled" : "failed", {
      duration_ms: Date.now() - startedAt,
      error: truncate(error.message)
    });
    throw error;
  } finally {
    clearTimeout(timer);
  }

  if (stdoutBuffer.trim()) {
    try {
      const event = JSON.parse(stdoutBuffer);
      parseCodexEvent(event, state);
      monitor.record(event);
    } catch {
      nonJsonOutput = appendLimited(nonJsonOutput, stdoutBuffer);
    }
  }

  const result = {
    ok: outcome.code === 0 && !timedOut && !state.failure,
    run_id: monitor.runId,
    status_file: monitor.statusPath,
    log_file: monitor.logPath,
    model: MODEL,
    cwd,
    reasoning_effort: reasoningEffort,
    sandbox,
    duration_ms: Date.now() - startedAt,
    exit_code: outcome.code,
    ...(outcome.closeSignal ? { signal: outcome.closeSignal } : {}),
    ...(state.threadId ? { thread_id: state.threadId } : {}),
    ...(state.usage ? { usage: state.usage } : {}),
    ...(timedOut ? { timed_out: true } : {}),
    ...(state.failure ? { failure: state.failure } : {}),
    output: state.finalText || nonJsonOutput.trim()
  };
  if (!result.ok && stderr.trim()) result.stderr = stderr.trim();
  if (!result.ok && !result.output) result.output = "Codex exited without a final agent message.";
  const finalStatus = timedOut ? "timed_out" : signal?.aborted ? "cancelled" : result.ok ? "completed" : "failed";
  await monitor.finish(finalStatus, {
    duration_ms: result.duration_ms,
    exit_code: result.exit_code,
    ...(result.usage ? { usage: result.usage } : {}),
    ...(result.output ? { final_output_preview: truncate(result.output, 500) } : {}),
    ...(result.stderr ? { error: truncate(result.stderr, 500) } : {})
  });
  return result;
}

async function runBatch(args, signal) {
  assertObject(args, "arguments");
  if (!Array.isArray(args.tasks) || args.tasks.length < 1 || args.tasks.length > 8) {
    throw new Error("tasks must contain between 1 and 8 items");
  }
  const maxParallel = args.max_parallel ?? 4;
  if (!Number.isInteger(maxParallel) || maxParallel < 1 || maxParallel > 4) {
    throw new Error("max_parallel must be an integer from 1 to 4");
  }
  const shared = {
    reasoning_effort: args.reasoning_effort,
    sandbox: args.sandbox,
    timeout_seconds: args.timeout_seconds
  };
  const results = new Array(args.tasks.length);
  let cursor = 0;
  async function worker() {
    while (cursor < args.tasks.length) {
      const index = cursor++;
      assertObject(args.tasks[index], `tasks[${index}]`);
      try {
        results[index] = await runAgent({ ...shared, ...args.tasks[index] }, signal);
      } catch (error) {
        results[index] = { ok: false, model: MODEL, output: error.message };
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(maxParallel, args.tasks.length) }, worker));
  return results;
}

function asToolResult(value) {
  const failed = Array.isArray(value) ? value.some(item => !item.ok) : !value.ok;
  const text = Array.isArray(value)
    ? value.map((item, index) => `## Agent ${index + 1}\n\n${item.output}`).join("\n\n")
    : value.output;
  return {
    content: [{ type: "text", text }],
    structuredContent: Array.isArray(value) ? { results: value } : value,
    ...(failed ? { isError: true } : {})
  };
}

async function handleRequest(message) {
  const { id, method, params } = message;
  if (method === "initialize") {
    send({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: params?.protocolVersion || "2025-06-18",
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
        instructions: "Use run_luna_agent for one task or run_luna_agents for independent parallel tasks. Each agent uses GPT-5.6 Luna."
      }
    });
    return;
  }
  if (method === "ping") {
    send({ jsonrpc: "2.0", id, result: {} });
    return;
  }
  if (method === "tools/list") {
    send({ jsonrpc: "2.0", id, result: { tools } });
    return;
  }
  if (method === "tools/call") {
    const controller = new AbortController();
    activeRequests.set(id, controller);
    try {
      let value;
      if (params?.name === "run_luna_agent") {
        value = await runAgent(params.arguments || {}, controller.signal);
      } else if (params?.name === "run_luna_agents") {
        value = await runBatch(params.arguments || {}, controller.signal);
      } else {
        rpcError(id, -32602, `Unknown tool: ${params?.name || "(missing)"}`);
        return;
      }
      send({ jsonrpc: "2.0", id, result: asToolResult(value) });
    } catch (error) {
      const messageText = error.name === "AbortError" ? "Luna agent run was cancelled." : error.message;
      send({ jsonrpc: "2.0", id, result: asToolResult({ ok: false, model: MODEL, output: messageText }) });
    } finally {
      activeRequests.delete(id);
    }
    return;
  }
  rpcError(id, -32601, `Method not found: ${method}`);
}

let inputBuffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => {
  inputBuffer += chunk;
  const lines = inputBuffer.split("\n");
  inputBuffer = lines.pop() || "";
  for (const line of lines) {
    if (!line.trim()) continue;
    let message;
    try {
      message = JSON.parse(line);
    } catch (error) {
      rpcError(null, -32700, "Parse error", error.message);
      continue;
    }
    if (message.method === "notifications/cancelled") {
      activeRequests.get(message.params?.requestId)?.abort();
      continue;
    }
    if (message.id === undefined) continue;
    handleRequest(message).catch(error => rpcError(message.id, -32603, "Internal error", error.message));
  }
});

process.stdin.on("end", () => {
  for (const controller of activeRequests.values()) controller.abort();
});
process.stdin.resume();

process.on("SIGTERM", () => {
  for (const controller of activeRequests.values()) controller.abort();
  process.exit(0);
});
