import type {WorkflowNodeInfo, WorkflowEdgeInfo} from '../types';

export type StudioNodeCategory = 'trigger' | 'prompt' | 'llm' | 'knowledge' | 'tool' | 'logic' | 'response';

export interface ComponentPaletteItem {
  type: string;
  category: StudioNodeCategory;
  name: string;
  description: string;
  icon: string;
  defaultConfig: Record<string, any>;
}

export interface StudioNodeData {
  [key: string]: unknown;
  nodeId: string;
  nodeType: string;
  category: StudioNodeCategory;
  label: string;
  description?: string;
  config: Record<string, any>;
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'idle';
  outputPreview?: any;
  onSelectNode?: (nodeId: string) => void;
  onDeleteNode?: (nodeId: string) => void;
  onDuplicateNode?: (nodeId: string) => void;
}

export interface StudioEdgeData {
  label?: string;
}

export interface WorkflowDefinitionData {
  workflow_id: string;
  name: string;
  version: string;
  description: string;
  nodes: WorkflowNodeInfo[];
  edges: WorkflowEdgeInfo[];
}

export const PALETTE_CATEGORIES: {id: StudioNodeCategory; label: string; icon: string}[] = [
  {id: 'trigger', label: '입력 & 트리거', icon: '📥'},
  {id: 'prompt', label: '프롬프트 & 템플릿', icon: '📝'},
  {id: 'llm', label: 'AI 모델 (LLM)', icon: '🧠'},
  {id: 'knowledge', label: '지식검색 (RAG)', icon: '📚'},
  {id: 'tool', label: '도구 & API 연동', icon: '🛠️'},
  {id: 'logic', label: '로직 & 검증', icon: '🔀'},
  {id: 'response', label: '출력 & 응답', icon: '📤'},
];

export const PALETTE_ITEMS: ComponentPaletteItem[] = [
  {
    type: 'trigger_input',
    category: 'trigger',
    name: '사용자 질의 입력',
    description: '포털 사용자로부터 대화형 질문이나 요청을 수신합니다.',
    icon: '📥',
    defaultConfig: {input_key: 'query', placeholder: '질문을 입력하세요'}
  },
  {
    type: 'trigger_webhook',
    category: 'trigger',
    name: '시스템 이벤트 / Webhook',
    description: '외부 시스템 이벤트 또는 스케줄러 트리거를 수신합니다.',
    icon: '⚡',
    defaultConfig: {endpoint: '/webhook/event', method: 'POST'}
  },
  {
    type: 'prompt_template',
    category: 'prompt',
    name: '프롬프트 템플릿',
    description: '문맥 및 사용자 입력을 결합하는 템플릿을 정의합니다.',
    icon: '📝',
    defaultConfig: {template: '다음 정보를 바탕으로 고객의 질문에 전문적으로 답변하세요:\n{{context}}\n\n질문: {{query}}'}
  },
  {
    type: 'llm_reasoning',
    category: 'llm',
    name: '금융 특화 AI 모델',
    description: '금융 규정 및 정형 분석에 최적화된 내부 고성능 LLM',
    icon: '🧠',
    defaultConfig: {model_id: 'mock-fast', temperature: 0.2, max_tokens: 2048, system_prompt: '당신은 금융 심사 전문 AI 어시스턴트입니다.'}
  },
  {
    type: 'llm_creative',
    category: 'llm',
    name: '범용 보고서 작성 모델',
    description: '유연한 텍스트 생성과 요약에 최적화된 LLM',
    icon: '✨',
    defaultConfig: {model_id: 'mock-creative', temperature: 0.7, max_tokens: 3000, system_prompt: '상세하고 정중한 고객 안내문을 작성합니다.'}
  },
  {
    type: 'rag_search',
    category: 'knowledge',
    name: '사내 지식베이스 검색 (RAG)',
    description: '여신 규정, 업무 매뉴얼 및 내부 문서를 벡터 검색합니다.',
    icon: '📚',
    defaultConfig: {knowledge_base: 'kb-credit-guideline', top_k: 3, score_threshold: 0.75}
  },
  {
    type: 'tool_execution',
    category: 'tool',
    name: '금융 상품 / 한도 조회 Tool',
    description: '승인된 내부 기간계 도구(Tool)를 호출하여 실시간 데이터를 조회합니다.',
    icon: '🛠️',
    defaultConfig: {tool_id: 'financial_product_lookup', arguments: {category: 'loan'}}
  },
  {
    type: 'logic_condition',
    category: 'logic',
    name: '조건 분기 (If/Else)',
    description: '조회된 데이터나 점수에 따라 후속 실행 흐름을 분기합니다.',
    icon: '🔀',
    defaultConfig: {condition: 'score >= 70', true_label: '승인 흐름', false_label: '정밀 심사'}
  },
  {
    type: 'logic_guardrail',
    category: 'logic',
    name: '가드레일 & 보안 검증',
    description: '개인정보(PII) 유출 및 금융 금지어 포함 여부를 필터링합니다.',
    icon: '🛡️',
    defaultConfig: {policy: 'pii_and_compliance', action: 'mask_and_proceed'}
  },
  {
    type: 'response_output',
    category: 'response',
    name: '최종 응답 반환',
    description: '사용자 또는 호출 시스템에 최종 심사/답변 결과를 반환합니다.',
    icon: '📤',
    defaultConfig: {output_format: 'markdown'}
  }
];

export const CATEGORY_COLORS: Record<StudioNodeCategory, {bg: string; border: string; badge: string; text: string}> = {
  trigger: {bg: '#F0FDF4', border: '#86EFAC', badge: '#15803D', text: '#166534'},
  prompt: {bg: '#FDF4FF', border: '#F0ABFC', badge: '#A21CAF', text: '#86198F'},
  llm: {bg: '#FAF5FF', border: '#D8B4FE', badge: '#7E22CE', text: '#6B21A8'},
  knowledge: {bg: '#EFF6FF', border: '#93C5FD', badge: '#1D4ED8', text: '#1E40AF'},
  tool: {bg: '#FFF7ED', border: '#FDBA74', badge: '#C2410C', text: '#9A3412'},
  logic: {bg: '#FFFBEB', border: '#FDE68A', badge: '#B45309', text: '#92400E'},
  response: {bg: '#F8FAFC', border: '#CBD5E1', badge: '#334155', text: '#1E293B'}
};
