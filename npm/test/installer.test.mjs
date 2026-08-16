import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  A2A_PACKAGE,
  ALL_TARGETS,
  marketplaceDocuments,
  parseArgs,
  resolveTargets,
} from "../cli.mjs";

test("resolve --all para as seis CLIs canônicas", () => {
  const args = parseArgs(["install", "--all"]);
  assert.deepEqual(resolveTargets(args), [...ALL_TARGETS]);
});

test("aceita instalação individual e rejeita alvo desconhecido", () => {
  assert.deepEqual(resolveTargets(parseArgs(["install", "cursor"])), ["cursor"]);
  assert.throws(() => resolveTargets(parseArgs(["install", "inexistente"])), /alvo desconhecido/);
});

test("marketplaces apontam para o payload estável relativo", () => {
  const documents = marketplaceDocuments("1.2.3+codex.teste");
  assert.equal(documents.claude.name, "multiagente-npm");
  assert.equal(documents.claude.plugins[0].source, "./plugins/multiagente-consensual");
  assert.equal(documents.codex.plugins[0].source.path, "./plugins/multiagente-consensual");
  assert.equal(documents.codex.plugins[0].policy.authentication, "ON_USE");
});

test("dry-run isolado não cria arquivos", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "multiagente-npm-test-"));
  const home = path.join(root, "home");
  const installRoot = path.join(root, "marketplace");
  const { spawnSync } = await import("node:child_process");
  const cli = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "cli.mjs");
  const result = spawnSync(
    process.execPath,
    [cli, "install", "cursor", "--dry-run", "--json", "--home", home, "--install-root", installRoot, "--skip-registries", "--skip-bridge"],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout).simulation, true);
  assert.equal(fs.existsSync(home), false);
  assert.equal(fs.existsSync(installRoot), false);
  fs.rmSync(root, { recursive: true, force: true });
});

test("--with-a2a planeja o pacote complementar sem escrever no dry-run", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "multiagente-a2a-test-"));
  const home = path.join(root, "home");
  const installRoot = path.join(root, "marketplace");
  const { spawnSync } = await import("node:child_process");
  const cli = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "cli.mjs");
  const result = spawnSync(
    process.execPath,
    [cli, "install", "--all", "--with-a2a", "--dry-run", "--json", "--home", home, "--install-root", installRoot, "--skip-registries", "--skip-bridge"],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.a2a.status, "installed");
  assert.equal(report.a2a.package, "@nicholasjacob90/a2a-mesh@1.4.0");
  assert.ok(report.actions.some((action) => action.binary.endsWith("npm") && action.argv.includes("@nicholasjacob90/a2a-mesh@1.4.0")));
  assert.equal(fs.existsSync(home), false);
  fs.rmSync(root, { recursive: true, force: true });
});

test("pin do instalador coincide com a versão local do pacote A2A", async () => {
  const packageFile = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "..", "packages", "a2a-mesh", "package.json");
  const packageDocument = JSON.parse(fs.readFileSync(packageFile, "utf8"));
  assert.equal(A2A_PACKAGE, `@nicholasjacob90/a2a-mesh@${packageDocument.version}`);
});

test("upgrade atualiza todas as superfícies e também o A2A quando solicitado", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "multiagente-upgrade-test-"));
  const home = path.join(root, "home");
  const installRoot = path.join(root, "marketplace");
  const { spawnSync } = await import("node:child_process");
  const cli = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "cli.mjs");
  const result = spawnSync(
    process.execPath,
    [cli, "upgrade", "--all", "--with-a2a", "--dry-run", "--json", "--home", home, "--install-root", installRoot, "--skip-registries", "--skip-bridge"],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.command, "upgrade");
  assert.deepEqual(report.targets, [...ALL_TARGETS]);
  assert.equal(report.a2a.package, A2A_PACKAGE);
  assert.equal(report.simulation, true);
  assert.equal(fs.existsSync(home), false);
  fs.rmSync(root, { recursive: true, force: true });
});
