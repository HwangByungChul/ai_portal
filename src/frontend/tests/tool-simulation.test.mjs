import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { simulateUnsavedTool } from '../src/toolSimulation.ts';

const scope = { tenantId: 'tenant-a', csrf: 'synthetic-csrf' };
const tool = {
  tool_id: 'fixture_tool', name: 'Fixture', description: 'unsaved', source_type: 'openapi',
  input_schema: { type: 'object' }, raw_meta: {},
  dev_profile: { protocol_type: 'rest_http', base_endpoint_url: 'https://example.invalid/dev' },
  // Extra client state must never reach the transient API.
  prd_profile: { base_endpoint_url: 'https://example.invalid/prd' },
  publication_status: 'approved_published',
};

test('unsaved simulation sends one transient request with current scope and no production authority', async () => {
  const calls = [];
  const reply = { status: 'success', routed_env: 'development' };
  const request = async (...args) => { calls.push(args); return reply; };
  assert.equal(await simulateUnsavedTool(request, scope, tool, '{"amount":10}'), reply);
  assert.deepEqual(calls, [['/tools/auto-wrap/simulate', {
    ...scope, method: 'POST', body: {
      tool_id: tool.tool_id, name: tool.name, description: tool.description,
      source_type: tool.source_type, input_schema: tool.input_schema,
      raw_meta: {}, dev_profile: tool.dev_profile, arguments: { amount: 10 },
    },
  }]]);
});

test('rejected simulation never falls back to durable registration', async () => {
  const paths = [];
  const failure = new Error('simulation denied');
  await assert.rejects(simulateUnsavedTool(async path => {
    paths.push(path); throw failure;
  }, scope, tool, '{}'), failure);
  assert.deepEqual(paths, ['/tools/auto-wrap/simulate']);
});

test('invalid arguments fail before requesting any endpoint', () => {
  for (const text of ['{', 'null', '[]', '3']) {
    assert.throws(() => simulateUnsavedTool(() => {
      assert.fail('invalid input must not issue a request');
    }, scope, tool, text));
  }
});

test('wizard invokes the transient helper and reserves the durable endpoint for final registration', () => {
  const source = readFileSync(new URL('../src/ToolAdminPage.tsx', import.meta.url), 'utf8');
  const simulation = source.split('const handleTestInvoke = async () => {')[1].split('const handleFinalRegister')[0];
  assert.match(simulation, /simulateUnsavedTool\(/);
  assert.doesNotMatch(simulation, /auto-wrap\/register|\/invoke/);
  assert.equal(source.match(/['"]\/tools\/auto-wrap\/register['"]/g)?.length, 1);
});
