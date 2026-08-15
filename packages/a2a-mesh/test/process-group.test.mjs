import assert from 'node:assert/strict';
import test from 'node:test';

import { scheduleForcedTaskTermination, signalTaskProcess } from '../runtime/a2a-shared/base-server.js';

test('SIGKILL continua sendo enviado depois de SIGTERM marcar child.killed', () => {
  const signals = [];
  const child = {
    pid: 99999999,
    killed: false,
    exitCode: null,
    kill(signal) {
      signals.push(signal);
      this.killed = true;
      return true;
    },
  };
  const task = { process: child };
  signalTaskProcess(task, 'SIGTERM');
  assert.equal(child.killed, true);
  signalTaskProcess(task, 'SIGKILL');
  assert.deepEqual(signals, ['SIGTERM', 'SIGKILL']);
});

test('shutdown aguarda a janela de graça e força SIGKILL antes de sair', async () => {
  const signals = [];
  const task = {
    process: {
      pid: 99999998,
      exitCode: null,
      kill(signal) { signals.push(signal); return true; },
    },
  };
  await new Promise((resolve) => {
    scheduleForcedTaskTermination([task], { graceMs: 0, exit: resolve });
  });
  assert.deepEqual(signals, ['SIGKILL']);
});
