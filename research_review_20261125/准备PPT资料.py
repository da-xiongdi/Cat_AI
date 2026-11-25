import os,csv,json,shutil,zipfile,re
from pathlib import Path
root=Path.cwd(); review=root/'research_review_20261125'; out=review/'ppt_materials'; out.mkdir(exist_ok=False)
J=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
manifest=[]
def cp(rel):
 src=root/rel; assert src.is_file(),str(src)
 dst=out/'来源'/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst);manifest.append((str(dst.relative_to(out)).replace('\\','/'),str(rel).replace('\\','/')))
def csvwrite(name,rows,fields=None):
 path=out/name; path.parent.mkdir(parents=True,exist_ok=True); rows=list(rows)
 if fields is None: fields=list(rows[0]) if rows else []
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
# Existing reviewed report data and figures, keeping original names for report links.
for f in review.iterdir():
 if f.is_file() and f.suffix.lower() in ('.png','.csv','.py'):
  shutil.copy2(f,out/f.name); manifest.append((f.name,str(f.relative_to(root)).replace('\\','/')))
report=(review/'科研分析报告.md').read_text(encoding='utf-8-sig').replace('../artifacts/','来源/artifacts/').replace('../docs/','来源/docs/')
(out/'科研分析报告.md').write_text(report,encoding='utf-8');manifest.append(('科研分析报告.md','research_review_20261125/科研分析报告.md（仅改写源链接以便打包）'))
paths=[
'docs/s3_01_comparison.md','docs/s4_04_comparison_analysis.md','docs/s4_04_applicability_coverage.md',
'artifacts/reports/s4-01-20261120/profile.json','artifacts/reports/s4-01-20261120/record-audit.csv',
'artifacts/reports/s4-02-20261120-v1/all-view.json','artifacts/reports/s4-02-20261120-v1/cu-view.json','artifacts/reports/s4-02-20261120-v1/distributions.json',
'artifacts/reports/s4-04-comparison-20261120-v1/comparison.json','artifacts/reports/s4-04-comparison-20261120-v1/paired_records.csv',
'artifacts/reports/s5-02-e01-seed45-range-v2/ablation_analysis.json','artifacts/reports/s5-02-e01-seed45-range-v2/descriptor_dictionary.md','artifacts/reports/s5-02-e01-seed45-range-v2/acceptance_report.md',
'artifacts/reports/s5-03-m2-audit-20261124/report.md','artifacts/reports/s5-03-m2-audit-20261124/material_records.json','artifacts/reports/s5-03-m2-audit-20261124/partition_audit.json',
'artifacts/reports/s5-03-start-20261124/paired_predictions.csv','artifacts/reports/s5-03-start-20261124/paired_metrics.json','artifacts/reports/s5-03-start-20261124/descriptor_inventory.json',
'artifacts/reports/s5-04-e02-20261124-v1/final-review-report.md','artifacts/reports/s5-04-e02-20261124-v1/preregistration.md','artifacts/reports/s5-04-e02-20261124-v1/doi-strata.json',
'artifacts/reports/s5-05-e05-20261124-v1/final_report.md','artifacts/reports/s5-05-e05-20261124-v1/metrics.json','artifacts/reports/s5-05-e05-20261124-v1/fold-permutation.json','artifacts/reports/s5-05-e05-20261124-v1/applicability-and-permutation.json','artifacts/reports/s5-05-e05-20261124-v1/historical-r2.json','artifacts/reports/s5-05-e05-20261124-v1/f3-training-selection.json','artifacts/reports/s5-05-e05-20261124-v1/preregistration.md',
'artifacts/reports/s3-01-20261118-01/metrics-01c.csv','artifacts/reports/d-02-20261118-01/group-importance.csv','artifacts/reports/d-02-20261118-01/permutation-repeats.csv']
for p in paths:cp(Path(p))
for s in (42,43,44):
 for exp in ('EXP-01','EXP-02','EXP-03'):
  base=Path(f'artifacts/reports/s4-04-runs-20261120-v1/{exp}-{s}')
  for sub in ('config.json','split.json','cross_validation.json','holdout/metrics.json','holdout/predictions.json','holdout/observed-predicted.svg','holdout/residuals.svg','holdout/error-distribution.svg'):cp(base/sub)
