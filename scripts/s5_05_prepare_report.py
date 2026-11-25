import json,statistics,shutil,subprocess,sys,zipfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'artifacts/reports/s5-05-e05-20261124-v1'; M=R/'artifacts/models/s5-e05-20261124-v1'
def rd(p):return json.loads(p.read_text(encoding='utf8'))
m=rd(O/'metrics.json');d=rd(O/'applicability-and-permutation.json'); f=rd(O/'fold-permutation.json');hist=rd(O/'historical-r2.json'); tr=rd(O/'training-trace.json')
M.mkdir(parents=True,exist_ok=False)
for n in ('config.json','split.json','cross_validation.json','model.pkl','run.log','lock.json'):shutil.copy2(O/'run-45'/n,M/n)
with zipfile.ZipFile(O/'source-snapshot.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted((R/'src/catalyst_ai').rglob('*.py')):z.write(p,p.relative_to(R).as_posix())
 for p in (R/'pyproject.toml',R/'uv.lock'):z.write(p,p.relative_to(R).as_posix())
r=subprocess.run([sys.executable,'-m','pip','freeze'],capture_output=True,text=True,encoding='utf8'); (O/'environment-freeze.txt').write_text(r.stdout if r.returncode==0 else 'pip freeze unavailable; environment versions recorded in lock.json\n',encoding='utf8')
lines=[]
for s,x in m.items():
 a=x['holdout']['0'];v=a['available'];o=x['oof']['0']['available'];common=x['holdout_common']['overall'];base=common['arms']['0']['common']['mae']; xgb=common['arms']['6']['common']['mae'];
 lines.append(f"| {s} | {o['mae']:.3f} | {a['available_n']}/{a['total']} | {v['mae']:.3f} | {v['rmse']:.3f} | {v['r2']:.3f} | {a['doi_equal_mae']:.3f} ({a['doi_n']}) | {len(common['common_ids'])} | {base:.3f} / {xgb:.3f} |")
fold=[]
for s,fs in f.items():
 line=[]
 for k in ('conditions','composition'):
  vals=[x['blocks'][k]['mean'] for x in fs]; line.append(f'{statistics.mean(vals):.3f} ({min(vals):.3f}–{max(vals):.3f})')
 fold.append(f'| {s} | {line[0]} | {line[1]} |')
report='''# S5-05 综合模型评价与收口报告 v1

## 决策与范围

S5-E05 在用户批准 XGBoost 后作为 S5-05 新研究开展，不重新开启 S5-04。方案、三份配置、F3 训练侧判定和技术预检均在训练前登记；训练完成并锁定全部种子后分别进行一次留出评分。三个种子均由训练 OOF 的 s5-paired-v1 平局规则保留 F_base/Extra Trees 固定基线，主模型为预定主种子 45 的该模型。F3-P 在各自训练侧被选为组合研究的 F3；并非依据留出选择。18 臂×3 种子均已完成，单算法每特征各三组；为统一选择重新拟合包括可复用的基线与 F_base 参数组，属于重复计算，并未替换或改写 S5-02～04 原证据。现有留出数据此前已被观察，包括 S5-04 事后技术验证，故全部结果为内部探索性评价，不是独立盲测或外部泛化性能。

## 性能与稳定性

误差单位为 CO₂ 转化率百分点。入口可用为 ok/caution 且预测有限；DOI 等权先在每个 DOI 的入口可用记录内计算 MAE，再对 DOI 等权。XGB 固定参数为 100 树、深度 3、学习率 0.1；共同集为 18 臂严格交集，因此与各自可用 MAE 的分母不同。数值只作描述，未用于选择。

| 种子 | 基线 OOF MAE | 留出覆盖 | 留出 MAE | RMSE | R² | DOI 等权 MAE (DOI 数) | 18 臂共同数 | 共同集 ET / XGB MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
'''+ '\n'.join(lines)+'''

全臂、逐折和每 DOI 指标、原始 ID、严格共同集、偏差及残差范围见 [metrics.json](metrics.json)；每种子训练侧资格与平局轨迹见各运行 `cross_validation.json`。每个种子的留出总数均为 108，诊断预测包含不满足入口状态的有限预测，指标与可用集分别列出。多种子训练/留出成员重叠，种子间波动相关，不能视作独立重复实验。R² 仅报告；历史可核验预测按相同口径补算，见 [historical-r2.json](historical-r2.json)，覆盖 S4 九次以及 S5-02～04 相关可找到运行，不覆盖原文件；其他无法取得逐条可核对预测的更早历史成果不能补算。

## 特征贡献与铜基

对固定基线训练内五折重拟合并逐条核对原 OOF，在各折入口可用记录上联合置换，10 次重复的 MAE 增量如下；括号为五折均值范围。

| 种子 | 工况块 | 组成块 |
|---|---:|---:|
'''+ '\n'.join(fold)+'''

逐折人数和置换次数在 [fold-permutation.json](fold-permutation.json)。联合置换可能生成不现实组合，相关特征共享贡献，故不是因果证据。物化特征使用 S5-02 的 F_base/F1/F2/F3 同折消融，Cu 特征使用 S5-03 B1/B2 同训练铜基成员及折的消融；二者是模型间对照而非独立块置换。S5-03 三种子 Cu 块留出配对 MAE 增量分别 +0.0285、+0.0692、+0.0084 百分点，共同可用分别 39、49、44；无稳定增益或等效性的证明。材料来源角色和名义中心量并非原文逐篇核实的活性位或实测负载，详见 [S5-03 报告](../s5-03-m2-audit-20261124/report.md)。

## 适用范围与后续

主种子训练 434 条：温度 433–673 K，绝压 0.4–50 bar，H₂/CO₂ 3–5，反应物质量归一流量 0.87–40 NL/g_cat/h；组成与角色词表、每种子工况范围及警示数量见 [applicability-and-permutation.json](applicability-and-permutation.json)。主种子留出 101 ok、5 caution、2 未见物种角色而入口不可用。范围为单变量边界，不能保证边界内所有组合可靠。S5-03 铜基 211 条、16 DOI，铜基训练温度不超过 553 K，具体来源及覆盖缺口见其审计。新催化剂、未见物种/角色、跨体系与新 DOI 均需后续独立数据验证；D-06 尚待合格新来源。树模型输出不构成校准不确定性区间。

S5-04 有两项限定范围事前程序例外，详见其[最终验收说明](../s5-04-final-acceptance-v1/final-acceptance.md)，不得据后补材料声称事前程序已发生。本次技术验证复用已验证合成和独立发布材料，并事前对全部配置预检、测试及正式登记。原始 S4 包采用原环境重放的记录见 S5-03 和 S5-04 验收证据。

## 文件和复现

主模型与模型卡见 [model_card.md](model_card.md)，局限见 [limitations.md](limitations.md)。预登记和各配置在本目录，运行含逐条 OOF、留出、状态、候选、模型及锁；数据、源代码和依赖在锁内固定，源码归档为 source-snapshot.zip。实际研究运行使用 `.venv-xgb-release` 的 Python，环境版本以各锁文件为准。证据文件与散列见 evidence-sha256.json；审核提交不等于审核通过。
'''
(O/'final_report.md').write_text(report,encoding='utf8')
card='''# 模型卡：S5-E05 主种子 45 固定基线 v1

- 用途：在已有 TheMeCat 文献数据的相近材料、工况和角色定义范围内研究 CO₂ 转化率点预测，单位为百分数/百分点；不得把结果视为实验替代或新催化剂的外部验证。
- 模型：F_base/Extra Trees，100 树、最小叶 2、深度不限、max_features 1.0、模型种子 42、单线程。模型目录 `artifacts/models/s5-e05-20261124-v1/` 保存主种子的正式研究锁及全报告臂包；索引 0 是选定模型。研究模型 pickle 仅从可信来源加载，需匹配锁定源码和环境。
- 数据：S4 全体系共同资格 542，主划分训练 434、留出 108；身份组隔离，训练五折。输入为四项工况和来源角色下组成 mol%；物种/角色未见时入口拒绝，范围超出时发出 caution。
- 训练侧选择：S5-paired-v1 的 OOF 记录等权 MAE、覆盖和共同支持规则；0.1 百分点平局优先固定基线。R² 不用于选模。
- 内部留出：入口可用 106/108；记录等权 MAE 2.085、RMSE 3.483、R² 0.844；27 个 DOI 等权 MAE 2.387 百分点。此前留出已被观察，以上并非独立外部验证。
- 训练工况范围：433–673 K，0.4–50 bar(abs)，H₂/CO₂ 3–5，反应物质量归一流量 0.87–40 NL/g_cat/h。各维度边界不构成联合适用域保证。历史来源集中、计量和绝压假设，以及未见催化剂/新 DOI 外推均受限。
- 逐条状态、预测及版本证据见 `artifacts/reports/s5-05-e05-20261124-v1/`；不提供已校准预测区间。
'''
(O/'model_card.md').write_text(card,encoding='utf8');(M/'model_card.md').write_text(card,encoding='utf8')
(O/'limitations.md').write_text('''# S5-05 局限和下一阶段缺口

- 本轮留出以及历史留出此前已观察，结果为观察后内部探索，不能称盲测或独立外部评价。多次划分有成员重叠且相关。
- S4 铜基 211 条、16 DOI，来源不均；来源角色、材料 mol% 和名义中心数依赖目录及记录，原文抽取尚未逐篇核实。绝压口径含假设。
- 训练区间仅为边际范围，未见物种/角色硬拒绝，超范围给予 caution；区间内新组合、新催化剂及跨体系性能未知。新的独立 DOI 和铜基覆盖是下一阶段重点，D-06 仍待合格新来源。
- 工况及组成联合置换为事后模型依赖诊断，相关性和不现实组合影响解释；物化和 Cu 使用同折消融，不支持因果推断。树间分散度不构成校准预测区间。
- S5-04 两项限定范围事前程序例外已记录于其最终验收，不追认缺失的事前凭证。历史早期无法逐条核对的实验未补算 R²。S5-03 的材料原文核验缺口应在来源就绪后复启。
''',encoding='utf8')
print('report and primary model package prepared')
