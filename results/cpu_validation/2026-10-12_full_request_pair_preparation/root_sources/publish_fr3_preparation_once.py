"""Publish the reviewed FR3 sources and seal its first new checks once."""
from pathlib import Path
import ast
import hashlib
import json
import re

root=Path(__file__).resolve().parents[1]
candidate=root/'external/fr3_candidate'
dest=root/'results/cpu_validation/2026-10-12_full_request_pair_preparation'
assert not dest.exists()
contract=json.loads((root/'external/fr3_first_mapping_contract/contract.json').read_bytes())
assert contract['status']=='passed' and not contract['failures']
mapping={
 'full_request_pair_mpc.py':('src/developmental_physics/full_request_pair_mpc.py','7d364c819e464beb1375158df7a6e78ee17a4e71986e6afa59fb492c39257e55'),
 'full_request_pair_development.py':('src/developmental_physics/full_request_pair_development.py','eb76b2100dc04bcec6230a076312a689bb132b1c462a3c2098a981e790c32cd9'),
 'develop_full_request_pair.py':('scripts/develop_full_request_pair.py','b274fdd03194c12bd4035b73313076bd6d8db6ae9cf3ec9290fd040a41e58a91')}
pins, published={},{}
def identity(data):
 return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def save(name,data):
 target=dest/name
 target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('xb') as stream:stream.write(data)
 pins[name]=identity(data)
dest.mkdir()
for name,(target_name,sha) in mapping.items():
 source=(candidate/name).read_bytes()
 assert identity(source)['sha256']==sha
 target=root/target_name
 assert not target.exists(),target_name
 normalized=source.replace(b'\r\n',b'\n')
 assert ast.dump(ast.parse(source),include_attributes=False)==ast.dump(ast.parse(normalized),include_attributes=False)
 with target.open('xb') as stream:stream.write(normalized)
 published[target_name]={'original':identity(source),'published':identity(normalized),'AST_equal':True}
for path in sorted(candidate.glob('*')):
 if path.is_file():save('external_originals/'+path.name,path.read_bytes())
for path in sorted((root/'external/fr3_first_mapping_contract').glob('*')):
 if path.is_file():save('first_mapping_contract/'+path.name,path.read_bytes())
for name in ('fr3_seed_qualification.json','fr3_control_design.md','run_fr3_mapping_first_once.py',
             'run_fr3_first_once.py','archive_fr3_first_once.py','publish_fr3_preparation_once.py'):
 save('root_sources/'+name,(root/'external'/name).read_bytes())
protocol=(root/'docs/FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md').read_bytes()
save('protocol.md',protocol)
save('static_review.json',(json.dumps({'reviewer':'checkpoint_review','scope':'controller/collector/runner/protocol/new_fixture static only',
 'concrete_contract_errors_found':0,'raw_or_model_parameter_reads':0,'executions':0,
 'final_fixture_revision':'scope wording and predicted-first label only; no case or numerical changes'},indent=2)+'\n').encode())
save('publication.json',(json.dumps({'published':published,'protocol':identity(protocol),
 'normalization_only_no_logic_change':True,'first_mapping_contract_passed':True,
 'new_checks':len(contract['checks']),'new_pair_attempts':contract['cost']['new_mapping_contract_pair_prediction_attempts'],
 'new_scalar_attempts':contract['cost']['new_mapping_contract_scalar_prediction_attempts'],
 'physics_or_fit_or_RLS_or_old_experiments':0},indent=2)+'\n').encode())
entry='[FR3完整首请求网格协议](FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md)已与新scalar/batch、collector/runner一并准备；首次新参数化契约672项通过，48,762pair/97,524scalar前向、0物理/fit/RLS。固定开发seed8001/8002/8003，先原配方FR3A辨识/独立预测，全门通过才执行已冻FR3B；旧FR2失败保留，原20%/5%/努力门不改。最终±.5Nm、首10微步反馈/140PD尾保留；新delta可达±1、网格变粗且一般无purePD候选为新增先验。C4及C5–C7仍未验收，持续目标active，提交推送后立即首次执行。'
def replace_para(text,start,new):
 assert start in text,start
 old=start+text.split(start,1)[1].split('\n\n',1)[0]
 assert text.count(old)==1
 return text.replace(old,new,1)
rooted=entry.replace('](FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md)','](docs/FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md)')
for name in ('AGENTS.md','README.md','docs/CONTINUOUS_EXECUTION_PLAN.md','docs/CPU_VALIDATION_TARGET.md','docs/PROGRESS.md'):
 p=root/name;text=p.read_text(encoding='utf-8')
 if name=='AGENTS.md':
  text=replace_para(text,'[FR2首次自由root匹配控制]',rooted)
 elif name=='README.md':
  text=replace_para(text,'**当前执行入口：**','**当前执行入口：** '+rooted)
 elif name=='docs/CONTINUOUS_EXECUTION_PLAN.md':
  text=replace_para(text,'- **FR2首次结果：**','- **当前入口FR3：** '+entry)
  text+='\n\n### FR2动作描述后唯一FR3候选\n\n'+entry+'\n\n[一次保存动作诊断](FREE_ROOT_PAIR_AUTHORITY_RESULTS.md)不识别失败原因，不重算旧科学门；新bank先自辨识，不恢复旧参数。\n'
 elif name=='docs/CPU_VALIDATION_TARGET.md':
  text=replace_para(text,'[FR2首次自由root匹配控制]',entry)
  text=replace_para(text,'已冻结FR2比较','新FR3仅检验一个完整首请求参数化修订；预测与控制都在新数据前冻结。C4验收后依次进入C5未知动力学适应、C6成熟机制和C7新留出综合验收。')
 else:
  text=text.replace('## 当前入口：FR2首次完整匹配控制结果','## 历史：FR2首次完整匹配控制结果',1)
  marker='# 开发进度与仓库检查点\n\n'
  assert marker in text
  text=text.replace(marker,marker+'## 当前入口：FR3完整首请求网格准备与首次执行\n\n'+entry+'\n\n',1)
 p.write_text(text,encoding='utf-8',newline='\n')
links=[]
for name in ('docs/FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md','docs/FREE_ROOT_PAIR_AUTHORITY_RESULTS.md'):
 p=root/name
 for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
  if '://' in target or target.startswith('#'):continue
  exists=(p.parent/target.split('#',1)[0]).resolve().is_file()
  links.append({'document':name,'target':target,'exists':exists})
assert all(item['exists'] for item in links)
save('navigation_checks.json',(json.dumps({'checks':len(links),'failed':0,'links':links},indent=2)+'\n').encode())
save('manifest.json',(json.dumps({'files_before_manifest':pins.copy(),'published':published,
 'first_mapping_contract':'passed','scientific_adoption':False,'new_physics':0,
 'continuous_goal_stays_active':True},ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({'published':published,'first_new_fixture_checks':len(contract['checks']),
 'archived_payloads_before_manifest':len(pins)-1,'new_links_checked':len(links),'new_physics_or_fit_or_RLS':0}))
