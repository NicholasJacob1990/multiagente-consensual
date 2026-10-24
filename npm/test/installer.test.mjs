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

test("catálogo instalado resolve os dois plugins e distribui as skills jurídicas e PDF", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "multiagente catalogo "));
  try {
    const home = path.join(root, "home");
    const installRoot = path.join(root, "marketplace");
    const { spawnSync } = await import("node:child_process");
    const cli = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "cli.mjs");
    const run = spawnSync(process.execPath, [cli, "install", "--all", "--json", "--home", home,
      "--install-root", installRoot, "--skip-registries", "--skip-bridge"], { encoding: "utf8" });
    assert.equal(run.status, 0, run.stderr);
    for (const [file, format] of [[".claude-plugin/marketplace.json", "claude"],
      [".agents/plugins/marketplace.json", "codex"]]) {
      const market = JSON.parse(fs.readFileSync(path.join(installRoot, file), "utf8"));
      assert.deepEqual(market.plugins.map((p) => p.name), ["multiagente-consensual", "legal-br"]);
      for (const plugin of market.plugins) {
        const folder = path.resolve(installRoot, format === "claude" ? plugin.source : plugin.source.path);
        const metadata = JSON.parse(fs.readFileSync(path.join(folder, `.${format}-plugin/plugin.json`), "utf8"));
        assert.equal(metadata.name, plugin.name);
        const skills = fs.readdirSync(path.join(folder, "skills"));
        assert.equal(skills.length, plugin.name === "legal-br" ? 10 : 9);
      }
    }
    for (const name of ["minuta-juridica-fundamentada", "analise-juridica-epistemica",
      "auditoria-juridica-de-minutas", "pdf"]) {
      for (const surface of [[".codex"], [".claude"], [".cursor"], [".config", "opencode"], [".agents"]]) {
        assert.ok(fs.readFileSync(path.join(home, ...surface, "skills", name, "SKILL.md"), "utf8").startsWith("---"));
      }
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
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
  assert.equal(report.a2a.package, "@nicholasjacob90/a2a-mesh@1.4.3");
  assert.ok(report.actions.some((action) => action.binary.endsWith("npm") && action.argv.includes("@nicholasjacob90/a2a-mesh@1.4.3")));
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

test("instalação recusa manifesto Kimi inconsistente antes de tocar os destinos", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "multiagente-kimi-invalid-"));
  try {
    const source = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "..");
    const payload = path.join(root, "source");
    for (const relative of ["package.json", "npm/cli.mjs", ".claude-plugin/plugin.json",
      ".codex-plugin/plugin.json", "assets/multiagent-manifest.json", "scripts/manifest_lint.py"]) {
      const dest = path.join(payload, relative);
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.copyFileSync(path.join(source, relative), dest);
    }
    const manifestFile = path.join(payload, "assets", "multiagent-manifest.json");
    const manifest = JSON.parse(fs.readFileSync(manifestFile, "utf8"));
    manifest.seats.kimi.allowed_models = ["kimi-code/k3"];
    fs.writeFileSync(manifestFile, JSON.stringify(manifest));
    const home = path.join(root, "home");
    const installRoot = path.join(root, "marketplace");
    const { spawnSync } = await import("node:child_process");
    const result = spawnSync(process.execPath, [path.join(payload, "npm", "cli.mjs"), "install", "--all",
      "--home", home, "--install-root", installRoot, "--skip-registries", "--skip-bridge", "--json"], { encoding: "utf8" });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr + result.stdout, /Kimi/);
    // O Python da Apple pode criar Library/Caches no HOME temporário.
    for (const surface of [".agents", ".codex", ".claude", ".cursor", ".config", ".local", ".gemini"]) {
      assert.equal(fs.existsSync(path.join(home, surface)), false, surface);
    }
    assert.equal(fs.existsSync(installRoot), false);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("reinstalação limpa preserva extras no backup e sincroniza as seis CLIs", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "multiagente-clean-test-"));
  try {
    const source = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "..");
    const cli = path.join(source, "npm", "cli.mjs");
    const home = path.join(root, "home");
    const central = path.join(home, ".codex", "skills", "loop-debate-agentes");
    const claude = path.join(home, ".claude", "skills", "loop-debate-agentes");
    const cursor = path.join(home, ".cursor", "skills", "loop-debate-agentes");
    const unrelated = path.join(home, ".agents", "skills", "minha-skill", "SKILL.md");
    for (const dir of [central, claude, path.dirname(cursor), path.dirname(unrelated)]) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(path.join(central, "extensao-local.txt"), "preservar extensão");
    fs.writeFileSync(path.join(claude, "SKILL.md"), "cópia antiga");
    fs.symlinkSync(path.join(root, "destino-inexistente"), cursor);
    fs.writeFileSync(unrelated, "skill do usuário");
    const { spawnSync } = await import("node:child_process");
    const argv = [cli, "install", "--all", "--json", "--home", home,
      "--install-root", path.join(root, "marketplace"), "--skip-registries", "--skip-bridge"];
    const dry = spawnSync(process.execPath, [...argv, "--clean-managed", "--dry-run"], { encoding: "utf8" });
    assert.equal(dry.status, 0, dry.stderr);
    assert.equal(fs.readFileSync(path.join(central, "extensao-local.txt"), "utf8"), "preservar extensão");
    assert.equal(fs.readlinkSync(cursor), path.join(root, "destino-inexistente"));
    assert.equal(fs.existsSync(path.join(home, ".local", "state")), false);
    const additive = spawnSync(process.execPath, argv, { encoding: "utf8" });
    assert.equal(additive.status, 0, additive.stderr);
    assert.equal(fs.existsSync(path.join(central, "extensao-local.txt")), true);
    assert.equal(fs.readFileSync(path.join(claude, "SKILL.md"), "utf8"), "cópia antiga");
    const clean = spawnSync(process.execPath, [...argv, "--clean-managed"], { encoding: "utf8" });
    assert.equal(clean.status, 0, clean.stderr);
    const report = JSON.parse(clean.stdout);
    assert.equal(report.skillSyncMode, "replace-managed");
    const manifest = JSON.parse(fs.readFileSync(path.join(report.backup.path, "manifest.json"), "utf8"));
    const backed = (original) => path.join(report.backup.path, manifest.entries.find((entry) => entry.source === original).backup);
    assert.equal(fs.readFileSync(path.join(backed(central), "extensao-local.txt"), "utf8"), "preservar extensão");
    assert.equal(fs.readFileSync(path.join(backed(claude), "SKILL.md"), "utf8"), "cópia antiga");
    assert.equal(fs.lstatSync(backed(cursor)).isSymbolicLink(), true);
    assert.equal(fs.existsSync(path.join(central, "extensao-local.txt")), false);
    assert.equal(fs.readFileSync(unrelated, "utf8"), "skill do usuário");
    const tree = (directory) => {
      const result = {};
      function visit(current, relative = "") {
        for (const item of fs.readdirSync(current, { withFileTypes: true })) {
          if (["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store"].includes(item.name) || item.name.endsWith(".pyc")) continue;
          const rel = path.join(relative, item.name);
          if (item.isDirectory()) visit(path.join(current, item.name), rel);
          else result[rel] = fs.readFileSync(path.join(current, item.name)).toString("base64");
        }
      }
      visit(directory);
      return result;
    };
    for (const name of fs.readdirSync(path.join(source, "skills"))) {
      if (!fs.existsSync(path.join(source, "skills", name, "SKILL.md"))) continue;
      const expected = tree(path.join(source, "skills", name));
      for (const surface of [[".codex"], [".claude"], [".cursor"], [".config", "opencode"], [".agents"]]) {
        assert.deepEqual(tree(path.join(home, ...surface, "skills", name)), expected, `${surface.join("/")}/${name}`);
      }
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
