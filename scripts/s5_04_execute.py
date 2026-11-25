"""Pre-register, train, lock, score, and report S5-E02 in separate phases."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from catalyst_ai.modeling.s5_metrics import compare

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/reports/s5-04-e02-20261124-v1'
ET = {'n_estimators': 100, 'min_samples_leaf': 2, 'max_depth': None, 'max_features': 1.0, 'n_jobs': 1}
GB = {'n_estimators': 100, 'max_depth': 3, 'learning_rate': 0.1}
def candidate(name, params):
    return {'feature': 'F_base', 'model': name, 'params': params}
FIXED = [candidate('extra_trees', ET), candidate('random_forest', ET),
         candidate('gradient_boosting', GB), candidate('dummy', {}), candidate('ridge', {'alpha': 1.0})]
SEARCH = FIXED + [candidate('extra_trees', dict(ET, max_depth=8)),
                  candidate('extra_trees', dict(ET, min_samples_leaf=4, max_features=0.7)),
                  candidate('random_forest', dict(ET, max_depth=8)),
                  candidate('random_forest', dict(ET, min_samples_leaf=4, max_features=0.7)),
                  candidate('gradient_boosting', dict(GB, max_depth=2, learning_rate=0.05, n_estimators=150)),
                  candidate('gradient_boosting', dict(GB, max_depth=2, learning_rate=0.1, n_estimators=100))]
def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
def init():
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT/'preregistration.md').write_text('''# S5-E02 预登记 v1

固定 F_base、模型种子 42、S5 冻结 45/46/47 成员与五折。固定对照顺序为 ET、RF、梯度提升、Dummy、Ridge；搜索在相同固定臂后对 ET、RF、提升各增加两套参数。各配置的完整有序候选列表见 configs；每种树模型各三套，含固定版。提升采用 scikit-learn GradientBoostingRegressor：当前 Windows Python 3.14 环境没有安装或锁定 XGBoost，未完成 XGBoost 轮子及发布打包验证，故本轮不使用 XGBoost；scikit-learn 已是项目 modeling 依赖。不得据此声称 XGBoost 不兼容。

先完成三种子固定对照训练，再完成三种子搜索训练；所有模型及训练侧决定锁定后才进行任何留出评分。按 s5-paired-v1 在每次运行的全部候选中选择；R² 仅报告。报告所有预登记臂的训练 OOF、各折及一次留出得分。每次拟合使用单线程，禁止早停；每次运行限时 1800 秒，总训练六次，最多 240 次折拟合与 48 次全训练拟合；超时或失败保留日志并中止，不查看留出、不改候选；预算耗尽回退固定基准，必须另行锁定并报告失败，不能以留出挑选。仅同种子同成员比较。时间包括特征拟合和预测。
''', encoding='utf-8')
    (OUT/'configs').mkdir()
    for phase, candidates in [('fixed', FIXED), ('search', SEARCH)]:
        for seed in (45, 46, 47):
            base = json.loads((ROOT/f'artifacts/reports/s5-03-start-20261124/a-{seed}.json').read_text(encoding='utf-8'))
            base.update(candidates=candidates, metrics=['mae','rmse','r2','availability'], outputs=['predictions'], selection_rule='s5-paired-v1')
            write(OUT/'configs'/f'{phase}-{seed}.json', base)
    files = sorted((OUT/'configs').glob('*.json')) + [OUT/'preregistration.md']
    write(OUT/'preregistration-sha256.json', {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})

def run():
    env = os.environ.copy()
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        env[key] = '1'
    traces = []
    for phase in ('fixed', 'search'):
        for seed in (45, 46, 47):
            name = f'{phase}-{seed}'
            started = time.monotonic()
            cmd = [sys.executable, str(ROOT/'scripts/run_research_experiment.py'), 'train', str(OUT/'configs'/f'{name}.json'), '--output', str(OUT/name)]
            try:
                result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=1800, encoding='utf-8')
                (OUT/f'{name}.stdout.log').write_text(result.stdout, encoding='utf-8')
                (OUT/f'{name}.stderr.log').write_text(result.stderr, encoding='utf-8')
                status = result.returncode
            except subprocess.TimeoutExpired as exc:
                (OUT/f'{name}.timeout.log').write_text(str(exc), encoding='utf-8')
                status = 'timeout'
            traces.append({'run': name, 'status': status, 'seconds': time.monotonic()-started})
            write(OUT/'training-trace.json', traces)
            if status != 0:
                raise RuntimeError(f'{name} failed; holdout not scored')
    for phase in ('fixed', 'search'):
        for seed in (45, 46, 47):
            name = f'{phase}-{seed}'
            result = subprocess.run([sys.executable, str(ROOT/'scripts/run_research_experiment.py'), 'score', str(OUT/name)], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=1800)
            (OUT/f'{name}.score.log').write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
            if result.returncode:
                raise RuntimeError(f'{name} score failed; preserve failure')
    for phase in ('fixed', 'search'):
        for seed in (45, 46, 47):
            name = f'{phase}-{seed}'; folder = OUT/name
            cv = json.loads((folder/'cross_validation.json').read_text(encoding='utf-8'))
            held = json.loads((folder/'holdout/all_arms.json').read_text(encoding='utf-8'))
            report = {'candidates': [r['candidate'] for r in cv['results']],
                      'selection': cv['selection_decision'],
                      'oof': compare({str(i): r['predictions'] for i,r in enumerate(cv['results'])}),
                      'holdout': compare({str(a['candidate_index']): a['predictions'] for a in held})}
            write(OUT/f'{name}-metrics.json', report)

if __name__ == '__main__':
    if sys.argv[1] == 'init': init()
    elif sys.argv[1] == 'run': run()
