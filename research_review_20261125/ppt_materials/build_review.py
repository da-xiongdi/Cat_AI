import json, pathlib, math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import defaultdict
root=pathlib.Path('.'); out=root/'research_review_20261125'; rep=root/'artifacts/reports'; load=lambda p:json.loads(p.read_text(encoding='utf8'))
plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']; plt.rcParams['axes.unicode_minus']=False
m=load(rep/'s5-05-e05-20261124-v1/metrics.json'); ab=load(rep/'s5-02-e01-seed45-range-v2/ablation_analysis.json')['seeds']; p=load(rep/'s5-05-e05-20261124-v1/run-45/holdout/predictions.json'); p=[r for r in p if r['status'] in ('ok','caution') and r['raw_prediction'] is not None]
fmt=lambda x: '—' if x is None else f'{x:.3f}'
lines=[]
def add(s): lines.append(s+'\n')
add('''# S1–S5 CO2 转化率模型训练结果与科研复盘

2026-11-25｜依据已冻结的实验和逐条预测；误差单位均为转化率百分点。

## 摘要

S5 主模型 F_base / Extra Trees 在三个分组随机留出划分中，可用预测 MAE 为 2.072–2.303、RMSE 为 3.107–3.522、R² 为 0.844–0.904，覆盖率 105–107 / 108。S4 更严格的 DOI 留出全体诊断 MAE 为 5.451–9.574，表明新文献泛化存在明显困难。两类划分的成员和来源不同，差值不能单独归因于划分方法。已有留出数据曾被观察，所有结果均为内部研究评价，尚无独立外部验证。

物化特征和铜基专属特征未表现出稳定增益；三种子训练侧选择规则最终保留基础树模型。模型适合训练数据覆盖范围内的探索性排序和提出待实验验证的候选，不能仅凭数值预测确认新配方，更不能视作外部验证过的筛选工具。

## 数据、目标与评价口径

源表 821 行；S4 冻结 593 条、37 DOI、141 个组成签名，其中 Cu 基 211 条（16 DOI）、非 Cu 382 条。铜基包括 207 条 Cu 物种及 4 条 La–Mn–Cu 氧化物；来源角色不等同于真实活性位。CO2 转化率为入口与出口 CO2 摩尔流量差除以入口量，单位 %。S1 共同资格为 553 条；S4/S5 进一步采用 542 条共同母池，不能把以上规模混为同一训练集。详见 [S4 数据审计](../artifacts/reports/s4-01-20261120/profile.json) 与 [S3 数据和划分](../docs/s3_01_comparison.md)。

S3 R1 为训练/开发验证/历史测试 493/47/53；R2 为 454/47/52，按 DOI 分组，训练内三折 DOI CV。S4 随机 434/108；DOI 划分种子 42、43、44 的训练/留出分别为 432/110、438/104、434/108；铜基训练/留出分别 181/30、170/41、166/45。S5 全体系各种子均 434/108、训练内五折，按身份组划分；铜基分别 170/41、162/49、166/45。分组随机允许同一 DOI 同时出现于训练和留出，不能代表新文献。不同种子训练成员高度重叠，不是独立重复。

S4 全体温度 433–673 K（中位数 523 K），绝压 0.4–60 bar（中位数 30 bar）；S5 主种子训练为 433–673 K、0.4–50 bar、H₂/CO2 3–5、质量归一流量 0.87–40 NL/g_cat/h。铜基视图温度最高 553 K。压力沿用数据集绝压假设；区间内也不保证组合被充分覆盖。来源未逐篇核实。目标分布下图使用 S5 主种子可用留出记录，并非全母池分布。
''')
y=np.array([r['observed'] for r in p]); pred=np.array([r['raw_prediction'] for r in p]); err=pred-y
fig,axs=plt.subplots(1,2,figsize=(10,4)); axs[0].hist(y,bins=15,color='#337b8a',edgecolor='white'); axs[0].set(xlabel='实测 CO2 转化率 (%)',ylabel='记录数',title='留出目标分布，n=106'); axs[1].scatter(y,pred,s=18,alpha=.7); lim=max(y.max(),pred.max()); axs[1].plot([0,lim],[0,lim],'k--'); axs[1].set(xlabel='实测 (%)',ylabel='预测 (%)',title='S5 种子 45 可用留出'); fig.tight_layout(); fig.savefig(out/'distribution_scatter.png',dpi=160); plt.close(fig)
add('![留出目标分布及实测预测](distribution_scatter.png)\n')
add('## 多种子模型表现\n\nS5-E05 基础模型，入口可用（ok/caution），OOF 为训练集五折折外预测，留出各 108 条；MAE、RMSE、R²在各自可用集合计算。\n\n| 种子 | OOF 可用/总数 | OOF MAE | OOF RMSE | OOF R² | 留出可用/总数 | 留出 MAE | 留出 RMSE | 留出 R² | DOI 等权 MAE |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
for s in ['45','46','47']:
 a=m[s]['oof']['0']; b=m[s]['holdout']['0']; x=a['available']; z=b['available']; add(f"| {s} | {a['available_n']}/{a['total']} | {fmt(x['mae'])} | {fmt(x['rmse'])} | {fmt(x['r2'])} | {b['available_n']}/{b['total']} | {fmt(z['mae'])} | {fmt(z['rmse'])} | {fmt(z['r2'])} | {fmt(b['doi_equal_mae'])} |")
fig,ax=plt.subplots(figsize=(7,4));
for s in ['45','46','47']:
 folds=m[s]['folds']['0']; vals=[f['available']['mae'] for f in folds.values()]
 if vals: ax.scatter([int(s)]*len(vals),vals,alpha=.7,label=f'{s} 五折')
 ax.scatter(int(s),m[s]['holdout']['0']['available']['mae'],marker='D',s=70,color='black')
ax.set(xlabel='划分种子',ylabel='MAE（百分点）',title='训练五折与留出（黑菱形）'); ax.set_xticks([45,46,47]); fig.tight_layout(); fig.savefig(out/'stability.png',dpi=160); plt.close(fig)
add('\n![多种子与训练折稳定性](stability.png)\n\nOOF 不是训练集拟合内误差；它与留出误差接近并不能证明不存在过拟合。多次实验使用同一母池并观察过留出，存在研究选择性适配风险。\n')
add('## 特征方案\n\nF_cond 为温度、绝压、H₂/CO2 比及质量归一流量 4 项；F_base 再加来源角色×物种的材料 mol% 列，宽度由训练词表决定；F1 再加活性角色总量、正含量物种数、电负性和共价半径均值 4 项；F2 再加载体同类 4 项及活性–载体两属性差，共较 F_base 增 10 项。F3-P 用角色元素组成和物化分布替代物种词表，F3-H 将物化材料块加入 F_base，F3-I 在 P 基础上加入角色间差、比例及分布。F3 和 F_base 的总列数随词表、适用标志而变，应以各运行特征清单为准；公式见 [描述符字典](../artifacts/reports/s5-02-e01-seed45-range-v2/descriptor_dictionary.md)。Cu 块以材料名义 mol%、Cu 中心量及同角色 Cu/Zn、Cu/Zr、Cu/Al 比及适用标志描述，非实测分散度或活性位。\n\n下表为 S5-02 固定 Extra Trees、同种子同成员同折，各臂各自可用留出集；不同覆盖意味着表内数值不能直接当作配对差值。\n\n| 种子 | 特征 | 可用/108 | MAE | RMSE | R² |\n|---|---|---:|---:|---:|---:|')
for seed in ab:
 for c in seed['candidates']:
  h=c['holdout']; q=h['available_metrics']; add(f"| {seed['seed']} | {c['feature']} | {h['available_records']}/108 | {fmt(q['mae'])} | {fmt(q['rmse'])} | {fmt(q['r2'])} |")
fig,ax=plt.subplots(figsize=(9,4)); names=[c['feature'] for c in ab[0]['candidates']]; xx=np.arange(len(names));
for i,seed in enumerate(ab): ax.bar(xx+(i-1)*.25,[c['holdout']['available_metrics']['mae'] for c in seed['candidates']],.25,label=str(seed['seed']))
ax.set_xticks(xx); ax.set_xticklabels(names,rotation=25); ax.set_ylabel('留出 MAE（百分点）'); ax.set_title('各自可用集；覆盖不同时不可直接作配对比较'); ax.legend(title='种子'); fig.tight_layout(); fig.savefig(out/'features.png',dpi=160); plt.close(fig)
add('''
![特征方案各自可用留出误差](features.png)

严格共同可用集的 F3-P − F_base MAE 差为 +0.0747、+0.1107、−0.0973；F3-H − F_base 为 +0.0816、+0.0626、−0.1239。S3 的 DOI 三折 R2 共同子集 F1/F2 相对 F_base 的论文等权 OOF MAE 分别增加 0.558/0.514。S5-02 训练侧分别选择 F1、F_base、F_base，而 S5-E05 的组合训练规则三种子都保留 F_base/ET；两者选择空间不同，不矛盾。

Cu 全体系与专属训练模型的共同留出配对差 B1−A 为 +0.0436、+0.0073、−0.0330；加 Cu 块 B2−B1 为 +0.0285、+0.0692、+0.0084，n=39、49、44。Cu/Zn 同角色可算 85/211，Cu/Zr、Cu/Al 为 0/211，名义比依赖来源角色与数据口径。证据支持的是“本次未见稳定增益”，不是证明描述符无物理作用。可能原因包括小样本、特征与已有组成冗余、角色与真实活性位不一致、缺少分散度和反应前后表征，以及来源/工况混杂；这些均是待检验假设。

## 算法与参数

S5-04 固定 F_base：ET 和 RF 均 100 树、叶最小 2、最大特征 1、深度不限；Gradient Boosting 100 树、深度 3、学习率 0.1；Dummy 预测均值；Ridge α=1。每种树的有限搜索另试两组，三个种子固定参数在对应训练共同集均优于其备选；不是穷举最优。S5-E05 后续实际加入 XGBoost，固定组 100 树、深度 3、学习率 0.1，并给 ET、RF、XGB 各三组预算、F_base 与训练侧选中的 F3-P 组合。S5-04 本身没有 XGB，不能混写。

下表为 S5-04 五算法各种子严格共同可用集合，故每行的 MAE、RMSE、R²使用同一成员；覆盖则为该臂各自可用数/108。OOF 为五算法训练共同可用集合。

| 种子 | 算法 | OOF共同n | OOF MAE | OOF RMSE | OOF R² | 留出共同n | 留出 MAE | 留出 RMSE | 留出 R² | 留出覆盖 |\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|''')
alg=[]
for s in [45,46,47]:
 d=load(rep/f's5-04-e02-20261124-v1/fixed-{s}-metrics.json'); oo=d['oof']['overall']; ho=d['holdout']['overall'];
 for i,c in enumerate(d['candidates']):
  a=oo['arms'][str(i)]['common']; b=ho['arms'][str(i)]['common']; avail=ho['arms'][str(i)]['available']; add(f"| {s} | {c['model']} | {a['records']} | {fmt(a['mae'])} | {fmt(a['rmse'])} | {fmt(a['r2'])} | {b['records']} | {fmt(b['mae'])} | {fmt(b['rmse'])} | {fmt(b['r2'])} | {avail}/108 |")
  alg.append((s,c['model'],b['mae']))
fig,ax=plt.subplots(figsize=(8,4)); names=[x['model'] for x in d['candidates']]; xx=np.arange(len(names));
for j,s in enumerate([45,46,47]): ax.bar(xx+(j-1)*.25,[next(z for ss,n,z in alg if ss==s and n==name) for name in names],.25,label=str(s))
ax.set_xticks(xx); ax.set_xticklabels(names,rotation=20); ax.set_ylabel('共同集 MAE（百分点）'); ax.legend(title='种子'); fig.tight_layout(); fig.savefig(out/'algorithms.png',dpi=160); plt.close(fig)
add('''
![固定算法共同留出比较](algorithms.png)

S5-E05 的 18 臂严格共同留出集 100、100、102 条：固定 ET MAE 分别 2.193、2.187、2.367，固定 XGB 为 2.276、2.419、2.420。训练严格共同集分别 412、412、410 条，种子 45 固定基线距最低 MAE 0.0922，其余两种子为 0；按事先规定 0.1 平局规则保留较简单的固定基线。R² 未用于选择，并非各指标排序一致：例如种子 45 的 S5-04 共同留出上 Gradient Boosting 的 R² 高于 ET，而其 MAE 更差；R²受同集目标方差与大误差影响。完整 18 臂所有参数及训练/留出指标见 [E05 逐臂指标](../artifacts/reports/s5-05-e05-20261124-v1/metrics.json)。

## 泛化与解释

S4 DOI 分组全体诊断 MAE 依种子为 5.451、9.574、5.679；随机分组为 2.026、2.663、2.553。相同种子偶然共同留出记录上 DOI/随机分别 5.677/2.672（31 条）、7.953/4.066（24 条）、6.934/2.351（26 条）。训练成员、论文、配方及工况同时变化，不能将差异归为单一原因。DOI 种子 43 一篇文献 22 条贡献 66.4% 的绝对误差，且有流量越界警示；来源和配方同时改变，不能断定越界导致大误差。未见配方、跨材料族和独立实验室的可靠性尚无足够受控证据；未见物种/角色还可能被入口拒绝。

训练五折联合置换导致 MAE 增量：组成块种子 45/46/47 为 4.546/4.755/4.684，工况块为 3.048/2.977/3.058。说明两块均被模型利用；置换可产生不现实组合、相关变量共享贡献，数字不能解释为独立因果效应。以下为 S5-02 种子 45 最终拟合模型的树分裂重要性，属于模型内统计，不是催化机理。
''')
imp=ab[0]['candidates'][0]['importance']; top=sorted(imp.items(),key=lambda x:-x[1])[:12]; fig,ax=plt.subplots(figsize=(8,5)); ax.barh([x[0] for x in top][::-1],[x[1] for x in top][::-1]); ax.set(xlabel='树分裂重要性',title='S5-02 F_base / ET，种子 45'); fig.tight_layout(); fig.savefig(out/'importance.png',dpi=160); plt.close(fig)
add('![模型特征重要性](importance.png)\n\n| 特征 | 分裂重要性 |\n|---|---:|');
for k,v in top: add(f'| {k} | {v:.4f} |')
fig,axs=plt.subplots(1,2,figsize=(10,4)); axs[0].scatter(y,err,s=18,alpha=.7); axs[0].axhline(0,color='black',linestyle='--'); axs[0].set(xlabel='实测转化率 (%)',ylabel='预测 − 实测（百分点）',title='残差'); bins=[0,5,10,20,40,101]; group=[np.abs(err[(y>=a)&(y<b)]) for a,b in zip(bins[:-1],bins[1:])]; labs=[f'{a}–{b} (n={len(g)})' for a,b,g in zip(bins[:-1],bins[1:],group)]; axs[1].bar(range(len(group)),[np.mean(g) if len(g) else 0 for g in group]); axs[1].set_xticks(range(len(group))); axs[1].set_xticklabels(labs,rotation=35,ha='right'); axs[1].set(ylabel='MAE（百分点）',title='按实测转化率分层'); fig.tight_layout(); fig.savefig(out/'residuals.png',dpi=160); plt.close(fig)
add('\n## 误差与实例\n\n![残差和转化率分层](residuals.png)\n\n主种子 45，106 条入口可用留出；残差定义为预测减实测。分层样本量小的柱不宜比较为稳定体系差异。\n\n| 转化率区间 (%) | n | MAE | 平均残差 |\n|---|---:|---:|---:|')
for a,b in zip(bins[:-1],bins[1:]):
 ix=(y>=a)&(y<b); add(f'| [{a}, {b}) | {sum(ix)} | {fmt(np.mean(np.abs(err[ix])) if sum(ix) else None)} | {fmt(np.mean(err[ix]) if sum(ix) else None)} |')
add('\n| 样本 ID | DOI | 实测 | 预测 | 绝对误差 |\n|---|---|---:|---:|---:|')
for r in sorted(p,key=lambda r:abs(r['raw_prediction']-r['observed']))[:3]+sorted(p,key=lambda r:abs(r['raw_prediction']-r['observed']),reverse=True)[:3]: add(f"| {r['record_id']} | {r['doi']} | {r['observed']:.2f} | {r['raw_prediction']:.2f} | {abs(r['raw_prediction']-r['observed']):.2f} |")
add('''

个例可能反映训练邻域密度、配方与工况差异、测量噪声或来源口径，但仅凭这些预测不能判定原因。种子 45 的 DOI `10.1016/0926-860x(95)00049-6` 可用留出 2 条 MAE 12.597，样本太少，不代表该体系的普遍误差。逐 DOI 指标与状态见 [E05 metrics](../artifacts/reports/s5-05-e05-20261124-v1/metrics.json)。温度和催化体系逐条关联需要再核对样本表与记录身份；本报告不把未核实的分层推测写成结果。

## 科研结论与建议

当前最可靠的结论是：模型在既有数据分布内有可观的内部预测能力，但跨文献误差显著更大且覆盖下降；单一 MAE 或 R² 不能代表新配方性能。基础组成和工况编码有效，有限搜索、物化扩展及铜基专属块尚未带来稳定可复现的替代优势。瓶颈可能包括文献来源集中、配方与工况共变、名义组成不能描述真实活性结构、来源测量条件异质，以及未知物种支持不足；这些原因需通过新数据检验。

建议优先：① 锁定新 DOI 和独立实验室数据，记录覆盖率、记录及 DOI 等权误差；② 设计按配方/材料族分组的预注册测试，区别插值与外推；③ 核验原文、压力与单位，增加重复实验和误差标注；④ 对代表性铜基配方加入实测负载、分散度、表面结构并在同成员、同折上消融；⑤ 建立校准的不确定度与适用域，先在独立数据上检验，再用于筛选。候选必须经过实验复核，树模型分散度不等于已校准预测区间。

## 原始证据

- [S4 DOI 与随机划分、铜基配对分析](../docs/s4_04_comparison_analysis.md)；[S4 覆盖审计](../docs/s4_04_applicability_coverage.md)。
- [S5-02 全特征消融与逐折结果](../artifacts/reports/s5-02-e01-seed45-range-v2/ablation_analysis.json)；[S5-03 铜基审计](../artifacts/reports/s5-03-m2-audit-20261124/report.md)。
- [S5-04 算法评价](../artifacts/reports/s5-04-e02-20261124-v1/final-review-report.md)；[S5-E05 完整报告](../artifacts/reports/s5-05-e05-20261124-v1/final_report.md)、[逐条留出预测](../artifacts/reports/s5-05-e05-20261124-v1/run-45/holdout/predictions.json)、[五折块置换](../artifacts/reports/s5-05-e05-20261124-v1/fold-permutation.json)。
''')
(out/'科研分析报告.md').write_text('\n'.join(lines),encoding='utf8')
print('report created',len(lines))


