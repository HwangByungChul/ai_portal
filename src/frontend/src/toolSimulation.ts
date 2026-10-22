import type { RequestOptions } from './api';

interface UnsavedTool {
  tool_id: string;
  name: string;
  description: string;
  source_type: string;
  input_schema: Record<string, unknown>;
  raw_meta: Record<string, unknown>;
  dev_profile: { protocol_type: string; base_endpoint_url: string };
}

export function simulateUnsavedTool(
  request: <T>(path: string, options: RequestOptions) => Promise<T>,
  scope: { tenantId: string; csrf: string },
  tool: UnsavedTool,
  argumentsText: string,
): Promise<unknown> {
  const argumentsValue: unknown = JSON.parse(argumentsText);
  if (typeof argumentsValue !== 'object' || argumentsValue === null || Array.isArray(argumentsValue)) {
    throw new Error('테스트 인자는 JSON 객체여야 합니다.');
  }
  return request('/tools/auto-wrap/simulate', {
    method: 'POST',
    tenantId: scope.tenantId,
    csrf: scope.csrf,
    body: {
      tool_id: tool.tool_id,
      name: tool.name,
      description: tool.description,
      source_type: tool.source_type,
      input_schema: tool.input_schema,
      raw_meta: tool.raw_meta,
      dev_profile: tool.dev_profile,
      arguments: argumentsValue,
    },
  });
}
