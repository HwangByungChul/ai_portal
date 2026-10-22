import React, { useState, useEffect } from 'react';
import type { Tenant, User } from './types';
import { api } from './api';
import { simulateUnsavedTool } from './toolSimulation';

interface DynamicToolItem {
  tool_id: string;
  name: string;
  description: string;
  source_type: string;
  input_schema: any;
  enabled: boolean;
  has_dev_profile: boolean;
  has_prd_profile: boolean;
}

const SAMPLE_SPECS = {
  openapi: JSON.stringify({
    openapi: "3.0.0",
    info: { title: "BNK 코어뱅킹 신용대출 조회 API", version: "1.0" },
    paths: {
      "/api/v1/credit/loan-limit": {
        post: {
          operationId: "check_loan_limit",
          summary: "대출 가능 한도 및 우대금리 자동 심사",
          requestBody: {
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  required: ["customer_id", "annual_income_krw"],
                  properties: {
                    customer_id: { type: "string", description: "고객 고유 식별자" },
                    annual_income_krw: { type: "number", description: "연소득 (원 단위)" },
                    employment_type: { type: "string", description: "직장 형태 (정규직/전문직/사업자)" }
                  }
                }
              }
            }
          }
        }
      }
    }
  }, null, 2),

  wsdl: `<?xml version="1.0" encoding="utf-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:tns="http://banking.bnk.co.kr/remittance"
                  targetNamespace="http://banking.bnk.co.kr/remittance">
  <wsdl:message name="RealtimeTransferInput">
    <wsdl:part name="SenderAccount" type="xsd:string"/>
    <wsdl:part name="ReceiverAccount" type="xsd:string"/>
    <wsdl:part name="TransferAmount" type="xsd:long"/>
    <wsdl:part name="BankCode" type="xsd:string"/>
  </wsdl:message>
  <wsdl:portType name="RemittancePortType">
    <wsdl:operation name="RealtimeTransfer">
      <wsdl:documentation>실시간 타행 송금 및 지급 결제 서비스 (SOAP)</wsdl:documentation>
      <wsdl:input message="tns:RealtimeTransferInput"/>
    </wsdl:operation>
  </wsdl:portType>
</wsdl:definitions>`,

  jdbc: JSON.stringify({
    table_or_view: "v_branch_daily_sales_stats",
    db_type: "postgresql",
    columns: [
      { name: "branch_code", type: "string" },
      { name: "branch_name", type: "string" },
      { name: "total_deposit_krw", type: "number" },
      { name: "consultation_score", type: "number" }
    ],
    custom_sql: "SELECT branch_code, branch_name, total_deposit_krw, consultation_score FROM v_branch_daily_sales_stats"
  }, null, 2),

  financial_packet: JSON.stringify({
    packet_code: "BNK-FEP-0200",
    packet_name: "타행 즉시 이체 승인 전문 (ISO 8583 / FEP)",
    protocol: "tcp_socket",
    fields: [
      { field_id: "INST_CODE", name: "참가기관코드", type: "string", length: 3 },
      { field_id: "TX_CODE", name: "전문거래구분", type: "string", length: 4 },
      { field_id: "ACCOUNT_NO", name: "출금계좌번호", type: "string", length: 16 },
      { field_id: "TX_AMOUNT", name: "거래금액", type: "number", length: 10 },
      { field_id: "REMARK", name: "통장적요메모", type: "string", length: 20 }
    ]
  }, null, 2)
};

