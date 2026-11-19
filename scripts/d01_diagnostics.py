import csv, json, hashlib, sys, platform, statistics, collections, math, importlib.metadata
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def read(p): return json.loads((R/p).read_text(encoding='utf8'))
def sha(p): return hashlib.sha256((R/p).read_bytes()).hexdigest()
def dump(x): return json.dumps(x,ensure_ascii=False,sort_keys=True)
paths=['artifacts/runs/s3-20261118-01/r2/report.json','artifacts/models/s3-20261118-01/r2/manifest.json','artifacts/models/s3-20261118-01/r2/model.pkl','artifacts/reports/s3-01-20261118-01/r2-predictions.csv','artifacts/reports/s3-01-20261118-01/inputs.json','artifacts/reports/s3-02-20261118-02a/formal-r2-checks.json','artifacts/reports/s1-b-20261113-v4/features.json','artifacts/reports/themecat-i2-20261110/split-verified.json','configs/s3_20261118_01_r2.yaml','scripts/d01_diagnostics.py']
report=read(paths[0]); manifest=read(paths[1]); replay=read(paths[5]); feats=read(paths[6])['content']['rows']; features={r['record_id']:r for r in feats}; assert len(features)==len(feats)
assert report['selected']=={'feature_set':'F_base','model':'extra_trees'} and manifest['report_sha256']==report['content_sha256']
checks={r['record_id']:r for r in replay}; assert len(checks)==len(replay)==47
train=set(manifest['training_record_ids']); folds={f['fold']:set(f['training_record_ids']) for f in report['fold_details']}; rows=[]
with (R/paths[3]).open(encoding='utf-8-sig',newline='') as f: csvrows=list(csv.DictReader(f))
for part, preds in [('validation',report['validation']['candidates']['F_base/extra_trees']['predictions']),('oof',report['oof_predictions']['F_base']['extra_trees'])]:
 selected=[x for x in csvrows if (x['feature'],x['model'],x['partition'])==('F_base','extra_trees',part)]
 assert len(selected)==len(preds)==(47 if part=='validation' else 454)
 by={x['record_id']:x for x in selected}; assert len(by)==len(preds) and set(by)=={p['record_id'] for p in preds}
 for p in preds:
  rid=p['record_id']; assert json.loads(by[rid]['diagnostics_json'])==p
  feat=features[rid]; comp=feat['composition']; cond=feat['conditions']; scope=train if part=='validation' else folds[p['fold']]
  keys={(c['role'],c['species']) for i in scope for c in features[i]['composition'] if c['material_mol_pct']>0}
  signature=sorted((c['role'],c['species'],c['material_mol_pct']) for c in comp if c['material_mol_pct']>0)
  known=all((a,b) in keys for a,b,_ in signature)
  seen_signature=any(signature==sorted((c['role'],c['species'],c['material_mol_pct']) for c in features[i]['composition'] if c['material_mol_pct']>0) for i in scope)
  assert known==p['fully_encoded']
  dims=[]
  for k,v in cond.items():
   vals=[features[i]['conditions'][k] for i in scope if features[i]['conditions'][k] is not None]
   if v is not None and vals and (v<min(vals) or v>max(vals)): dims.append(k)
  if part=='validation':
   c=checks[rid]; q=c['prediction']; assert c['training_row']==p and q['status']==p['status'] and q['unseen_species_roles']==p['unseen_species_roles'] and q['out_of_range']==p['out_of_range'] and q['model_id']==manifest['model_id']
   available=q['co2_conversion_pct']; assert (available is None)==(p['status']=='unsupported_species_role')
   if available is not None: assert math.isclose(available,p['raw_prediction'],abs_tol=1e-10)
  else: available=p['raw_prediction'] if p['status'] in ('ok','caution') else None
  rows.append(dict(partition=part,record_id=rid,doi=p['doi'],fold=p.get('fold',''),composition=dump(signature),species_roles=dump(sorted({(a,b) for a,b,_ in signature})),composition_seen=seen_signature,vocabulary_seen=known,conditions=dump(cond),condition_outside=dump(dims),status=p['status'],unseen_species_roles=dump(p['unseen_species_roles']),out_of_range=dump(p['out_of_range']),observed=p['observed'],diagnostic_prediction=p['raw_prediction'],available_prediction=available,diagnostic_abs_error=abs(p['observed']-p['raw_prediction']),available_abs_error=abs(p['observed']-available) if available is not None else None))
 assert collections.Counter(p['status'] for p in preds)==({'ok':26,'caution':2,'unsupported_species_role':19} if part=='validation' else {'ok':102,'caution':172,'unsupported_species_role':180})
