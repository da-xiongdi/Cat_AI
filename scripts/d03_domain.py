import csv, json, hashlib, sys, collections
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1]
def load(p): return json.loads((R/p).read_text(encoding='utf8'))
paths=['artifacts/runs/s3-20261118-01/r2/report.json','artifacts/models/s3-20261118-01/r2/manifest.json','artifacts/reports/s1-b-20261113-v4/features.json','artifacts/reports/d-01-20261118-03/row-review.csv','scripts/d03_domain.py']
report=load(paths[0]); manifest=load(paths[1]); features={x['record_id']:x for x in load(paths[2])['content']['rows']}
with (R/paths[3]).open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
dois={r['record_id']:r['doi'] for r in rows}; train=set(manifest['training_record_ids']); folds={str(f['fold']):set(f['training_record_ids']) for f in report['fold_details']}
assert set(dois)>=train and len(rows)==501
conditions=['temperature_k','pressure_bar_abs','h2_co2_ratio','reactants_flow_nl_g_h']
def vector(rid):
 d=collections.defaultdict(float)
 for c in features[rid]['composition']: d[(c['role'],c['species'])]+=c['material_mol_pct']/100
 return d
def cd(a,b): return sum(abs(a.get(k,0)-b.get(k,0)) for k in a.keys()|b.keys())
vec={rid:vector(rid) for rid in dois}
def build(ids):
 ids=sorted(ids); a=np.array([[features[i]['conditions'].get(k) if features[i]['conditions'].get(k) is not None else np.nan for k in conditions] for i in ids],float)
 med=np.nanmedian(a,axis=0); q=np.nanpercentile(a,[25,75],axis=0); scale=q[1]-q[0]; scale[scale==0]=1
 def dist(rid, exclude_doi=False):
  candidates=[i for i in ids if not exclude_doi or dois[i]!=dois[rid]]
  if not candidates: raise ValueError('No independent DOI in training reference')
  dc=min(cd(vec[rid],vec[i]) for i in candidates)
  v=np.array([features[rid]['conditions'].get(k) if features[rid]['conditions'].get(k) is not None else np.nan for k in conditions],float)
  valid=[i for i in candidates if all(features[i]['conditions'].get(k) is not None for k in conditions)]
  if not np.isfinite(v).all() or not valid: dw=None
  else: dw=min(float(np.max(np.abs((v-np.array([features[i]['conditions'][k] for k in conditions]))/scale))) for i in valid)
  return dc,dw
 samples=[dist(i,True) for i in ids]; c=[x[0] for x in samples]; w=[x[1] for x in samples if x[1] is not None]
 thresholds={'composition':list(map(float,np.quantile(c,[.90,.99]))),'conditions':list(map(float,np.quantile(w,[.90,.99])))}
 return dist,{'records':len(ids),'dois':len({dois[i] for i in ids}),'condition_iqr':dict(zip(conditions,map(float,scale))),'condition_median':dict(zip(conditions,map(float,med))),'thresholds':thresholds,'calibration_condition_records':len(w)}
models={}; models['final']=build(train)
for fold,ids in folds.items():
 assert all(dois[i]!=dois[j] for i in ids for j in train-ids)
 models[fold]=build(ids)
for r in rows:
 scope='final' if r['partition']=='validation' else r['fold']; dist,info=models[scope]; reasons=[]
 if r['status']=='unsupported_species_role': label='outside'; reasons.append('unsupported_species_role') ; dc=dw=None
 else:
  dc,dw=dist(r['record_id']); t=info['thresholds']; label='inside'
  if r['status']=='caution': label='warning'; reasons.append('existing_caution')
  for name,value in [('composition',dc),('conditions',dw)]:
   if value is None: label='warning' if label=='inside' else label; reasons.append(name+'_unassessable')
   elif value>t[name][1]: label='outside'; reasons.append(name+'_above_p99')
   elif value>t[name][0]: label='warning' if label=='inside' else label; reasons.append(name+'_above_p90')
 r.update(candidate_label=label,candidate_reasons=json.dumps(reasons,ensure_ascii=False),composition_distance=dc,condition_distance=dw,reference_scope=scope)
out=Path(sys.argv[1]); out.mkdir(parents=True,exist_ok=False)
def write(name,rs):
 with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
write('row-domain.csv',rows)
metrics=[]
for part in ['oof','validation']:
 sub=[r for r in rows if r['partition']==part]
 for scheme,labels in [('baseline',['ok','caution','unsupported_species_role']),('candidate',['inside','warning','outside'])]:
  for label in labels:
   group=[r for r in sub if r['status' if scheme=='baseline' else 'candidate_label']==label]; av=[r for r in group if r['available_abs_error']!='']; by=collections.defaultdict(list)
   for r in av: by[r['doi']].append(float(r['available_abs_error']))
   metrics.append(dict(partition=part,scheme=scheme,label=label,records=len(group),dois=len({r['doi'] for r in group}),coverage=len(group)/len(sub),available_records=len(av),available_dois=len(by),available_mae=float(np.mean([float(r['available_abs_error']) for r in av])) if av else None,paper_equal_available_mae=float(np.mean([np.mean(v) for v in by.values()])) if by else None))
write('group-metrics.csv',metrics)
rule={'version':'d03-candidate-v1','model_id':manifest['model_id'],'scope':'diagnostic only; existing prediction interface unchanged','composition':'L1 distance over role/species material_mol_pct / 100; no closure normalization','conditions':'nearest complete training row, maximum absolute coordinate difference divided by training IQR; zero IQR replaced by 1 in native unit','thresholds':'90th and 99th percentiles of training-row nearest distances excluding same DOI, separately per reference scope; >99 outside, >90 warning','precedence':'unsupported outside; otherwise either metric above p99 outside, p90 or existing caution or missing conditions warning, else inside','reference':{k:v[1] for k,v in models.items()},'input_sha256':{p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in paths}}
(out/'rule.json').write_text(json.dumps(rule,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
lines=['# D-03 适用域候选规则','', '候选版本 d03-candidate-v1，仅供诊断，不改变预测入口。阈值按训练侧跨 DOI 最近邻距离的 90%、99% 分位数预先确定，不使用误差标签；OOF 每折单独拟合，验证集使用完整训练侧。标签不是独立验证结论。详细坐标、尺度、阈值和输入哈希见 rule.json。', '', '| 分区 | 规则 | 标签 | 记录 / DOI | 覆盖率 | 可用记录 / DOI | 可用论文等权 MAE（百分点） |','|---|---|---|---:|---:|---:|---:|']
for m in metrics: lines.append(f"| {m['partition']} | {m['scheme']} | {m['label']} | {m['records']} / {m['dois']} | {m['coverage']:.1%} | {m['available_records']} / {m['available_dois']} | {m['paper_equal_available_mae']:.3f} |" if m['paper_equal_available_mae'] is not None else f"| {m['partition']} | {m['scheme']} | {m['label']} | {m['records']} / {m['dois']} | {m['coverage']:.1%} | {m['available_records']} / {m['available_dois']} | — |")
lines += ['', '分组的可用 MAE 仅含原入口提供预测的记录；域外仍可能有入口可用预测。记录级原因包括原入口拒绝和候选触发项，原始原因字段保留在逐条表中。样本及 DOI 数较少，距离阈值是经验分位数，不能解释为失效概率；最近邻及阈值均依赖训练数据分布。缺失工况标记为不可评估并警示。历史 test 和独立数据未用于拟合或评估。']
(out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print('D-03 completed',out)
