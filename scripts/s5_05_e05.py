import json, hashlib, datetime, subprocess, sys, os, time
from pathlib import Path
from catalyst_ai.modeling.s5_selection import select
from catalyst_ai.modeling.research_preflight import preflight
from catalyst_ai.workbench import backup,index,service
from catalyst_ai.storage.workbench import atomic_operations
R=Path(__file__).resolve().parents[1]; O=R/'artifacts/reports/s5-05-e05-20261124-v1'; DB=R/'data/workbench.sqlite'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
ET={'n_estimators':100,'min_samples_leaf':2,'max_depth':None,'max_features':1.0,'n_jobs':1}
P={'extra_trees':[ET,dict(ET,max_depth=8),dict(ET,min_samples_leaf=4,max_features=.7)],'random_forest':[ET,dict(ET,max_depth=8),dict(ET,min_samples_leaf=4,max_features=.7)],'xgboost':[{'n_estimators':100,'max_depth':3,'learning_rate':.1},{'n_estimators':150,'max_depth':2,'learning_rate':.05},{'n_estimators':100,'max_depth':2,'learning_rate':.1}]}
def init():
 O.mkdir(parents=True,exist_ok=False); (O/'configs').mkdir()
 (O/'preregistration.md').write_text('''# S5-E05 可执行预登记 v1

2026-11-24，北京时间。用户批准 XGBoost 用于 S5-05。已观察 S5 和历史留出结果，所有评价均为内部探索性评价，不构成独立验证；参数列表不依据这些成绩。原 S5-04 结论不变。

三次分组随机划分 45/46/47，模型种子 42，每个划分仅使用本划分训练数据及五折。F3 的选择仅依赖已归档 S5-02 同种子 E01 训练 OOF：对 F_base/ET 和 F3-P、F3-H、F3-I/ET 用 s5-paired-v1 判断资格，在全部合格臂的共同可用 OOF 集上选 MAE 最小的合格 F3，0.1 百分点平局依 P、H、I 顺序；若无合格 F3 或共同支持不足则中止并记录缺口。记录输入散列、完整判定和选定特征。

每种子有 F_base、该 F3 各配 ET、RF、XGBoost，每个组合三套参数，共 18 臂，其中首臂固定 F_base/ET 基线；参数明细见三个配置。ET/RF 三套与 S5-04 同目录；XGBoost n_estimators 100–150、max_depth 2–3、learning_rate 0.05–0.1，恰三组，固定其他实现默认值；每算法每特征同样三组，单线程、不早停。总预算最多 270 次折拟合与 54 次全训练拟合，三次训练每次限时 1800 秒；失败或超时保存记录并中止，不用留出修改配置。每次按 s5-paired-v1 训练 OOF MAE 在全部候选间选择，准入、共同支持、0.1 pp 平局及基线回退沿用 S5-01；R² 不参与选模。每种子完整 18 个报告臂、选中臂和基线均留痕。全部三种子训练和选择锁定后，才逐种子一次性评分全部报告臂；只在相同种子同成员逐记录配对。留出指标仅报告；不存在跨种子留出反馈。种子间数据重叠且结果相关。

分别报告诊断、入口可用、严格共同可用及全留出分母；MAE、RMSE、R²、DOI 等权 MAE、覆盖率、折及种子稳定性、偏差、分层与失败原因。R² 在样本不足或目标为常数时为空并说明。优先引用已有同模型锁和留出清单的结果；新实验使用同样目录以实现训练内统一比较，若拟合重复应披露。外部独立验证尚待新来源。
''',encoding='utf8')
 selection={}
 for seed in (45,46,47):
  folder='s5-02-e01-20261124-v1' if seed==45 else f's5-02-e01-seed{seed}-20261124-v1'
  path=R/'artifacts/reports'/folder/'run/cross_validation.json'; cv=read(path); arms=[cv['results'][i] for i in (0,4,5,6)]; d=select(arms)
  eligible=[i for i in (1,2,3) if d['comparisons'][i]['eligible']]; ids=d.get('selection_common_ids',[])
  if not eligible or len(ids)<d['minimum_common']:raise ValueError('F3 training support insufficient')
  values={i:d['selection_common_mae'][str(i)] if str(i) in d['selection_common_mae'] else d['selection_common_mae'][i] for i in eligible}; best=min(values.values()); i=min(i for i in eligible if values[i]<=best+.1+1e-12); feature=arms[i]['candidate']['feature']
  selection[str(seed)]={'e01_oof_path':path.relative_to(R).as_posix(),'sha256':sha(path),'decision':d,'f3_mae':values,'chosen':feature}
  candidates=[]
  for feature_name in ('F_base',feature):
   for algorithm in ('extra_trees','random_forest','xgboost'):
    for params in P[algorithm]:candidates.append({'feature':feature_name,'model':algorithm,'params':params})
  cfg=read(R/f'artifacts/reports/s5-03-start-20261124/a-{seed}.json');cfg.update(candidates=candidates,metrics=['mae','rmse','r2','availability'],outputs=['predictions'],selection_rule='s5-paired-v1');write(O/'configs'/f'{seed}.json',cfg)
 write(O/'f3-training-selection.json',selection)
 write(O/'preregistration-sha256.json',{p.relative_to(R).as_posix():sha(p) for p in [O/'preregistration.md',O/'f3-training-selection.json',*sorted((O/'configs').glob('*.json'))]})
