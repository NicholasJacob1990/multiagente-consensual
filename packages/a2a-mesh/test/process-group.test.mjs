import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import test from 'node:test';

import * as baseServer from '../runtime/a2a-shared/base-server.js';

const { scheduleForcedTaskTermination, signalTaskProcess } = baseServer;

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

test('peer supervisionado detecta a morte do supervisor', async () => {
  const supervisor = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], {
    stdio: 'ignore',
  });
  await new Promise((resolve) => supervisor.once('spawn', resolve));
  let watchdog;
  try {
    const detected = new Promise((resolve) => {
      watchdog = baseServer.startSupervisorWatchdog?.({
        supervisorPid: supervisor.pid,
        intervalMs: 10,
        onOrphaned: resolve,
      });
    });
    supervisor.kill('SIGTERM');
    await new Promise((resolve) => supervisor.once('exit', resolve));
    await Promise.race([
      detected,
      new Promise((_, reject) => setTimeout(() => reject(new Error('watchdog não detectou o supervisor morto')), 1000)),
    ]);
    assert.ok(watchdog, 'watchdog de supervisão não foi iniciado');
  } finally {
    if (watchdog) clearInterval(watchdog);
    if (supervisor.exitCode === null) supervisor.kill('SIGKILL');
  }
});
