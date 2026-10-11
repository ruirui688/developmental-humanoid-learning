"""One-time stdlib publication of reviewed FR learning candidates, before data."""
from pathlib import Path
import ast
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / 'results/cpu_validation/2026-10-12_free_root_pair_prediction_preparation'
assert not PREP.exists(), 'first preparation output already exists'
PREP.mkdir(parents=True)
reads = []
writes = []
def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
def read(relative):
    data = (ROOT / relative).read_bytes()
    reads.append({'path': relative, **pin(data)})
    return data
def put(relative, data):
    destination = ROOT / relative
    assert not destination.exists(), relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    writes.append({'path': relative, **pin(data)})
def lf(data):
    return data.decode('utf-8').replace('\r\n', '\n')
base = 'results/cpu_validation/2026-10-12_free_root_pair_prediction_preparation'
collector_path = 'external/c4_free_learning_candidate/free_root_pair_development.py'
original = read(collector_path)
put(base + '/reviewed_originals/free_root_pair_development.py', original)
collector = lf(original)
assert collector.count('"maximum_endpoint_normal_force_n": max(sums, default=0.)') == 1
collector = collector.replace('"maximum_endpoint_normal_force_n": max(sums, default=0.)',
    '"maximum_endpoint_normal_force_n": max(sums) if sums else None,\n'
    '                "maximum_scope": "observed_endpoints_only_partial_is_not_full_maximum"')
collector = collector.replace('from .fast_feedback_pair_mpc import FastFeedbackResidualPDPairMPC, public_pd_request',
    'from .fast_feedback_pair_mpc import public_pd_request\n'
    'from .batched_fast_feedback_pair_mpc import BatchedFastFeedbackResidualPDPairMPC')
collector = collector.replace('controller = FastFeedbackResidualPDPairMPC(models[name], current["public_joint_ranges2"])',
    'controller = BatchedFastFeedbackResidualPDPairMPC(models[name], current["public_joint_ranges2"],\n'
    '                                                              counted_model_type=CountedGuardModel)')
collector = collector.replace('"pair_update_accounting", "pair_prediction_accounting", "pair_planning_accounting"',
    '"pair_update_accounting", "pair_prediction_accounting", "pair_planning_accounting", "batch_execution_cost"')
needle = '                            raise\n                        cost["MPC_decision_returns"] += 1'
assert collector.count(needle) == 1
collector = collector.replace(needle,
    '                            raise\n'
    '                        finally:\n'
    '                            batch = dict(getattr(controller, "last_batch_execution", {}))\n'
    '                            current.setdefault("batch_execution_records", []).append(\n'
    '                                {"active_index": index, **batch})\n'
    '                            for key, value in batch.items():\n'
    '                                cost["planning_batch_"+key] += value\n'
    '                        cost["MPC_decision_returns"] += 1')
ast.parse(collector)
for label, text in [('before', lf(original)), ('after', collector)]:
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == 'CountedGuardModel')
    if label == 'before':
        counted = ast.dump(node, include_attributes=False)
    else:
        assert ast.dump(node, include_attributes=False) == counted
put('src/developmental_physics/free_root_pair_development.py', collector.encode())
batch_original = read('external/batch_fast_feedback_candidate/batched_fast_feedback_pair_mpc.py')
put(base + '/reviewed_originals/batched_fast_feedback_pair_mpc.py', batch_original)
batch = lf(batch_original)
assert ast.dump(ast.parse(batch), include_attributes=False) == ast.dump(ast.parse(batch_original), include_attributes=False)
put('src/developmental_physics/batched_fast_feedback_pair_mpc.py', batch.encode())
tests = read('external/c4_free_learning_candidate/test_free_root_pair_collection.py')
put(base + '/reviewed_originals/test_free_root_pair_collection.py', tests)
put('tests/test_free_root_pair_collection.py', lf(tests).encode())
protocol_original = read('external/FREE_ROOT_LEARNING_PROTOCOL_CANDIDATE.md')
put(base + '/reviewed_originals/FREE_ROOT_LEARNING_PROTOCOL_CANDIDATE.md', protocol_original)
protocol = lf(protocol_original)
protocol = protocol.replace('事前外部候选，尚未生产发布/执行。', '事前冻结协议；在任何FR1新数据前发布，尚未正式物理执行。')
start = protocol.index('批候选实现由其他代理另准备，**本候选默认不采用**。')
end = protocol.index('\n\n**模型贡献门：**', start)
protocol = protocol[:start] + (
    '本协议在FR1任何新数据前采用 `BatchedFastFeedbackResidualPDPairMPC`，'
    '显式传入新collector的CountedGuardModel。首次固定11项合成检查全部通过，'
    '共154,062 pair /307,962 scalar attempts；完整决策的JSON浮点表示与Counter精确一致。'
    '零物理/fit/RLS/快照恢复。实现只批PD/guard/features，仍逐head原九元dot及逐轴Python代价，'
    '81/H150、tie、feasible、fallback与所有原门不变。新实现、原规范、Counted类及依赖身份共同冻结。'
    '生产LF规范化不改AST；首次检查的原字节与生产映射封存。'
    '逐决策保存实际batch阶段/feature行/dot与scalar fallback次数；逻辑前向仍逐pair/scalar计，'
    '未知/覆写模型走原scalar实现。异步中断的实际执行前缀随stage顺序变化，保留实际费用、不重试，'
    '不宣称中断前缀等价或20ms实时。不能在FR1揭晓后替换kernel或改网格/时距/代价。') + protocol[end:]
protocol = protocol.replace('拟生产协议 `docs/FREE_ROOT_LEARNING_PROTOCOL.md`', '生产协议 `docs/FREE_ROOT_LEARNING_PROTOCOL.md`')
put('docs/FREE_ROOT_LEARNING_PROTOCOL.md', protocol.encode())
for source in (
    'external/batch_fast_feedback_check_01.json',
    'external/batch_fast_feedback_candidate/check_batched_fast_feedback_equivalence.py',
    'external/batch_fast_feedback_candidate/EQUIVALENCE_CHECK_DESIGN.md',
    'external/batch_fast_feedback_candidate/preparation_receipt.json',
    'external/free_root_learning_protocol_design_receipt.json',
    'external/c4_free_learning_candidate/collection_review_and_checks_preparation.json',
    'external/c4_free_learning_candidate/collector_preparation.json',
    'external/c4_free_learning_candidate/contact_revision_preparation.json'):
    data = read(source)
    put(base + '/external_originals/' + source.split('/')[-1], data)
put(base + '/publication_receipt.json', (json.dumps({
    'stage': 'before_FR1_data', 'reads': reads, 'writes_before_receipt': writes,
    'Counted_class_AST_unchanged': True, 'batch_AST_unchanged': True,
    'collector_revisions': ['missing-contact maximum None', 'pre-data batch adoption with actual counters'],
    'formal_physics': 0, 'model_fit_or_RLS': 0, 'no_seed_search_repeated': True,
    'batch_check': 'first_11_fixtures_all_passed', 'runner_published_separately_after_review': True
}, ensure_ascii=False, indent=2)+'\n').encode())
print(json.dumps({'published': len(writes), 'collector': pin(collector.encode()), 'protocol': pin(protocol.encode())}))
