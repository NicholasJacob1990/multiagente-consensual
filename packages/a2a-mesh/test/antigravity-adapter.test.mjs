import assert from 'node:assert/strict';
import test from 'node:test';

import {
  REQUIRED_ANTIGRAVITY_MODEL,
  antigravityModelLabelsMatch,
  parseAntigravityModels,
  parseAntigravityStreamLine,
} from '../runtime/a2a-gemini/antigravity-cli-adapter.js';

test('modelo Antigravity obrigatório é Gemini 3.7 Flash High', () => {
  assert.equal(REQUIRED_ANTIGRAVITY_MODEL, 'gemini-3.7-flash-high');
  assert.equal(antigravityModelLabelsMatch(REQUIRED_ANTIGRAVITY_MODEL, 'gemini-3.7-flash-high'), true);
  assert.equal(antigravityModelLabelsMatch(REQUIRED_ANTIGRAVITY_MODEL, 'gemini-3.6-flash-high'), false);
});

test('parser reconhece catálogo e stream-json real do Antigravity', () => {
  assert.deepEqual(
    parseAntigravityModels('gemini-3.7-flash-high  Gemini 3.7 Flash (High)\ngemini-3.6-flash-high  Gemini 3.6 Flash (High)\n'),
    ['gemini-3.7-flash-high', 'gemini-3.6-flash-high'],
  );
  assert.deepEqual(
    parseAntigravityStreamLine('{"event":"init","conversation_id":"c1","init":{"model":"gemini-3.7-flash-high"}}'),
    { event: 'init', model: 'gemini-3.7-flash-high', conversationId: 'c1' },
  );
  const delta = parseAntigravityStreamLine('{"event":"step_update","step_update":{"state":"DONE","step_type":"agent_response","text_delta":"OK\\n"}}');
  assert.equal(delta.text, 'OK\n');
  const result = parseAntigravityStreamLine('{"event":"result","result":{"status":"SUCCESS","response":"OK\\n","conversation_id":"c1"}}');
  assert.equal(result.terminal, true);
  assert.equal(result.isError, false);
  assert.equal(result.response, 'OK\n');
});
