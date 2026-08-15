import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  inspectCursorMcp,
  removeCursorMcp,
  upsertCursorMcp,
} from '../runtime/a2a-shared/cursor-mcp-config.js';

test('mescla MCP do Cursor sem apagar servidores existentes e remove só a entrada própria', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-cursor-mcp-'));
  const file = path.join(home, '.cursor', 'mcp.json');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify({ mcpServers: { existente: { command: 'keep-me' } }, preferencia: true }));
  const nodePath = process.execPath;
  const bridge = '/opt/a2a/mesh-bridge-mcp.js';

  try {
    const installed = upsertCursorMcp({ home, nodePath, bridge });
    assert.equal(installed.status, 'configured');
    const document = JSON.parse(fs.readFileSync(file, 'utf8'));
    assert.equal(document.mcpServers.existente.command, 'keep-me');
    assert.equal(document.preferencia, true);
    assert.deepEqual(document.mcpServers['a2a-mesh'].args, [bridge]);
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    assert.equal(inspectCursorMcp({ home, nodePath, bridge }).matches, true);

    const removed = removeCursorMcp({ home, nodePath, bridge });
    assert.equal(removed.status, 'removed');
    const after = JSON.parse(fs.readFileSync(file, 'utf8'));
    assert.equal(after.mcpServers.existente.command, 'keep-me');
    assert.equal(after.mcpServers['a2a-mesh'], undefined);
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
});

test('preserva configuração a2a-mesh divergente sem --replace-mcp', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-cursor-preserve-'));
  const file = path.join(home, '.cursor', 'mcp.json');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify({ mcpServers: { 'a2a-mesh': { command: 'custom', args: ['custom.js'] } } }));
  try {
    assert.equal(upsertCursorMcp({ home, nodePath: process.execPath, bridge: '/new.js' }).status, 'preserved-existing');
    assert.equal(JSON.parse(fs.readFileSync(file, 'utf8')).mcpServers['a2a-mesh'].command, 'custom');
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
});
