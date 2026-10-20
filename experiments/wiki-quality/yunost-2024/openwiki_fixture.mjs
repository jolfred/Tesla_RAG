/** Verify the upstream raw reader and prompts with all outbound fetches denied.
 * Usage: node openwiki_fixture.mjs <built upstream directory> <new empty fixture home>
 * No model client/agent is created. Fixture text is synthetic, not study evidence.
 */
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [vendor, home] = process.argv.slice(2).map(x => path.resolve(x));
if (!vendor || !home) throw new Error("Expected vendor and empty home");
await fs.mkdir(home, { recursive: false });
process.env.OPENWIKI_CONFIG_DIR = home;
process.env.OPENWIKI_PROVIDER = "openai-compatible";
process.env.OPENWIKI_MODEL_ID = "gpt-6-luna";
process.env.OPENWIKI_REASONING_EFFORT = "medium";
process.env.OPENWIKI_OPENAI_COMPATIBLE_USE_RESPONSES_API = "true";
process.env.OPENWIKI_OPENAI_COMPATIBLE_REASONING_EFFORT_SUPPORTED = "true";
globalThis.fetch = async () => { throw new Error("Network is forbidden in this fixture"); };

const { createOpenWikiConnectorTools } = await import(pathToFileURL(path.join(vendor, "dist/connectors/tools.js")));
const { createSystemPrompt, createUserPrompt } = await import(pathToFileURL(path.join(vendor, "dist/agent/prompt.js")));
const { resolveReasoningConfig } = await import(pathToFileURL(path.join(vendor, "dist/config/reasoning.js")));
const tools = createOpenWikiConnectorTools("local-wiki");
const read = tools.find(x => x.name === "openwiki_read_raw_item");
assert.ok(read);
const raw = path.join(home, "connectors/custom-mcp/raw/2024-01");
await fs.mkdir(raw, { recursive: true });
const body = JSON.stringify({ post_id: "wall-1_1", text_raw: "SYNTHETIC JANUARY EVIDENCE" }) + "\n";
await fs.writeFile(path.join(raw, "posts.jsonl"), body);
const result = await read.invoke({ connectorId: "custom-mcp", path: "2024-01/posts.jsonl", maxBytes: 500000 });
assert.ok(JSON.stringify(result).includes("SYNTHETIC JANUARY EVIDENCE"));
await assert.rejects(() => read.invoke({ connectorId: "custom-mcp", path: "2024-02/posts.jsonl" }), /ENOENT/);
await fs.writeFile(path.join(home, "connectors/outside.json"), "MUST NOT BE READ");
await assert.rejects(() => read.invoke({ connectorId: "custom-mcp", path: "../../outside.json" }), /stay inside/);
for (const command of ["init", "update"]) {
  const system = createSystemPrompt(command, "local-wiki", "ru");
  assert.ok(system.includes("raw data paths are supplied"));
  await fs.writeFile(path.join(home, `${command}-system.md`), system);
  const user = createUserPrompt(command, { lastUpdate: null },
    JSON.stringify({ source_specific_connector_raw_data: { connectorId: "custom-mcp", path: "2024-01/posts.jsonl" } }), "local-wiki", path.join(home, "wiki"));
  assert.ok(user.includes("2024-01/posts.jsonl"));
  await fs.writeFile(path.join(home, `${command}-user.md`), user);
}
assert.deepEqual(resolveReasoningConfig("openai-compatible", "gpt-6-luna"),
  { effort: "medium", transport: "responses-reasoning" });
await fs.writeFile(path.join(home, "fixture-report.json"), JSON.stringify({
  status: "passed", llm_calls: 0, network: "denied", raw_reader: "native custom-mcp",
  model_id: "gpt-6-luna", reasoning_effort: "medium", transport: "responses",
  limitation: "This tests raw reading and prompt composition, not paid agent generation or OS isolation."
}, null, 2));
console.log(JSON.stringify({ status: "passed", llm_calls: 0, home }));
