// ============================================
// Cursor MCP configuration — atomic, selective and reversible
// ============================================

import fs from 'node:fs';
import path from 'node:path';

function readJson(file) {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeAtomic(file, value, mode = 0o600) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temporary = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.tmp`);
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode });
  fs.renameSync(temporary, file);
  fs.chmodSync(file, mode);
}

function configPath(home) {
  return path.join(home, '.cursor', 'mcp.json');
}

function entryFor(nodePath, bridge) {
  return { command: nodePath, args: [bridge], type: 'stdio' };
}

function sameEntry(entry, nodePath, bridge) {
  return Boolean(
    entry
    && entry.command === nodePath
    && Array.isArray(entry.args)
    && entry.args.length === 1
    && path.resolve(entry.args[0]) === path.resolve(bridge),
  );
}

export function inspectCursorMcp({ home, nodePath, bridge }) {
  const file = configPath(home);
  const document = readJson(file);
  const servers = document.mcpServers && typeof document.mcpServers === 'object'
    ? document.mcpServers
    : {};
  const entry = servers['a2a-mesh'] || null;
  return {
    file,
    present: Boolean(entry),
    matches: sameEntry(entry, nodePath, bridge),
    entry,
  };
}

export function upsertCursorMcp({ home, nodePath, bridge, replace = false, dryRun = false }) {
  const state = inspectCursorMcp({ home, nodePath, bridge });
  if (state.matches) return { status: 'already-configured', bridge, file: state.file };
  if (state.present && !replace) return { status: 'preserved-existing', file: state.file };
  if (dryRun) return { status: state.present ? 'replaced' : 'configured', simulated: true, bridge, file: state.file };

  const document = readJson(state.file);
  const mode = 0o600;
  if (state.present) {
    const stamp = `${Date.now()}-${process.pid}`;
    const backup = `${state.file}.a2a-mesh-backup-${stamp}`;
    fs.copyFileSync(state.file, backup, fs.constants.COPYFILE_EXCL);
    fs.chmodSync(backup, mode);
  }
  document.mcpServers = document.mcpServers && typeof document.mcpServers === 'object'
    ? { ...document.mcpServers }
    : {};
  document.mcpServers['a2a-mesh'] = entryFor(nodePath, bridge);
  writeAtomic(state.file, document, mode || 0o600);
  return { status: state.present ? 'replaced' : 'configured', bridge, file: state.file };
}

export function removeCursorMcp({ home, nodePath, bridge, dryRun = false }) {
  const state = inspectCursorMcp({ home, nodePath, bridge });
  if (!state.present) return { status: 'absent', file: state.file };
  if (!state.matches) return { status: 'preserved-existing', file: state.file };
  if (dryRun) return { status: 'simulated', file: state.file };

  const document = readJson(state.file);
  const mode = fs.statSync(state.file).mode & 0o777;
  document.mcpServers = { ...(document.mcpServers || {}) };
  delete document.mcpServers['a2a-mesh'];
  writeAtomic(state.file, document, mode || 0o600);
  return { status: 'removed', file: state.file };
}