for s in (45,46,47):
 for tag in ('fixed','search'):
  base=Path(f'artifacts/reports/s5-04-e02-20261124-v1/{tag}-{s}')
  for sub in ('config.json','split.json','cross_validation.json','holdout/metrics.json','holdout/predictions.json','holdout/all_arms.json'):cp(base/sub)
  cp(Path(f'artifacts/reports/s5-04-e02-20261124-v1/{tag}-{s}-metrics.json'))
 for pre in (f'artifacts/reports/s5-02-e01-seed{s}-range-v2/run',f'artifacts/reports/s5-05-e05-20261124-v1/run-{s}'):
  base=Path(pre)
  for sub in ('config.json','split.json','cross_validation.json','holdout/metrics.json','holdout/predictions.json','holdout/all_arms.json'):cp(base/sub)
# Cohort extracts preserve original columns, record IDs and field values.
audit=list(csv.DictReader((root/'artifacts/reports/s4-01-20261120/record-audit.csv').open(encoding='utf-8-sig',newline='')))
allids=set(J(root/'artifacts/reports/s4-02-20261120-v1/all-view.json')['content']['common_record_ids']); cuids=set(J(root/'artifacts/reports/s4-02-20261120-v1/cu-view.json')['content']['common_record_ids']);assert len(allids)==542 and len(cuids)==211 and cuids<=allids
allrows=[r for r in audit if r['record_id'] in allids];curows=[r for r in audit if r['record_id'] in cuids];assert len(allrows)==542 and len(curows)==211
csvwrite('统计表/全体系542_原始记录.csv',allrows); csvwrite('统计表/铜基211_原始记录.csv',curows)
# Human-readable full-model metrics from preserved E05 metric source; retain both scope and exact denominators.
m=J(root/'artifacts/reports/s5-05-e05-20261124-v1/metrics.json'); flat=[];folds=[]
for seed,obj in m.items():
 for i,cand in enumerate(obj['candidates']):
  for part in ('oof','holdout'):
   x=obj[part][str(i)]
   for scope in ('diagnostic','available'):
    vals=x[scope]; flat.append(dict(seed=seed,candidate=i,feature=cand['feature'],model=cand['model'],params=json.dumps(cand['params'],ensure_ascii=False),partition=part,scope=scope,total=x['total'],n=x['diagnostic_n' if scope=='diagnostic' else 'available_n'],available_n=x['available_n'],coverage=x['coverage'],mae=vals['mae'],rmse=vals['rmse'],r2=vals['r2'],doi_equal_mae=x['doi_equal_mae'] if scope=='available' else None))
   comm=obj[part+'_common']['overall']['arms'][str(i)]['common'];flat.append(dict(seed=seed,candidate=i,feature=cand['feature'],model=cand['model'],params=json.dumps(cand['params'],ensure_ascii=False),partition=part,scope='all_18_common_available',total=x['total'],n=comm['records'],available_n=x['available_n'],coverage=x['coverage'],mae=comm['mae'],rmse=comm['rmse'],r2=comm['r2'],doi_equal_mae=None))
  for f,v in obj['folds'][str(i)].items():
   z=v['available']; folds.append(dict(seed=seed,candidate=i,feature=cand['feature'],model=cand['model'],fold=f,total=v['total'],available_n=v['available_n'],coverage=v['coverage'],mae=z['mae'],rmse=z['rmse'],r2=z['r2']))
csvwrite('统计表/S5_E05_18臂_多种子OOF留出.csv',flat);csvwrite('统计表/S5_E05_18臂_逐折可用指标.csv',folds)
# Extract feature ablation and impurity importances as shown in existing scientific report.
ab=J(root/'artifacts/reports/s5-02-e01-seed45-range-v2/ablation_analysis.json'); features=[];importance=[]
for sd in ab['seeds']:
 for c in sd['candidates']:
  for part in ('oof','holdout'):
   z=c[part];
   for scope in ('available','diagnostic'):
    v=z[scope+'_metrics'];features.append(dict(seed=sd['seed'],feature=c['feature'],partition=part,scope=scope,total=z['total_records'],n=z[scope+'_records'],coverage=z['available_fraction'],mae=v['mae'],rmse=v['rmse'],r2=v['r2'],doi_equal_mae=v['paper_equal_mae']))
  for k,v in c['importance'].items():importance.append(dict(seed=sd['seed'],feature_scheme=c['feature'],feature_name=k,importance=v))
