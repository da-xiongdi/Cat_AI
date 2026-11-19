"""Development-only tree dispersion diagnostic for the frozen S3 R2 package."""
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from catalyst_ai.modeling.predictor import load_package

ROOT = Path(__file__).resolve().parents[1]
paths = ['artifacts/models/s3-20261118-01/r2/manifest.json', 'artifacts/models/s3-20261118-01/r2/model.pkl', 'artifacts/runs/s3-20261118-01/r2/report.json', 'data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json', 'artifacts/reports/d-03-20261118-01/row-domain.csv', 'artifacts/reports/d-03-20261118-01/rule.json', 'artifacts/reports/d-04-20261118-01/freeze.json', 'scripts/d05_uncertainty.py']
def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf8'))

meta, fitted = load_package(ROOT / 'artifacts/models/s3-20261118-01/r2')
report, snapshot, freeze = read(paths[2]), read(paths[3]), read(paths[6])
assert freeze['eligible_groups'] == 0 and not freeze['calibration_groups']
records = {r['record_id']: r for r in snapshot['content']['records']}
with (ROOT / paths[4]).open(encoding='utf-8-sig', newline='') as f:
    domain = {r['record_id']: r for r in csv.DictReader(f) if r['partition'] == 'validation'}
preds = report['validation']['candidates']['F_base/extra_trees']['predictions']
rows = [p for p in preds if p['status'] in ('ok', 'caution')]
assert len(preds) == 47 and len(rows) == 28 and len(domain) == 47
assert all(domain[p['record_id']]['status'] == p['status'] for p in preds)
x = np.array([fitted['features'].transform_one(records[p['record_id']]['payload'])['values'] for p in rows], dtype=float)
model = fitted['model']
tree = np.array([est.predict(x) for est in model.estimators_])
mean = tree.mean(axis=0)
assert np.allclose(mean, model.predict(x), rtol=0, atol=1e-10)
assert np.allclose(mean, [p['raw_prediction'] for p in rows], rtol=0, atol=1e-10)
sd = tree.std(axis=0, ddof=0)
err = np.abs(np.array([p['observed'] for p in rows]) - mean)
cuts = np.quantile(sd, [1/3, 2/3])
output = []
for i, p in enumerate(rows):
    output.append(dict(record_id=p['record_id'], doi=p['doi'], status=p['status'], domain=domain[p['record_id']]['candidate_label'], observed=p['observed'], prediction=mean[i], abs_error=err[i], tree_sd=sd[i], dispersion_group=('low', 'middle', 'high')[np.searchsorted(cuts, sd[i], side='right')]))

def metrics(group, label, selected):
    by_doi = {}
    for r in selected:
        by_doi.setdefault(r['doi'], []).append(r['abs_error'])
    return dict(group=group, label=label, records=len(selected), dois=len(by_doi), mean_abs_error=float(np.mean([r['abs_error'] for r in selected])) if selected else None, paper_equal_mae=float(np.mean([np.mean(v) for v in by_doi.values()])) if selected else None, mean_tree_sd=float(np.mean([r['tree_sd'] for r in selected])) if selected else None)

groups = [metrics('all', 'available', output)]
for field, labels in [('dispersion_group', ['low', 'middle', 'high']), ('domain', ['inside', 'warning', 'outside']), ('status', ['ok', 'caution'])]:
    groups.extend(metrics(field, label, [r for r in output if r[field] == label]) for label in labels)
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=False)
def write(name, data):
    with (out / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
write('row-dispersion.csv', output); write('group-metrics.csv', groups)
rho = float(spearmanr(sd, err).statistic)
info = dict(model_id=meta['model_id'], input_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}, python=platform.python_version(), numpy=np.__version__, dependencies=meta['dependencies'], trees=len(tree), validation_total=len(preds), available=len(rows), available_dois=len({p['doi'] for p in rows}), dispersion_tertile_cutpoints=cuts.tolist(), spearman_rho=rho, max_prediction_difference=float(np.max(np.abs(mean - np.array([p['raw_prediction'] for p in rows])))), interval_status='not_calibrated', calibration_groups=0)
(out / 'inputs.json').write_text(json.dumps(info, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
lines = ['# D-05 树间离散度诊断', '', f"冻结模型 `{meta['model_id']}`；开发验证集共 47 条，入口可用 {len(rows)} 条、{info['available_dois']} 个 DOI；19 条被拒绝，不计算离散度和误差。树数 {len(tree)}，树预测均值与保存预测最大差 {info['max_prediction_difference']:.3g}。", '', f"树间离散度定义为各树预测的总体标准差（ddof=0），单位为转化率百分点；绝对误差使用同一单位。可用记录的 Spearman 等级相关系数为 {rho:.3f}。分层按该验证子集离散度三分位数划分，切点 {cuts[0]:.3f}、{cuts[1]:.3f}；这是事后描述，并非固定风险阈值。", '', '| 分层 | 类别 | 记录 / DOI | 记录等权 MAE | 论文等权 MAE | 平均树间标准差 |', '|---|---|---:|---:|---:|---:|']
for g in groups:
    fmt = lambda v: '—' if v is None else f'{v:.3f}'
    lines.append(f"| {g['group']} | {g['label']} | {g['records']} / {g['dois']} | {fmt(g['mean_abs_error'])} | {fmt(g['paper_equal_mae'])} | {fmt(g['mean_tree_sd'])} |")
lines += ['', '树间离散度仅为经验指标，树之间相关，不能解释为预测标准误、置信水平或覆盖概率。记录并非独立抽样，DOI 少且分层可能高度不均衡；相关性和分层差异不能作为独立验证或可靠风险排序。D-03 域标签仅作开发诊断，域外无入口可用记录。', '', 'D-04 冻结清单为 0 个合格独立组、0 个校准组，因此停止区间校准：没有拟合或冻结区间算法、覆盖率或参数，也不提供预测区间。需要取得与最终评估按 DOI 或可追溯来源隔离的足量合格校准组，按 D-04 协议确定覆盖率及方法后，才可在 D-06 前固定区间。历史验证集不替代独立校准集。逐条数据、分层数据及输入哈希见同目录 CSV 和 inputs.json。']
(out / 'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf8')
print(json.dumps(info, ensure_ascii=False))
