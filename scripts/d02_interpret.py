import csv, hashlib, json, sys, platform
from pathlib import Path
import numpy as np
from catalyst_ai.modeling.predictor import load_package
from catalyst_ai.features.pipeline import CONDITIONS

R = Path(__file__).resolve().parents[1]
def read(p): return json.loads((R / p).read_text(encoding='utf-8'))
paths = ['artifacts/models/s3-20261118-01/r2/manifest.json','artifacts/models/s3-20261118-01/r2/model.pkl','artifacts/runs/s3-20261118-01/r2/report.json','data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json','artifacts/reports/d-01-20261118-03/row-review.csv','scripts/d02_interpret.py']
meta, fitted = load_package(R / 'artifacts/models/s3-20261118-01/r2')
report = read(paths[2]); snapshot = read(paths[3]); records = {r['record_id']: r for r in snapshot['content']['records']}
preds = report['validation']['candidates']['F_base/extra_trees']['predictions']
rows = [p for p in preds if p['status'] in ('ok','caution')]
with (R / paths[4]).open(encoding='utf-8-sig', newline='') as f: review = {r['record_id']:r for r in csv.DictReader(f) if r['partition']=='validation'}
assert len(preds)==47 and len(rows)==28 and all(review[p['record_id']]['status']==p['status'] for p in preds)
features, model = fitted['features'], fitted['model']
x = np.array([features.transform_one(records[p['record_id']]['payload'])['values'] for p in rows], dtype=float)
y = np.array([p['observed'] for p in rows]); baseline = model.predict(x)
assert np.allclose(baseline, [p['raw_prediction'] for p in rows], rtol=0, atol=1e-10)
names = list(CONDITIONS) + [f'{role}/{species}' for role,species in features.vocabulary]
assert x.shape[1] == len(names) == model.n_features_in_
groups = {name:[i] for i,name in enumerate(CONDITIONS)}
groups['composition_all'] = list(range(4,len(names)))
for role in sorted({r for r,s in features.vocabulary}): groups['role_'+role] = [i+4 for i,(r,s) in enumerate(features.vocabulary) if r==role]
base_mae = np.mean(abs(y-baseline)); rng = np.random.default_rng(20261118); results=[]
for group, cols in groups.items():
 for rep in range(50):
  perm = rng.permutation(len(rows)); altered=x.copy(); altered[:,cols]=x[perm][:,cols]
  mae=float(np.mean(abs(y-model.predict(altered))))
  results.append({'group':group,'repeat':rep+1,'mae':mae,'delta_mae':mae-base_mae})
out=Path(sys.argv[1]); out.mkdir(parents=True,exist_ok=False)
def write_csv(name, data):
 with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
write_csv('permutation-repeats.csv',results)
summary=[]
for group, cols in groups.items():
 a=np.array([r['delta_mae'] for r in results if r['group']==group]); summary.append({'group':group,'features':len(cols),'mean_delta_mae':a.mean(),'sd_delta_mae':a.std(ddof=1),'p05':np.quantile(a,.05),'p95':np.quantile(a,.95),'positive_fraction':np.mean(a>0),'columns':json.dumps([names[i] for i in cols],ensure_ascii=False)})
write_csv('group-importance.csv',summary)
write_csv('evaluation-rows.csv',[{'record_id':p['record_id'],'doi':p['doi'],'status':p['status'],'observed':p['observed'],'prediction':float(v)} for p,v in zip(rows,baseline)])
info={'model_id':meta['model_id'],'input_sha256':{p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in paths},'seed':20261118,'repeats':50,'records':len(rows),'dois':len({p['doi'] for p in rows}),'baseline_mae':float(base_mae),'max_prediction_difference':float(np.max(abs(baseline-np.array([p['raw_prediction'] for p in rows])))),'python':platform.python_version(),'numpy':np.__version__,'dependencies':meta['dependencies']}
(out/'inputs.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
lines=['# D-02 当前模型解释','',f"模型 `{meta['model_id']}`，F_base / ExtraTrees；CO₂ 转化率，误差单位为百分点。验证集 47 条中入口可用 {len(rows)} 条、{info['dois']} 个 DOI（26 ok、2 caution）；其余 19 条不参与。基线记录等权 MAE {base_mae:.3f}，固定变换复现预测最大差 {info['max_prediction_difference']:.3g}。这是开发验证诊断，不是独立评估。",'', '在编码矩阵中，每次对一个块的全部列使用相同的随机行排列，保持块内结构；50 次，种子 20261118。重要性为置换后记录等权 MAE 减去基线，正值表示性能下降。分位数和标准差反映置换随机性，不是样本或论文抽样置信区间。', '', '| 块 | 列数 | 平均 MAE 增量 | 标准差 | 5%–95% | 正值比例 |','|---|---:|---:|---:|---:|---:|']
for s in summary: lines.append(f"| {s['group']} | {s['features']} | {s['mean_delta_mae']:.3f} | {s['sd_delta_mae']:.3f} | {s['p05']:.3f}–{s['p95']:.3f} | {s['positive_fraction']:.0%} |")
lines += ['', 'composition_all 与各 role 块重叠，不能相加。整体组分置换保留供体的组分闭合，但会打破配方与工况的关联；单角色置换可能破坏组分总量闭合并形成不现实的配方。工况单列置换也会打破相关结构；共线性及交互会分摊或改变重要性，因此这不是因果效应或可行实验的效应。负增量表示该样本上的置换改善误差。样本来自少量 DOI，重复置换不增加独立样本数，排序不应外推。', '', '未计算可选 Tree SHAP；本次交付分组置换结果。逐次结果、特征列、样本身份和输入哈希分别见 permutation-repeats.csv、group-importance.csv、evaluation-rows.csv、inputs.json。']
(out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print(json.dumps(info,ensure_ascii=False))
