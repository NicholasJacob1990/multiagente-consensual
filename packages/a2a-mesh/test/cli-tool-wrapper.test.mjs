import assert from 'node:assert/strict';
import test from 'node:test';

import { createToolCallStreamFilter } from '../runtime/a2a-shared/cli-tool-wrapper.js';

test('filtro incremental nunca exibe payload de tool_call dividido em chunks', () => {
  const filter = createToolCallStreamFilter();
  const chunks = [
    'Antes.\n<to',
    'ol_call>{"name":"a2a_',
    'broadcast","input":{"prompt":"segredo interno"}}</tool_',
    'call>\nDepois.',
  ];
  const visible = chunks.map((chunk) => filter.push(chunk)).join('') + filter.flush();
  assert.equal(visible, 'Antes.\n\nDepois.');
  assert.doesNotMatch(visible, /tool_call|a2a_broadcast|segredo interno/);
});

test('filtro preserva texto comum e descarta tool_call não terminado', () => {
  const common = createToolCallStreamFilter();
  assert.equal(common.push('Resposta normal'), 'Resposta normal');
  assert.equal(common.flush(), '');

  const unterminated = createToolCallStreamFilter();
  const visible = unterminated.push('Visível <tool_call>{"name":"x"}') + unterminated.flush();
  assert.equal(visible, 'Visível ');
});