export function ToolAdminPage({ tenant, user }: { tenant: Tenant; user: User }) {
  const [tools, setTools] = useState<DynamicToolItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);

  // Wizard States
  const [sourceType, setSourceType] = useState<'openapi' | 'wsdl' | 'jdbc' | 'financial_packet'>('openapi');
  const [rawSpec, setRawSpec] = useState(SAMPLE_SPECS.openapi);
  const [parsing, setParsing] = useState(false);
  const [parsedTools, setParsedTools] = useState<any[]>([]);
  const [selectedParsedIndex, setSelectedParsedIndex] = useState(0);

  // Dev & Prd Endpoint profiles
  const [devEndpoint, setDevEndpoint] = useState('https://dev.example.invalid/gateway/tools');
  const [prdEndpoint, setPrdEndpoint] = useState('https://production.example.invalid/gateway/tools');

  // Test Execution State
  const [testArgs, setTestArgs] = useState('{}');
  const [testResult, setTestResult] = useState<any>(null);
  const [invoking, setInvoking] = useState(false);
  const [registering, setRegistering] = useState(false);

  useEffect(() => {
    fetchTools();
  }, [tenant.tenant_id]);

  const fetchTools = async () => {
    setLoading(true);
    try {
      const data = await api.request<{ items: DynamicToolItem[] }>('/tools/dynamic', {
        tenantId: tenant.tenant_id,
      });
      setTools(data.items || []);
    } catch (err) {
      console.error('Failed to fetch dynamic tools', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSourceTypeChange = (st: 'openapi' | 'wsdl' | 'jdbc' | 'financial_packet') => {
    setSourceType(st);
    setRawSpec(SAMPLE_SPECS[st]);
    setParsedTools([]);
    setTestResult(null);
  };

  const handleParseSpec = async () => {
    setParsing(true);
    setTestResult(null);
    try {
      let bodyContent: any = rawSpec;
      if (sourceType === 'openapi' || sourceType === 'jdbc' || sourceType === 'financial_packet') {
        try {
          bodyContent = JSON.parse(rawSpec);
        } catch {
          alert('올바른 JSON 형식이 아닙니다.');
          setParsing(false);
          return;
        }
      }

      const data = await api.request<{ tools: any[] }>('/tools/auto-wrap/parse', {
        method: 'POST',
        tenantId: tenant.tenant_id,
        csrf: user.csrf_token,
        body: {
          source_type: sourceType,
          raw_content: bodyContent
        }
      });
      setParsedTools(data.tools || []);
      setSelectedParsedIndex(0);

      // Default sample arguments from generated schema
      if (data.tools && data.tools[0]) {
        const schema = data.tools[0].input_schema;
        const defaultArgs: any = {};
        if (schema && schema.properties) {
          Object.keys(schema.properties).forEach(k => {
            const prop = schema.properties[k];
            defaultArgs[k] = prop.type === 'number' ? 10000 : 'TEST_VAL';
          });
        }
        setTestArgs(JSON.stringify(defaultArgs, null, 2));
      }
    } catch (err: any) {
      alert(`오류 발생: ${err.message}`);
    } finally {
      setParsing(false);
    }
  };

  const handleTestInvoke = async () => {
    const curTool = parsedTools[selectedParsedIndex];
    if (!curTool) return;
    setInvoking(true);
    setTestResult(null);

    try {
      const data = await simulateUnsavedTool(
        api.request.bind(api),
        { tenantId: tenant.tenant_id, csrf: user.csrf_token },
        {
          tool_id: curTool.tool_id,
          name: curTool.name,
          description: curTool.description,
          source_type: sourceType,
          input_schema: curTool.input_schema,
          raw_meta: curTool.raw_operation || curTool,
          dev_profile: {
            protocol_type: sourceType === 'wsdl' ? 'soap_xml' : sourceType === 'jdbc' ? 'jdbc_view' : sourceType === 'financial_packet' ? 'tcp_socket' : 'rest_http',
            base_endpoint_url: devEndpoint,
          },
        },
        testArgs,
      );
      setTestResult(data);
    } catch (err: any) {
      alert(`테스트 호출 실패: ${err.message}`);
    } finally {
      setInvoking(false);
    }
  };

  const handleFinalRegister = async () => {
    const curTool = parsedTools[selectedParsedIndex];
    if (!curTool) return;
    setRegistering(true);

    try {
      await api.request('/tools/auto-wrap/register', {
        method: 'POST',
        tenantId: tenant.tenant_id,
        csrf: user.csrf_token,
        body: {
          tool_id: curTool.tool_id,
          name: curTool.name,
          description: curTool.description,
          source_type: sourceType,
          input_schema: curTool.input_schema,
          raw_meta: curTool.raw_operation || curTool,
          dev_profile: {
            protocol_type: sourceType === 'wsdl' ? 'soap_xml' : sourceType === 'jdbc' ? 'jdbc_view' : sourceType === 'financial_packet' ? 'tcp_socket' : 'rest_http',
            base_endpoint_url: devEndpoint,
          },
          prd_profile: {
            protocol_type: sourceType === 'wsdl' ? 'soap_xml' : sourceType === 'jdbc' ? 'jdbc_view' : sourceType === 'financial_packet' ? 'tcp_socket' : 'rest_http',
            base_endpoint_url: prdEndpoint,
          }
        }
      });

      alert('모의 Tool 정의를 테넌트별 영속 Registry에 저장했습니다. 호출은 개발 프로파일의 fixture 모의 실행이며 실제 MCP 서버나 금융 시스템 연결은 제공하지 않습니다.');
      setShowModal(false);
      fetchTools();
    } catch (err: any) {
      alert(`오류: ${err.message}`);
    } finally {
      setRegistering(false);
    }
  };

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: '24px 20px' }}>
      {/* 상단 헤더 */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: '#FFFFFF',
        padding: '20px 28px',
        borderRadius: 16,
        border: '1px solid #E2E8F0',
        boxShadow: '0 4px 16px rgba(15, 23, 42, 0.04)',
        marginBottom: 24
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 26 }}>🔌</span>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: '#0F172A' }}>
              연계 Connector & MCP Tool 관리
            </h1>
            <span style={{
              background: '#EEF2FF',
              color: '#4F46E5',
              fontSize: 12,
              fontWeight: 700,
              padding: '4px 10px',
              borderRadius: 20
            }}>
              구현 진행 중
            </span>
          </div>
          <p style={{ margin: '6px 0 0 0', fontSize: 14, color: '#64748B' }}>
            OpenAPI, WSDL, JDBC 명세 및 금융 전문(ISO 8583, EAI, FEP)을 코딩 없이 <strong>MCP Tool로 자동 변환</strong>하고,
            명세를 Tool 초안으로 변환합니다. 정의는 테넌트별 Registry에 저장하고, 호출은 개발 프로파일 fixture로 모의 실행하며 실제 금융 시스템에는 연결하지 않습니다.
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            setShowModal(true);
            setParsedTools([]);
            setTestResult(null);
          }}
          style={{
            background: 'linear-gradient(135deg, #4F46E5 0%, #3B82F6 100%)',
            color: '#FFFFFF',
            border: 'none',
            padding: '12px 22px',
            borderRadius: 10,
            fontSize: 14,
            fontWeight: 700,
            cursor: 'pointer',
            boxShadow: '0 4px 14px rgba(79, 70, 229, 0.3)',
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
        >
          <span>✨</span> 노코딩 Tool 자동 생성 마법사
        </button>
      </div>

      {/* 등록된 Tool 목록 그리드 */}
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 17, fontWeight: 700, color: '#1E293B', marginBottom: 12 }}>
          현재 등록된 연계 MCP Tool ({tools.length}개)
        </h2>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#64748B' }}>도구 목록을 불러오는 중...</div>
        ) : tools.length === 0 ? (
          <div style={{
            background: '#F8FAFC',
            border: '2px dashed #CBD5E1',
            borderRadius: 12,
            padding: '48px 24px',
            textAlign: 'center',
            color: '#64748B'
          }}>
            <p style={{ fontSize: 16, fontWeight: 600, margin: '0 0 8px 0' }}>등록된 동적 MCP Tool이 없습니다.</p>
            <p style={{ fontSize: 13, margin: '0 0 16px 0' }}>상단의 [노코딩 Tool 자동 생성 마법사]를 열어 OpenAPI/WSDL/JDBC/금융 전문을 즉시 변환 등록해보세요.</p>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))', gap: 16 }}>
            {tools.map(t => (
              <div
                key={t.tool_id}
                style={{
                  background: '#FFFFFF',
                  borderRadius: 12,
                  border: '1px solid #E2E8F0',
                  padding: 20,
                  boxShadow: '0 2px 8px rgba(15, 23, 42, 0.03)'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div>
                    <span style={{
                      fontSize: 11,
                      fontWeight: 700,
                      padding: '3px 8px',
                      borderRadius: 6,
                      background: t.source_type === 'openapi' ? '#E0F2FE' : t.source_type === 'wsdl' ? '#FEF3C7' : t.source_type === 'jdbc' ? '#DCFCE7' : '#F3E8FF',
                      color: t.source_type === 'openapi' ? '#0369A1' : t.source_type === 'wsdl' ? '#B45309' : t.source_type === 'jdbc' ? '#15803D' : '#7E22CE',
                      textTransform: 'uppercase'
                    }}>
                      {t.source_type}
                    </span>
                    <h3 style={{ margin: '8px 0 4px 0', fontSize: 16, fontWeight: 700, color: '#0F172A' }}>{t.name}</h3>
                    <code style={{ fontSize: 12, color: '#64748B' }}>{t.tool_id}</code>
                  </div>
                  <span style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: '3px 8px',
                    borderRadius: 12,
                    background: '#ECFDF5',
                    color: '#059669'
                  }}>
                    ● 활성 상태
                  </span>
                </div>

                <p style={{ fontSize: 13, color: '#475569', margin: '0 0 14px 0', lineHeight: 1.5, maxHeight: 42, overflow: 'hidden' }}>
                  {t.description}
                </p>

                {/* 환경 지원 뱃지 */}
                <div style={{ display: 'flex', gap: 8, borderTop: '1px solid #F1F5F9', paddingTop: 12 }}>
                  <span style={{
                    fontSize: 12,
                    padding: '4px 10px',
                    borderRadius: 6,
                    background: t.has_dev_profile ? '#F0FDF4' : '#FEF2F2',
                    color: t.has_dev_profile ? '#166534' : '#991B1B',
                    border: '1px solid #BBF7D0'
                  }}>
                    🧪 Dev (시험/Draft) 지원
                  </span>
                  <span style={{
                    fontSize: 12,
                    padding: '4px 10px',
                    borderRadius: 6,
                    background: t.has_prd_profile ? '#EEF2FF' : '#FEF2F2',
                    color: t.has_prd_profile ? '#3730A3' : '#991B1B',
                    border: '1px solid #C7D2FE'
                  }}>
                    🚀 Prd (승인완료) 지원
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 노코딩 Auto-Wrapping 생성 마법사 모달 */}
      {showModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(15, 23, 42, 0.65)',
          backdropFilter: 'blur(6px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: 20
        }}>
          <div style={{
            background: '#FFFFFF',
            borderRadius: 16,
            width: '100%',
            maxWidth: 1080,
            maxHeight: '92vh',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
            overflow: 'hidden'
          }}>
            {/* 모달 헤더 */}
            <div style={{
              padding: '18px 24px',
              borderBottom: '1px solid #E2E8F0',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              background: '#F8FAFC'
            }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: '#0F172A', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>🪄</span> 노코딩 MCP Tool 자동 생성 & 환경 분기 설정
                </h2>
                <p style={{ margin: '4px 0 0 0', fontSize: 13, color: '#64748B' }}>
                  인터페이스 명세를 업로드하면 수동 개발 코딩 없이 MCP 스키마가 즉시 생성됩니다.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#64748B' }}
              >
                ✕
              </button>
            </div>

            {/* 모달 본문 (2-Column) */}
            <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', overflow: 'hidden', flex: 1 }}>
              {/* 좌측: 인터페이스 유형 선택 및 명세 입력 */}
              <div style={{ padding: 24, borderRight: '1px solid #E2E8F0', overflowY: 'auto' }}>
                <label style={{ fontSize: 13, fontWeight: 700, color: '#334155', display: 'block', marginBottom: 8 }}>
                  1. 인터페이스 소스 규격 선택
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 16 }}>
                  {[
                    { id: 'openapi', label: 'OpenAPI (Swagger)' },
                    { id: 'wsdl', label: 'WSDL (SOAP XML)' },
                    { id: 'jdbc', label: 'JDBC (DB View)' },
                    { id: 'financial_packet', label: '금융 전문 (ISO/FEP)' }
                  ].map(tab => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => handleSourceTypeChange(tab.id as any)}
                      style={{
                        padding: '10px 6px',
                        fontSize: 12,
                        fontWeight: 700,
                        borderRadius: 8,
                        border: sourceType === tab.id ? '2px solid #4F46E5' : '1px solid #CBD5E1',
                        background: sourceType === tab.id ? '#EEF2FF' : '#FFFFFF',
                        color: sourceType === tab.id ? '#4F46E5' : '#475569',
                        cursor: 'pointer'
                      }}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <label style={{ fontSize: 13, fontWeight: 700, color: '#334155' }}>
                    2. 인터페이스 명세서 내용 (JSON / XML)
                  </label>
                  <button
                    type="button"
                    onClick={() => setRawSpec(SAMPLE_SPECS[sourceType])}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#4F46E5',
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      textDecoration: 'underline'
                    }}
                  >
                    ↺ 기본 샘플 불러오기
                  </button>
                </div>

                <textarea
                  value={rawSpec}
                  onChange={e => setRawSpec(e.target.value)}
                  rows={14}
                  style={{
                    width: '100%',
                    fontFamily: 'monospace',
                    fontSize: 12,
                    padding: 12,
                    borderRadius: 8,
                    border: '1px solid #CBD5E1',
                    background: '#0F172A',
                    color: '#F8FAFC',
                    lineHeight: 1.4,
                    boxSizing: 'border-box',
                    marginBottom: 16
                  }}
                />

                <button
                  type="button"
                  onClick={handleParseSpec}
                  disabled={parsing}
                  style={{
                    width: '100%',
                    background: '#4F46E5',
                    color: '#FFFFFF',
                    border: 'none',
                    padding: '12px',
                    borderRadius: 8,
                    fontSize: 14,
                    fontWeight: 700,
                    cursor: parsing ? 'not-allowed' : 'pointer'
                  }}
                >
                  {parsing ? '명세 분석 및 스키마 매핑 중...' : '⚡ 노코딩 스키마 자동 변환 (Parse)'}
                </button>
              </div>

              {/* 우측: 변환된 MCP Tool 확인 및 Dev/Prd 엔드포인트 설정 */}
              <div style={{ padding: 24, overflowY: 'auto', background: '#FAFAFA' }}>
                <label style={{ fontSize: 13, fontWeight: 700, color: '#334155', display: 'block', marginBottom: 8 }}>
                  3. 생성된 MCP Tool 명세 및 환경별 엔드포인트 바인딩
                </label>

                {parsedTools.length === 0 ? (
                  <div style={{
                    padding: 40,
                    textAlign: 'center',
                    color: '#94A3B8',
                    border: '1px dashed #CBD5E1',
                    borderRadius: 8
                  }}>
                    좌측에서 [노코딩 스키마 자동 변환] 버튼을 클릭하면<br />
                    추출된 MCP Tool 스키마와 엔드포인트 설정이 여기에 표시됩니다.
                  </div>
                ) : (
                  <div>
                    {/* 변환된 Tool 헤더 */}
                    <div style={{ background: '#FFFFFF', padding: 14, borderRadius: 8, border: '1px solid #E2E8F0', marginBottom: 16 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: '#4F46E5' }}>변환 완료된 Tool</span>
                      <h4 style={{ margin: '4px 0', fontSize: 15, fontWeight: 700 }}>
                        {parsedTools[selectedParsedIndex].name}
                      </h4>
                      <code style={{ fontSize: 12, color: '#64748B' }}>
                        {parsedTools[selectedParsedIndex].tool_id}
                      </code>
                    </div>

                    {/* Dev & Prd 엔드포인트 분리 설정 패널 */}
                    <div style={{ background: '#FFFFFF', padding: 14, borderRadius: 8, border: '1px solid #E2E8F0', marginBottom: 16 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', marginBottom: 10 }}>
                        🌐 배포 승인 상태별 엔드포인트 분기 설정 (T-035)
                      </div>

                      <div style={{ marginBottom: 10 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: '#166534' }}>🧪 개발용 (Dev/Draft 상태 호출)</span>
                        <input
                          type="text"
                          value={devEndpoint}
                          onChange={e => setDevEndpoint(e.target.value)}
                          placeholder="개발계 엔드포인트 URL"
                          style={{ width: '100%', padding: '6px 10px', fontSize: 12, borderRadius: 6, border: '1px solid #CBD5E1', marginTop: 4, boxSizing: 'border-box' }}
                        />
                      </div>

                      <div>
                        <span style={{ fontSize: 12, fontWeight: 700, color: '#1E40AF' }}>🚀 운영용 (Approved 배포완료 시 호출)</span>
                        <input
                          type="text"
                          value={prdEndpoint}
                          onChange={e => setPrdEndpoint(e.target.value)}
                          placeholder="운영계 엔드포인트 URL"
                          style={{ width: '100%', padding: '6px 10px', fontSize: 12, borderRadius: 6, border: '1px solid #CBD5E1', marginTop: 4, boxSizing: 'border-box' }}
                        />
                      </div>
                    </div>

                    {/* 즉시 호출 테스트 패널 */}
                    <div style={{ background: '#FFFFFF', padding: 14, borderRadius: 8, border: '1px solid #E2E8F0', marginBottom: 16 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                        <span style={{ fontSize: 12, color: '#64748B' }}>개발 프로파일 모의 실행 · 운영 호출 불가</span>
                      </div>

                      <textarea
                        value={testArgs}
                        onChange={e => setTestArgs(e.target.value)}
                        rows={4}
                        style={{
                          width: '100%',
                          fontFamily: 'monospace',
                          fontSize: 11,
                          padding: 8,
                          borderRadius: 6,
                          border: '1px solid #CBD5E1',
                          boxSizing: 'border-box',
                          marginBottom: 8
                        }}
                      />

                      <button
                        type="button"
                        onClick={handleTestInvoke}
                        disabled={invoking}
                        style={{
                          background: '#0F172A',
                          color: '#FFFFFF',
                          border: 'none',
                          padding: '8px 14px',
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 700,
                          cursor: invoking ? 'not-allowed' : 'pointer'
                        }}
                      >
                        {invoking ? '호출 중...' : '▶ 선택 환경으로 동적 라우팅 테스트 실행'}
                      </button>

                      {testResult && (
                        <div style={{ marginTop: 10, padding: 10, background: '#F8FAFC', borderRadius: 6, border: '1px solid #E2E8F0' }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: '#166534', marginBottom: 4 }}>
                            🧪 [개발 프로파일 모의 결과] ({testResult.duration_ms}ms)
                          </div>
                          <code style={{ fontSize: 11, color: '#334155', display: 'block', marginBottom: 4 }}>
                            선택된 모의 프로파일: {testResult.routed_endpoint}
                          </code>
                          <pre style={{ margin: 0, fontSize: 11, fontFamily: 'monospace', maxHeight: 120, overflow: 'auto', background: '#0F172A', color: '#38BDF8', padding: 8, borderRadius: 4 }}>
                            {JSON.stringify(testResult.result, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>

                    {/* 최종 등록 버튼 */}
                    <button
                      type="button"
                      onClick={handleFinalRegister}
                      disabled={registering}
                      style={{
                        width: '100%',
                        background: 'linear-gradient(135deg, #059669 0%, #10B981 100%)',
                        color: '#FFFFFF',
                        border: 'none',
                        padding: '12px',
                        borderRadius: 8,
                        fontSize: 14,
                        fontWeight: 700,
                        cursor: registering ? 'not-allowed' : 'pointer',
                        boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)'
                      }}
                    >
                      {registering ? '등록 중...' : '💾 모의 Tool 등록'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
