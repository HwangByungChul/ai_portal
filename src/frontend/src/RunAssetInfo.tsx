import type {Run} from './types';
export function RunAssetInfo({binding}:{binding:Run['asset_binding']}){
 return <details className="scope-note"><summary>실행 버전 정보</summary>{binding?<dl>
  <dt>실행한 설정 버전</dt><dd>{binding.revision}</dd>
  <dt>자산 식별자</dt><dd style={{overflowWrap:'anywhere'}}>{binding.asset_id}</dd>
  <dt>버전 식별자</dt><dd style={{overflowWrap:'anywhere'}}>{binding.version_id}</dd>
  <dt>설정 지문</dt><dd style={{overflowWrap:'anywhere'}}>{binding.config_hash}</dd>
 </dl>:<p>실행 버전 정보가 기록되지 않은 기존 실행입니다.</p>}</details>;
}
