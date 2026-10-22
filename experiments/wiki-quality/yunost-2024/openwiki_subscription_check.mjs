/** Native OpenWiki subscription worker; synthetic check by default.
 * Credentials are read from the local Codex login into memory, never copied
 * to an OpenWiki env file or logs. Only the subscription endpoint is allowed.
 * Usage: node openwiki_subscription_check.mjs <vendor> <new private output> <python>
 * Explicit study mode adds <previous-output-or-dash> <frozen-job-config.json>.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../..");
const [vendorArg, outputArg, python, previousArg, studySpecArg] = process.argv.slice(2);
const continueFromArg = previousArg === "-" ? undefined : previousArg;
const study = studySpecArg ? JSON.parse(await fs.readFile(studySpecArg, "utf8")) : null;
if (study) {
  assert.match(study.month, /^2024-(0[1-9]|1[0-2])$/u);
  assert.match(study.snapshot_id, /^[a-f0-9]{20}$/u);
  assert.equal(Boolean(continueFromArg), study.month !== "2024-01");
}
assert.ok(vendorArg && outputArg && python, "Expected vendor, new output, Python executable");
const vendor = path.resolve(vendorArg), output = path.resolve(outputArg);
const privateRoot = path.join(root, "storage/experiments/yunost-2024");
const rel = path.relative(privateRoot, output);
assert.ok(rel && !rel.startsWith("..") && !path.isAbsolute(rel), "Use a new private study directory");
await fs.mkdir(output, { recursive: false });
const home = path.join(output, "home");
if (continueFromArg) {
  const previous = path.resolve(continueFromArg);
  const previousRel = path.relative(privateRoot, previous);
  assert.ok(previousRel && !previousRel.startsWith("..") && !path.isAbsolute(previousRel));
  const previousReport = JSON.parse(await fs.readFile(path.join(previous, "report.json"), "utf8"));
  assert.ok(["passed", "completed", "completed_needs_artifact_verification"].includes(previousReport.status));
  if (study) assert.equal(previousReport.snapshot_id, study.snapshot_id);
  if (study) assert.equal(previousReport.month, `2024-${String(Number(study.month.slice(-2)) - 1).padStart(2, "0")}`);
  await fs.cp(path.join(previous, "home"), home, { recursive: true, errorOnExist: true });
} else {
  await fs.mkdir(home);
}
Object.assign(process.env, {
  OPENWIKI_CONFIG_DIR: home,
  OPENWIKI_PROVIDER: "openai-chatgpt", OPENWIKI_MODEL_ID: "gpt-6-luna",
  OPENWIKI_REASONING_EFFORT: "medium", OPENWIKI_PAGE_CONCURRENCY: "1",
  OPENWIKI_PROVIDER_RETRY_ATTEMPTS: "1", LANGSMITH_TRACING: "false",
  LANGCHAIN_TRACING_V2: "false", LANGFUSE_ENABLED: "0",
});
// Prevent accidental use of unrelated configured paid credentials.
for (const key of Object.keys(process.env)) {
  if (/(API_KEY|PROXYAPI|OPENROUTER|LANGSMITH_API|LANGFUSE_SECRET)/u.test(key)) delete process.env[key];
}
const load = p => import(pathToFileURL(path.join(vendor, "dist", p)));
const { resolveReasoningConfig } = await load("config/reasoning.js");
assert.deepEqual(resolveReasoningConfig("openai-chatgpt", "gpt-6-luna"),
  { effort: "medium", transport: "responses-reasoning" });
const { codexTokensToEnv } = await load("agent/openai-chatgpt-oauth.js");
const auth = JSON.parse(await fs.readFile(path.join(process.env.CODEX_HOME || path.join(os.homedir(), ".codex"), "auth.json"), "utf8"));
assert.equal(auth.auth_mode, "chatgpt", "A ChatGPT subscription login is required");
const t = auth.tokens;
const claims = JSON.parse(Buffer.from(t.access_token.split(".")[1], "base64url").toString("utf8"));
const expiresAtMs = Number(claims.exp) * 1000;
assert.ok(expiresAtMs > Date.now() + 10 * 60 * 1000, "Refresh the Codex login before this check");
Object.assign(process.env, codexTokensToEnv({ access: t.access_token, refresh: t.refresh_token,
  accountId: t.account_id, expiresAtMs, email: null, planType: null }));

const originalFetch = globalThis.fetch;
let calls = 0;
const started = Date.now();
const attempts = [];
let quotaStop = null;
globalThis.fetch = async (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input));
  assert.equal(url.origin, "https://chatgpt.com", "Non-subscription endpoint blocked");
  assert.equal(url.pathname, "/backend-api/codex/responses", "Only Codex generation is allowed");
  if (calls >= (study ? 500 : 24)) throw new Error("Per-job request ceiling reached");
  let limits;
  try {
    limits = JSON.parse(execFileSync(python, [path.join(here, "codex_subscription.py")],
      { encoding: "utf8", timeout: 45000, windowsHide: true }));
  } catch {
    quotaStop = { reason: "actual_quota_unavailable", checked_at_utc: new Date().toISOString() };
  }
  if (quotaStop || !limits.eligible) {
    quotaStop ??= { reason: "remaining_10_percent_or_less", ...limits };
    await fs.writeFile(path.join(output, "quota-stop.json"), JSON.stringify(quotaStop, null, 2));
    throw new Error("Actual subscription quota does not permit another call");
  }
  const body = JSON.parse(init?.body);
  assert.equal(body.model, "gpt-6-luna");
  assert.equal(body.reasoning?.effort, "medium");
  assert.equal(body.store, false);
  calls++;
  const prefix = path.join(output, `call-${String(calls).padStart(3, "0")}`);
  await fs.writeFile(prefix + "-request.json", JSON.stringify(body, null, 2));
  await fs.writeFile(prefix + "-quota.json", JSON.stringify(limits, null, 2));
  const timeout = study ? 900000 : 120000;
  const response = await originalFetch(input, { ...init,
    signal: init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(timeout)]) : AbortSignal.timeout(timeout) });
  const record = { call: calls, http_status: response.status };
  attempts.push(record);
  // Never persist request headers: they contain the account credential.
  const capture = response.clone().text().then(text => fs.writeFile(prefix + "-response.txt", text));
  attempts.at(-1).capture = capture;
  return response;
};

const month = study?.month ?? (continueFromArg ? "2024-02" : "2024-01");
const command = continueFromArg ? "update" : "init";
const raw = path.join(home, "connectors/custom-mcp/raw", month);
await fs.mkdir(raw, { recursive: true });
const evidence = continueFromArg
  ? { post_id: "synthetic-2", published_at: "2024-02-10T12:00:00Z",
      text_raw: "10 февраля 2024 года вымышленный отряд «Проба» провёл учебную встречу «Февральский флаг»." }
  : { post_id: "synthetic-1", published_at: "2024-01-05T12:00:00Z",
      text_raw: "5 января 2024 года вымышленный отряд «Проба» провёл учебную встречу «Январский маяк»." };
let taskMessage = JSON.stringify({ source_specific_connector_raw_data: {
  connectorId: "custom-mcp", path: `${month}/posts.jsonl` } });
if (study) {
  const bytes = await fs.readFile(study.batch_file);
  assert.equal(createHash("sha256").update(bytes).digest("hex"), study.batch_sha256);
  const task = await fs.readFile(study.task_file);
  assert.equal(createHash("sha256").update(task).digest("hex"), study.task_sha256);
  taskMessage = task.toString("utf8");
  assert.equal(JSON.parse(taskMessage).source_specific_connector_raw_data.path, `${month}/posts.jsonl`);
  await fs.writeFile(path.join(raw, "posts.jsonl"), bytes);
  await fs.writeFile(path.join(output, "job-config.json"), JSON.stringify(study, null, 2));
} else {
  await fs.writeFile(path.join(raw, "posts.jsonl"), JSON.stringify(evidence) + "\n");
}
const events = path.join(output, "events.jsonl");
const { runOpenWikiAgent } = await load("agent/index.js");
let status = "failed", errorType = null;
try {
  const result = await runOpenWikiAgent(command, path.join(home, "wiki"), {
    outputMode: "local-wiki", modelId: "gpt-6-luna", language: "ru",
    userMessage: taskMessage,
    onEvent(event) { appendFileSync(events, JSON.stringify(event) + "\n", "utf8"); },
  });
  await fs.writeFile(path.join(output, "native-result.json"), JSON.stringify(result, null, 2));
  const pages = (await fs.readdir(path.join(home, "wiki"), { recursive: true }))
    .filter(name => name.endsWith(".md"));
  const text = (await Promise.all(pages.map(name => fs.readFile(path.join(home, "wiki", name), "utf8")))).join("\n");
  if (!study) {
    assert.ok(text.includes("Январский маяк"), "The first synthetic fact must remain in Wiki");
    if (continueFromArg) assert.ok(text.includes("Февральский флаг"), "The new synthetic fact must appear in Wiki");
  }
  // Authentication must remain in memory, including when upstream saves state.
  for (const entry of await fs.readdir(home, { recursive: true, withFileTypes: true })) {
    if (!entry.isFile()) continue;
    const bytes = await fs.readFile(path.join(entry.parentPath, entry.name));
    for (const secret of [t.access_token, t.refresh_token, t.id_token]) {
      if (secret) assert.ok(!bytes.includes(Buffer.from(secret)), "Credential persisted by upstream");
    }
  }
  status = study ? "completed" : "passed";
} catch (error) {
  errorType = error.constructor.name;
  let diagnostic = String(error.stack || errorType);
  for (let cause = error.cause, depth = 0; cause && depth < 8; cause = cause.cause, depth++) {
    diagnostic += `\nCaused by: ${cause.constructor?.name ?? "Error"}: ${cause.message ?? ""} ${cause.code ?? ""}`;
  }
  for (const secret of [t.access_token, t.refresh_token, t.id_token, t.account_id]) {
    if (secret) diagnostic = diagnostic.replaceAll(secret, "[redacted]");
  }
  diagnostic = diagnostic.replace(/Bearer\s+\S+/giu, "Bearer [redacted]");
  if (quotaStop) status = "quota_blocked";
  await fs.writeFile(path.join(output, "error-redacted.txt"), diagnostic);
} finally {
  await Promise.allSettled(attempts.map(x => x.capture));
  const report = { status, error_type: errorType, model: "gpt-6-luna", effort: "medium",
    transport: "openwiki_native_openai_chatgpt", subscription: true, paid_api_allowed: false,
    study_data_used: Boolean(study), arm: "openwiki", snapshot_id: study?.snapshot_id ?? null,
    command, month, request_ceiling: study ? 500 : 24,
    old_fact_retention_checked: status === "passed" && Boolean(continueFromArg),
    calls, attempts: attempts.map(({ call, http_status }) => ({ call, http_status })),
    wall_seconds: (Date.now() - started) / 1000, upstream_commit: "6c14bff27830034bfd70c15bde46825d7686ec60",
    compatibility_patch: "openwiki-luna-compat.patch", credentials_persisted_by_launcher: false };
  await fs.writeFile(path.join(output, "report.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
  process.exitCode = ["failed", "quota_blocked"].includes(status) ? 1 : 0;
}