assert {p['record_id'] for p in report['oof_predictions']['F_base']['extra_trees']}==train
out=Path(sys.argv[1]); out.mkdir(parents=True,exist_ok=False)
def csvwrite(name,rs):
 with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
csvwrite('row-review.csv',rows)
groups=collections.defaultdict(list)
for r in rows:
 labels=[('all','all'),('doi',r['doi']),('status',r['status']),('composition_seen',str(r['composition_seen'])),('vocabulary_seen',str(r['vocabulary_seen'])),('condition_range','outside' if json.loads(r['condition_outside']) else 'inside')]
 labels += [('species_role',f'{a}/{b}') for a,b in json.loads(r['species_roles'])]
 for kind,value in labels: groups[(r['partition'],kind,value)].append(r)
metrics=[]
for (part,kind,value),rs in sorted(groups.items()):
 av=[r for r in rs if r['available_abs_error'] is not None]
 def paper_mean(sub,key):
  ds=collections.defaultdict(list)
  for r in sub: ds[r['doi']].append(r[key])
  return statistics.mean(statistics.mean(v) for v in ds.values()) if ds else None
 metrics.append(dict(partition=part,group_type=kind,group=value,records=len(rs),dois=len({r['doi'] for r in rs}),available_records=len(av),available_dois=len({r['doi'] for r in av}),availability=len(av)/len(rs),diagnostic_mae=statistics.mean(r['diagnostic_abs_error'] for r in rs),diagnostic_paper_equal_mae=paper_mean(rs,'diagnostic_abs_error'),available_mae=statistics.mean(r['available_abs_error'] for r in av) if av else None,available_paper_equal_mae=paper_mean(av,'available_abs_error')))
csvwrite('group-metrics.csv',metrics)
inputs={'model_id':manifest['model_id'],'target_definition':manifest['target_definition'],'unit':'%','binding':manifest['binding'],'input_sha256':{p:sha(p) for p in paths},'environment':{'python':sys.version,'platform':platform.platform(),'training_dependencies':manifest['dependencies'],'diagnostic_packages':{n:importlib.metadata.version(n) for n in ['numpy','scikit-learn']}},'code':'scripts/d01_diagnostics.py'}
(out/'inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
lines=['# D-01 基线与失败归因','',f"模型：{manifest['model_id']}；F_base / ExtraTrees。目标为 CO₂ 转化率，误差单位为百分点。",'', '依据 S3 保存的折外词表状态及预测，验证集使用最终训练包的入口重放；不是独立评估。每组均给出记录和 DOI 数，论文等权 MAE 先在 DOI 内平均。拒绝记录仅保留诊断预测，不计入可用预测误差。', '', '| 分区 | 记录 / DOI | 可用 | 诊断 MAE | 可用 MAE | 论文等权诊断 MAE |', '|---|---:|---:|---:|---:|---:|']
for m in metrics:
 if m['group_type']=='all': lines.append(f"| {m['partition']} | {m['records']} / {m['dois']} | {m['available_records']} ({m['availability']:.1%}) | {m['diagnostic_mae']:.3f} | {m['available_mae']:.3f} | {m['diagnostic_paper_equal_mae']:.3f} |")
lines += ['', '验证集状态为 26 ok、2 caution、19 unsupported_species_role；OOF 为 102、172、180。原因按记录逐项保存，多个原因可同时出现。工况范围按四项条件分别比较训练侧最小值与最大值；OOF 使用各折训练侧，验证使用完整训练侧。这是描述性分层，不是已验证适用域。物种角色分组可重叠，组间记录数不能相加。', '', '组分见过指正含量物种/角色均在对应训练词表中，并非完整配方曾出现。小组及 DOI 数见指标表，不宜外推。S3 入口 out_of_range 指组分维度，不等同工况范围。历史 test 未纳入此次诊断。', '', '逐条证据见 row-review.csv，分层指标见 group-metrics.csv；输入哈希与环境见 inputs.json。']
(out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print('D-01 completed')