def verify_register():
 checks={}
 for seed in (45,46,47):
  v=preflight(O/'configs'/f'{seed}.json',root=R); checks[str(seed)]={'counts':v['counts'],'hashes':v['hashes']}
 proc=subprocess.run([sys.executable,'-m','pytest','-q','tests/unit/test_s5_xgboost.py','tests/unit/test_s5_estimators.py','tests/unit/test_s5_metrics.py','tests/unit/test_s5_selection.py'],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=180)
 (O/'preexperiment-tests.log').write_text(proc.stdout+'\n'+proc.stderr,encoding='utf8'); assert proc.returncode==0
 official=R/'artifacts/reports/s5-04-xgboost-official-20261124-v1'; sources=[official/'synthetic/result.json',official/'synthetic/release-result.json',official/'partition-validation/verification.json']
 write(O/'preexperiment-verification.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'preflight':checks,'tests_exit':proc.returncode,'tests_sha256':sha(O/'preexperiment-tests.log'),'prior_synthetic_and_partition_proofs':{p.relative_to(R).as_posix():sha(p) for p in sources},'note':'E05 full candidate preflight; existing S5-04 synthetic and release evidence reused before E05 training.'})
 backup.backup_database(DB,O/'workbench-before.sqlite');backup.backup_database(O/'workbench-before.sqlite',O/'workbench-rehearsal.sqlite')
 files={'S5-05-E05-prereg-v1':O/'preregistration.md','S5-05-E05-config-hashes-v1':O/'preregistration-sha256.json','S5-05-E05-F3-selection-v1':O/'f3-training-selection.json','S5-05-E05-preflight-v1':O/'preexperiment-verification.json','S5-05-E05-tests-v1':O/'preexperiment-tests.log'}
 for seed in (45,46,47):files[f'S5-05-E05-config-{seed}-v1']=O/'configs'/f'{seed}.json'
 def reg(db):
  with atomic_operations(db):
   assert service.get_task(db,'S5-05')['status']=='in_progress'
   for key,p in files.items():index.register(db,'cat-ai',key,'document' if p.suffix=='.md' else 'attachment',p.relative_to(R).as_posix(),request_id='s5-e05-v1:register:'+key,actor='Codex')
   index.scan(db,'cat-ai',document_ids=list(files))
  import sqlite3
  with sqlite3.connect(db) as c: assert c.execute('pragma quick_check').fetchone()[0]=='ok' and not c.execute('pragma foreign_key_check').fetchall()
 reg(O/'workbench-rehearsal.sqlite');reg(DB)
 write(O/'registration-receipt.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{k:{'path':v.relative_to(R).as_posix(),'sha256':sha(v)} for k,v in files.items()},'status':'registered in formal workbench after rehearsal'})
def run():
 receipt=read(O/'registration-receipt.json'); assert all(sha(R/v['path'])==v['sha256'] for v in receipt['files'].values())
 env=os.environ.copy()
 for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[k]='1'
 trace=[]
 for seed in (45,46,47):
  start=time.monotonic(); name=f'run-{seed}'
  try:r=subprocess.run([sys.executable,str(R/'scripts/run_research_experiment.py'),'train',str(O/'configs'/f'{seed}.json'),'--output',str(O/name)],cwd=R,env=env,capture_output=True,text=True,encoding='utf8',timeout=1800); (O/f'{name}.log').write_text(r.stdout+'\n'+r.stderr,encoding='utf8');status=r.returncode
  except subprocess.TimeoutExpired as e:(O/f'{name}.log').write_text(str(e),encoding='utf8');status='timeout'
  trace.append({'seed':seed,'exit':status,'seconds':time.monotonic()-start});write(O/'training-trace.json',trace)
  if status!=0:raise RuntimeError('training failed; no holdout scoring')
 for seed in (45,46,47):
  name=f'run-{seed}';r=subprocess.run([sys.executable,str(R/'scripts/run_research_experiment.py'),'score',str(O/name)],cwd=R,env=env,capture_output=True,text=True,encoding='utf8',timeout=1800);(O/f'{name}.score.log').write_text(r.stdout+'\n'+r.stderr,encoding='utf8')
  if r.returncode:raise RuntimeError(f'{name} scoring failed')
if __name__=='__main__': {'init':init,'verify-register':verify_register,'run':run}[sys.argv[1]]()
