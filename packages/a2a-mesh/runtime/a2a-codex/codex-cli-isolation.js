import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const DEFAULT_SKILL_ROOTS = [
  path.join(os.homedir(), '.codex', 'skills'),
  path.join(os.homedir(), '.agents', 'skills'),
];

export function prepareCodexRuntimeHome({
  runtimeHome = process.env.A2A_CODEX_RUNTIME_HOME || path.join(os.homedir(), '.codex-a2a'),
  authHome = process.env.A2A_CODEX_AUTH_HOME || path.join(os.homedir(), '.codex'),
} = {}) {
  fs.mkdirSync(runtimeHome, { recursive: true, mode: 0o700 });

  const runtimeAuth = path.join(runtimeHome, 'auth.json');
  const sourceAuth = path.join(authHome, 'auth.json');
  if (!fs.existsSync(runtimeAuth)) {
    if (!fs.existsSync(sourceAuth)) {
      throw new Error(`Codex authentication file not found: ${sourceAuth}`);
    }
    fs.symlinkSync(sourceAuth, runtimeAuth);
  }

  return runtimeHome;
}

export function discoverSkillDirectories(roots = DEFAULT_SKILL_ROOTS) {
  const skillDirectories = new Set();
  const pending = roots.filter((root) => fs.existsSync(root));

  while (pending.length > 0) {
    const directory = pending.pop();
    let entries;
    try {
      entries = fs.readdirSync(directory, { withFileTypes: true });
    } catch {
      continue;
    }

    if (entries.some((entry) => entry.isFile() && entry.name === 'SKILL.md')) {
      skillDirectories.add(directory);
    }

    for (const entry of entries) {
      if (entry.isDirectory()) pending.push(path.join(directory, entry.name));
    }
  }

  return [...skillDirectories].sort();
}

/**
 * Codex auto-discovers user skills even with --ignore-user-config. The A2A
 * subprocess has its own tool protocol, so disabling those skills avoids a
 * context-budget error and prevents unrelated user skills from affecting it.
 */
export function buildDisabledSkillsOverride(roots = DEFAULT_SKILL_ROOTS) {
  const entries = discoverSkillDirectories(roots)
    .map((directory) => `{ path = ${JSON.stringify(directory)}, enabled = false }`);
  return entries.length > 0 ? `skills.config=[${entries.join(',')}]` : '';
}
