import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  extractResponseArtifacts,
  mergeArtifacts,
  preserveLocalFileArtifact,
  resolveStoredArtifact,
  stripArtifactDeclarations,
} from '../runtime/a2a-shared/file-artifacts.js';

test('preserva arquivo local por hash e mantém preview textual', (t) => {
  const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-artifact-test-'));
  const source = path.join(fixtureRoot, 'minuta.md');
  const priorStore = process.env.A2A_ARTIFACT_STORE;
  process.env.A2A_ARTIFACT_STORE = path.join(fixtureRoot, 'store');
  fs.writeFileSync(source, '# Minuta\n\nVersão aprovada.\n');
  t.after(() => {
    if (priorStore === undefined) delete process.env.A2A_ARTIFACT_STORE;
    else process.env.A2A_ARTIFACT_STORE = priorStore;
    fs.rmSync(fixtureRoot, { recursive: true, force: true });
  });

  const artifact = preserveLocalFileArtifact(source, { taskId: 'task-1', agentId: 'codex' });
  assert.equal(artifact.name, 'minuta.md');
  assert.equal(artifact.metadata.kind, 'local-file');
  assert.equal(artifact.metadata.size, fs.statSync(source).size);
  assert.match(artifact.metadata.sha256, /^[a-f0-9]{64}$/);
  assert.equal(artifact.parts[0].type, 'text');
  assert.match(artifact.parts[0].text, /Versão aprovada/);
  assert.equal(artifact.parts[1].type, 'file');

  fs.writeFileSync(source, '# Minuta alterada posteriormente\n');
  const stored = resolveStoredArtifact(artifact);
  assert.match(fs.readFileSync(stored.path, 'utf8'), /Versão aprovada/);
  assert.doesNotMatch(fs.readFileSync(stored.path, 'utf8'), /posteriormente/);
});

test('extrai declarações de arquivos e remove o marcador da resposta visível', (t) => {
  const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-artifact-declaration-'));
  const source = path.join(fixtureRoot, 'parecer.pdf');
  const priorStore = process.env.A2A_ARTIFACT_STORE;
  process.env.A2A_ARTIFACT_STORE = path.join(fixtureRoot, 'store');
  fs.writeFileSync(source, Buffer.from('%PDF-1.7\nfixture\n'));
  t.after(() => {
    if (priorStore === undefined) delete process.env.A2A_ARTIFACT_STORE;
    else process.env.A2A_ARTIFACT_STORE = priorStore;
    fs.rmSync(fixtureRoot, { recursive: true, force: true });
  });

  const output = `Parecer concluído.\n<artifact_path>${source}</artifact_path>`;
  const artifacts = extractResponseArtifacts(output, { taskId: 'task-pdf', agentId: 'claude' });
  assert.equal(artifacts.length, 1);
  assert.equal(artifacts[0].name, 'parecer.pdf');
  assert.equal(artifacts[0].metadata.mimeType, 'application/pdf');
  assert.equal(stripArtifactDeclarations(output), 'Parecer concluído.');
  assert.equal(mergeArtifacts(artifacts, artifacts).length, 1);
});
