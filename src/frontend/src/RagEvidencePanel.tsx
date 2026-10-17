/**
 * [RAG 답변 출처 및 근거 패널 컴포넌트 - RagEvidencePanel]
 * AI가 RAG를 통해 답변을 완료한 후, 사용자가 답변 하단의 [근거 보기] 버튼을 클릭했을 때
 * 인용된 문서의 제목, 버전, 페이지/문단 위치, 실제 원문 인용문(quote)을 표시하고
 * 원본 문서를 다운로드할 수 있도록 지원하는 프론트엔드 UI 컴포넌트입니다.
 */
import { useEffect, useRef, useState } from 'react';
import { sourceBlob } from './api';
import { get, useScope } from './scoped';
import { DOCX_MEDIA_TYPE, XLSX_MEDIA_TYPE } from './types';
import type { Evidence } from './types';

export function RagEvidencePanel({
  tenantId,
  runId,
  onUnavailable
}: {
  tenantId: string;
  runId: string;
  onUnavailable: () => void;
}) {
  const ctx = useScope();
  // UI 상태 관리
  const [open, setOpen] = useState(false);                 // 근거 패널 열림/닫힘 상태
  const [loaded, setLoaded] = useState(false);             // 근거 데이터 로딩 완료 여부
  const [rows, setRows] = useState<Evidence[]>([]);        // 백엔드에서 조회해 온 증거(출처) 목록
  const [error, setError] = useState<string | null>(null); // 에러 메시지
  const [busy, setBusy] = useState(false);                 // 파일 다운로드 중복 클릭 방지 상태

  const active = useRef(false);
  const request = useRef<AbortController | null>(null);
  const urls = useRef(new Set<string>());

  // 메모리 정리 함수: 컴포넌트 종료 시 생성된 Blob URL 및 네트워크 요청 취소
  function dispose() {
    request.current?.abort();
    for (const url of urls.current) URL.revokeObjectURL(url);
    urls.current.clear();
  }

  useEffect(() => () => {
    active.current = false;
    dispose();
  }, []);

  // [1단계: 출처 데이터 비동기 조회]
  // 사용자가 '근거 보기' 버튼을 눌러 open 상태가 true가 되었을 때 실행
  useEffect(() => {
    if (!open) return;
    const c = new AbortController();
    request.current = c;
    const signal = AbortSignal.any([ctx.signal, c.signal]);
    let querying = false;

    async function load() {
      if (querying || document.visibilityState !== 'visible' || signal.aborted) return;
      querying = true;
      try {
        // 백엔드 API 호출: 해당 대화 실행(runId)에 사용된 증거 목록 조회
        const result = await get<{ items: Evidence[] }>('/runs/' + runId + '/evidence', { tenantId, signal });
        if (ctx.current() && !signal.aborted) {
          if (result.items.some(x => x.content_status === 'unavailable')) {
            setRows([]);
            onUnavailable();
          } else {
            setRows(result.items);
            setLoaded(true);
            setError(null);
          }
        }
      } catch (problem) {
        if (ctx.current() && !signal.aborted) {
          setRows([]);
          const message = await ctx.fail(problem, () => setRows([]));
          setError(message);
          onUnavailable();
        }
      } finally {
        querying = false;
      }
    }

    void load();
    // 5초 주기로 최신 증거 상태 동기화
    const timer = setInterval(() => void load(), 5000);
    const visible = () => void load();
    window.addEventListener('focus', visible);
    document.addEventListener('visibilitychange', visible);

    return () => {
      clearInterval(timer);
      c.abort();
      dispose();
      window.removeEventListener('focus', visible);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [open, runId]);

  // [2단계: 원본 파일 다운로드]
  // 인용된 원본 문서(PDF, Word, Excel 등)를 내려받아 확인 가능
  async function download(row: Evidence) {
    if (busy || row.source_url !== '/api/v1/runs/' + runId + '/evidence/' + row.ordinal + '/source') return;
    setBusy(true);
    setError(null);
    try {
      const signal = AbortSignal.any([ctx.signal, request.current!.signal]);
      const blob = await sourceBlob(runId, row.ordinal, { tenantId, signal }, row.source_media_type ?? 'text/plain');
      if (!ctx.current() || signal.aborted || !active.current) return;

      const url = URL.createObjectURL(blob);
      urls.current.add(url);
      const link = document.createElement('a');
      link.href = url;
      // 문서 확장자 결정
      link.download = row.source_media_type === XLSX_MEDIA_TYPE ? 'document.xlsx'
        : row.source_media_type === DOCX_MEDIA_TYPE ? 'document.docx'
        : row.source_media_type === 'application/pdf' ? 'document.pdf'
        : 'document.txt';
      link.click();
      setTimeout(() => {
        URL.revokeObjectURL(url);
        urls.current.delete(url);
      }, 1000);
    } catch (problem) {
      if (ctx.current()) {
        setRows([]);
        setError(await ctx.fail(problem, () => setRows([])));
        onUnavailable();
      }
    } finally {
      if (ctx.current()) setBusy(false);
    }
  }

  return (
    <section className="evidence-panel" aria-label="답변 근거">
      {/* 근거 열기/닫기 토글 버튼 */}
      <button
        type="button"
        className="secondary small"
        aria-expanded={open}
        onClick={() => {
          active.current = !open;
          if (open) {
            dispose();
            setRows([]);
            setLoaded(false);
          }
          setOpen(!open);
        }}
      >
        근거 {open ? '닫기' : '보기'}
      </button>

      {/* 근거 상세 카드 목록 */}
      {open && (
        <div>
          {error && <p role="alert">{error}</p>}
          {!rows.length && !error && (
            <p role="status">{loaded ? '현재 표시할 인용 근거가 없습니다.' : '표시할 근거를 확인하고 있습니다.'}</p>
          )}

          {rows.map(row => (
            <article key={row.ordinal} style={{ marginTop: '8px', padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
              {/* 1. 문서 제목 및 버전 번호 */}
              <strong>[{row.ordinal + 1}] {row.title} · v{row.version_no}</strong>

              {/* 2. 문서 내 위치 정보 (Word: 문단번호/표위치, Excel: 시트/셀, PDF: 페이지번호) */}
              <p style={{ color: '#64748b', fontSize: '0.9em', margin: '4px 0' }}>
                {(row.source_media_type === DOCX_MEDIA_TYPE || row.source_media_type === XLSX_MEDIA_TYPE)
                  ? row.structure_locations?.map(x =>
                      x.kind === 'paragraph' ? `본문 ${x.paragraph}문단`
                      : x.kind === 'table_cell' ? `표 ${x.table} · ${x.row}행 ${x.column}열`
                      : x.kind === 'cell' ? `시트 ${x.sheet_name} · ${x.cell}`
                      : `시트 ${x.sheet_name}`
                    ).join(' / ')
                  : row.source_media_type === 'application/pdf'
                  ? `원문 ${row.page_start}~${row.page_end}페이지`
                  : `원문 ${row.location?.line_start}~${row.location?.line_end}행`
                }
              </p>

              {/* 3. 실제 원문 인용구 스니펫 */}
              <blockquote style={{ margin: '6px 0', paddingLeft: '8px', borderLeft: '3px solid #3b82f6', color: '#334155' }}>
                {row.quote}
              </blockquote>

              {/* 4. 원본 파일 내려받기 버튼 */}
              <button type="button" className="secondary small" disabled={busy} onClick={() => void download(row)}>
                원문 내려받기
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
