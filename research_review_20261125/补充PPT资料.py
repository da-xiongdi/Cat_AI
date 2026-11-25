import csv,shutil,zipfile
from pathlib import Path
root=Path.cwd();o=root/'research_review_20261125/ppt_materials'; man=o/'来源映射.csv'; items=[]
paths=['artifacts/reports/s3-01-20261118-01/observed-vs-predicted.png','artifacts/reports/s3-01-20261118-01/r1-predictions.csv','artifacts/reports/s3-01-20261118-01/r2-predictions.csv','artifacts/reports/s3-01-20261118-01/paired-deltas-01c.csv','artifacts/reports/s3-01-20261118-01/per-doi-01c.csv','artifacts/reports/s4-04-final-20261123-v1/fold-seed-mae.svg']
for seed in [45,46,47]:
 for run in ['a','b-select','b2']:
  base=f'artifacts/reports/s5-03-start-20261124/{run}-{seed}'
  paths.extend(f'{base}/{x}' for x in ['config.json','split.json','cross_validation.json','holdout/metrics.json','holdout/predictions.json','holdout/all_arms.json'])
for name in paths:
 src=root/name; assert src.is_file(),str(src); dest=o/'来源'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest);items.append({'package_path':str(dest.relative_to(o)).replace('\\','/'),'workspace_source':name})
with man.open('a',encoding='utf-8-sig',newline='') as f: w=csv.DictWriter(f,fieldnames=['package_path','workspace_source']);w.writerows(items)
readme=o/'README_资料索引.md';t=readme.read_text(encoding='utf8');t+='\n补充历史图：`来源/artifacts/reports/s3-01-20261118-01/observed-vs-predicted.png`、`来源/artifacts/reports/s4-04-final-20261123-v1/fold-seed-mae.svg`；S3 逐条预测、逐 DOI 指标及铜基三臂逐种子 OOF/留出预测均随包保存。\n';readme.write_text(t,encoding='utf8')
zpath=root/'research_review_20261125/ppt_materials.zip'
with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
 for f in sorted(o.rglob('*')):
  if f.is_file():z.write(f,Path('ppt_materials')/f.relative_to(o))
with zipfile.ZipFile(zpath) as z:
 bad=z.testzip(); print('zip',zpath.stat().st_size,'files',len(z.namelist()),'bad',bad); assert bad is None