csvwrite('统计表/S5_特征消融_各自可用和诊断.csv',features);csvwrite('统计表/S5_特征重要性_全部.csv',importance)
counts=[]
for view,rows in [('all',[(45,38),(46,39),(47,37)]),('cu',[(45,19),(46,21),(47,20)])]:
 for s,b in rows:
  for f,n in [('F_cond',4),('F_base',b),('F1',b+4),('F2',b+10),('F3-P',18),('F3-H',b+14),('F3-I',21)]+([('Cu_B2',b+18)] if view=='cu' else []): counts.append(dict(view=view,seed=s,feature=f,input_columns=n,source='S5-02/S5-03 full fitted model n_features_in_'))
csvwrite('统计表/特征方案_输入列数.csv',counts)
perm=J(root/'artifacts/reports/s5-05-e05-20261124-v1/fold-permutation.json'); rows=[]
for seed,ff in perm.items():
 for f in ff:
  for block,x in f['blocks'].items():rows.append(dict(seed=seed,fold=f['fold'],total=f['validation_total'],available=f['available'],baseline_mae=f['baseline_mae'],block=block,mae_increase_mean=x['mean'],mae_increase_sd=x['sd'],repeats=json.dumps(x['repeats'])))
csvwrite('统计表/S5_特征块逐折置换.csv',rows)
# readable F_base + F3 candidate/parameter definitions in same order as metrics.
csvwrite('统计表/S5_E05_候选与超参数.csv',[dict(seed=s,candidate=i,feature=c['feature'],model=c['model'],params=json.dumps(c['params'],ensure_ascii=False)) for s,z in m.items() for i,c in enumerate(z['candidates'])])
(out/'字段与评价口径.md').write_text('''# 字段与评价口径

- `record_id` 为记录身份；`doi` 为文献来源；相同 DOI 下记录不视为独立文献。`composition` 为来源角色、物种和材料 mol% 的列表；`classification` 是 Cu/non-Cu 分类。角色和名义量不等于实测活性位、分散度或金属负载。
- `conversion_pct` / `observed` 是实测 CO2 转化率（%）；`raw_prediction` 是模型预测，`prediction − observed` 为残差；MAE、RMSE、残差用转化率百分点。`temperature_k` 为 K，`pressure_bar_abs` 为绝压 bar（数据集假设），`h2_co2_ratio` 为进料摩尔比，`flow_nl_g_h` 为反应物质量归一流量 NL/g_cat/h。
- `seed` 为数据划分种子；`fold` 为训练内验证折；OOF 是每条训练记录在未用其所属折拟合的模型上得到的预测，不能当作全训练集拟合内误差。`candidate` 为对应运行配置的候选序号，具体特征、算法和参数见候选表和原始配置。
- `status` 的 ok/caution 且预测有限为入口可用；`unsupported_species_role` 等不计入可用集；`out_of_range` 记录范围警示；`total` 为分母，`n` 为指标计算样本数，`coverage` 是各臂可用数除以总数。警示不代表可靠性已保证。缺失 R² 表示不可定义而非零。
- S5-E05 18 臂 CSV 中 `diagnostic` 为含不可用状态的有限诊断预测，`available` 是各臂各自可用样本，`all_18_common_available` 是 18 臂严格交集。`doi_equal_mae` 是先在 DOI 内计算 MAE，再对 DOI 等权；仅在可用口径列出。各自可用和共同集不得直接混比。六算法表为额外事后对 S5-04 固定臂及 S5-E05 固定 XGB 的严格六臂共同留出交集，覆盖数仍是各臂各自值。
- S4 EXP-01 按 DOI 留出，EXP-02 分组随机全体系，EXP-03 是铜基投影；同种子不同实验的训练及测试成员不完全相同。随机留出允许同 DOI 已在训练出现，不能当作未见文献的外部验证。S5 45/46/47 的训练和留出各有 434/108 条，种子训练集重叠；所有留出此前已观察，均属内部探索性结果。
- 六算法材料排序按同 DOI、四项工况完全相同分组、同配方重复取均值；先取六臂记录交集，再要求四算法非恒定预测才计算四算法共同组的 Spearman、Kendall；Top-1 和 Top-2 进一步排除并列。Dummy 恒定预测相关系数不可定义。高值定义为观察后设定的实测 ≥20%，不是预设应用门槛。
- `sim` 为 1 减角色×物种名义材料 mol% 向量的半 L1 距离，报告留出样本对本种子训练配方的最大相似度；不表示表面结构或工况相似。置换 `mae_increase_mean` 为打乱整个特征块后的 MAE 增量，相关特征与不现实组合限制因果解释；树分裂重要性也不是催化机制证明。
- 原始 JSON 保留各自完整嵌套结构、预测状态、逐折记录、参数和成员；`统计表` CSV 是从原始证据提取的便于作图的派生表，并非新训练。字段中的空值保留原缺失语义。
''',encoding='utf-8')
(out/'README_资料索引.md').write_text('''# S1–S5 科研汇报资料包

先阅读 [科研分析报告](科研分析报告.md) 和 [字段与评价口径](字段与评价口径.md)。本包用于准备 PPT；结论和图表均是已有实验的内部探索，不构成独立外部验证。

- 根目录 PNG：最新完整报告实际使用的 12 张图，文件名与正文引用一致；同目录 CSV 为排序、高值、残差、六算法等已完成的诊断数据。
- `统计表/`：从冻结证据提取的 542 条全体系与 211 条铜基原始记录、特征列数、特征消融、18 臂逐种子 OOF/留出及逐折指标、参数、特征重要性与块置换。铜基为全体系子集。
- `来源/artifacts/reports/s4-04-runs-20261120-v1/`：S4 九个 DOI、随机和铜基运行的配置、划分、交叉验证、逐条留出预测及历史 SVG 图。
- `来源/artifacts/reports/s5-02-e01-seed45-range-v2/`、对应 46/47：物化特征消融，含全候选 OOF 与留出预测；`ablation_analysis.json` 提供三种子完整配对结果和特征重要性。
- `来源/artifacts/reports/s5-03-*/`：铜基配对预测、描述符覆盖和材料记录。
- `来源/artifacts/reports/s5-04-e02-20261124-v1/`：固定算法与有限超参数搜索、各种子 OOF、逐条留出及对比指标；包含 GB、RF、ET、Ridge、Dummy。
- `来源/artifacts/reports/s5-05-e05-20261124-v1/`：18 臂特征×算法×参数组合、OOF、逐条留出、历史 R²、置换、适用范围与选型；包括 XGBoost。S5-04 未运行 XGB，六算法统一比较为观察后的跨阶段共同样本计算。
- `来源/docs/` 与各原报告：历史文档和科研来源；`来源映射.csv` 可追溯复制前路径。原始文档内指向未收录工程文件的链接可能失效；包内主报告链接和绘图资源已改写为本包路径。
- `*.py`：本报告已完成的诊断及表格计算脚本，供追溯口径；不包含重新训练操作。模型包、数据库、软件测试、验收日志、散列和环境归档没有收录。

图表与数据对照：数据分布 → `统计表/全体系542_原始记录.csv` 和 `铜基211_原始记录.csv`；特征方案 → `统计表/S5_特征消融_各自可用和诊断.csv`；算法统一比较及排序/高值 → 根目录同名 CSV；实验值与预测值、残差 → S5-E05 `run-45/holdout/predictions.json`；多种子及训练折 → `统计表/S5_E05_18臂_多种子OOF留出.csv` 与逐折表；重要性 → `统计表/S5_特征重要性_全部.csv`；置换 → `统计表/S5_特征块逐折置换.csv`；DOI 对比 → S4 比较 JSON、配对 CSV 和九个运行；相似度 → 根目录 `专项_高值逐条.csv`。原始实验样本、分区和预测通过 record_id 可连接。
''',encoding='utf-8')
csvwrite('来源映射.csv',[dict(package_path=a,workspace_source=b) for a,b in manifest])
# Verify every relative link in the primary report resolves within export.
links=re.findall(r'\]\(([^)]+)\)',report); missing=[]
for link in links:
 path=(out/link.split('#')[0]).resolve()
 if not path.exists():missing.append(link)
assert not missing,missing
assert len(flat)==324 and len(folds)==270 and len(counts)==45
zip_path=review/'ppt_materials.zip'
with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
 for f in sorted(out.rglob('*')):
  if f.is_file():z.write(f,Path('ppt_materials')/f.relative_to(out))
with zipfile.ZipFile(zip_path) as z:
 assert z.testzip() is None
 print('FILES',len(z.namelist()),'ZIP_BYTES',zip_path.stat().st_size,'report links',len(links),'unmatched',len(missing),'E05 metric',len(flat),'folds',len(folds))
