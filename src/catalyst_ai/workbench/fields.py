"""Prototype field dictionary mapped to the existing domain contracts."""

import re

from catalyst_ai.schemas.domain import ValueState

CATEGORIES = ("结构", "性能", "合成方式", "测试工况", "专家知识")


def describe_fields(imported):
    definitions = {item["key"]: dict(item) for item in BUILTINS}
    for item in imported:
        definitions[item["key"]] = {**definitions.get(item["key"], {}), **item}
    for item in definitions.values():
        item.setdefault("data_type", "unknown")
        item.setdefault("version", 1)
        item.setdefault("domain_mapping", "extension." + item["key"])
        item["training_available"] = False
        item["training_requirement"] = "需按特征实现及构建版本核对支持范围"
        item["missing_states"] = [state.value for state in ValueState]
        item["required_scope"] = "按目标与使用阶段检查，未报告值保留 not_reported"
    return list(definitions.values())


def migrate_fields(fields, records):
    """Assign explicit metadata to descriptors from older offline backups."""
    warnings = []
    for item in fields:
        if not isinstance(item, dict) or "data_type" in item or item.get("builtin"):
            continue
        values = [
            record["extras"][item.get("key")]
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("extras"), dict)
            and record["extras"].get(item.get("key")) is not None
        ]
        types = {type(value) for value in values}
        type_names = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            dict: "object",
            list: "array",
        }
        if types and types <= {int, float}:
            data_type = "number"
        elif len(types) == 1:
            data_type = type_names.get(next(iter(types)), "string")
        else:
            data_type = "string"
        item["data_type"] = data_type
        item.setdefault("version", 1)
        warnings.append(f"历史字段 {item.get('key')} 类型迁移为 {data_type}，请复核")
    return warnings


def validate_fields(fields, records):
    errors = []
    definitions = {item["key"]: item for item in BUILTINS}
    keys = set()
    for item in fields:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            errors.append(f"字段 {item.get('id')} 机器键无效")
            continue
        if key in keys:
            errors.append(f"字段机器键重复：{key}")
        keys.add(key)
        if item.get("category") not in CATEGORIES:
            errors.append(f"字段 {key} 分类无效")
        if key not in definitions and item.get("data_type") not in (
            "string",
            "number",
            "integer",
            "boolean",
            "object",
            "array",
        ):
            errors.append(f"自定义字段 {key} 需要明确 data_type")
        if key not in definitions and (type(item.get("version")) is not int or item["version"] < 1):
            errors.append(f"自定义字段 {key} 需要正整数 version")
        definitions[key] = {**definitions.get(key, {}), **item}
    for record in records:
        if not isinstance(record, dict):
            continue
        extras = record.get("extras", {})
        if not isinstance(extras, dict):
            errors.append(f"样本 {record.get('id')} extras 必须是对象")
            continue
        for key, value in extras.items():
            definition = definitions.get(key)
            if definition is None:
                errors.append(f"样本 {record.get('id')} 扩展字段 {key} 未定义")
                continue
            if value is None:
                continue
            valid = {
                "string": isinstance(value, str),
                "number": type(value) in (int, float),
                "integer": type(value) is int,
                "boolean": type(value) is bool,
                "object": isinstance(value, dict),
                "array": isinstance(value, list),
            }.get(definition.get("data_type"), False)
            if not valid:
                errors.append(f"样本 {record.get('id')} 扩展字段 {key} 类型无效")
    return errors


# Names, definitions and original units come from the offline v1.0/v1.1 dictionary.
BUILTINS = [
    {
        "id": "F-001",
        "name": "样本编号",
        "category": "结构",
        "key": "sample_id",
        "unit": "文本",
        "required": True,
        "notes": "与原始文献/实验编号映射",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "TestRun.test_id",
        "training_available": False,
    },
    {
        "id": "F-002",
        "name": "材料体系",
        "category": "结构",
        "key": "material_family",
        "unit": "文本",
        "required": True,
        "notes": "如 Cu/ZnO/Al₂O₃，非预设唯一方向",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "Recipe.material_family",
        "training_available": False,
    },
    {
        "id": "F-003",
        "name": "元素组成",
        "category": "结构",
        "key": "elemental_composition",
        "unit": "文本",
        "required": True,
        "notes": "元素及比例，注明 mol%/wt%",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "Recipe.components",
        "training_available": False,
    },
    {
        "id": "F-004",
        "name": "载体",
        "category": "结构",
        "key": "support",
        "unit": "文本",
        "required": False,
        "notes": "载体或基底",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "Recipe.supports",
        "training_available": False,
    },
    {
        "id": "F-005",
        "name": "助剂/促进剂",
        "category": "结构",
        "key": "promoters",
        "unit": "文本",
        "required": False,
        "notes": "种类、含量、前驱体",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "Recipe.promoters",
        "training_available": False,
    },
    {
        "id": "F-006",
        "name": "物相组成",
        "category": "结构",
        "key": "crystal_phases",
        "unit": "文本",
        "required": False,
        "notes": "XRD/XAS 等证据",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "Characterization.properties.crystal_phases",
        "training_available": False,
    },
    {
        "id": "F-007",
        "name": "比表面积",
        "category": "结构",
        "key": "bet_m2_g",
        "unit": "m²/g",
        "required": False,
        "notes": "BET 方法注明",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "Characterization.properties.bet_m2_g",
        "training_available": False,
    },
    {
        "id": "F-008",
        "name": "Cu分散度",
        "category": "结构",
        "key": "cu_dispersion_pct",
        "unit": "%",
        "required": False,
        "notes": "非铜基体系可不适用",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "Characterization.properties.cu_dispersion_pct",
        "training_available": False,
    },
    {
        "id": "F-009",
        "name": "表面缺陷/氧空位",
        "category": "结构",
        "key": "vacancies",
        "unit": "文本",
        "required": False,
        "notes": "表征方法与定量口径",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "Characterization.properties.vacancies",
        "training_available": False,
    },
    {
        "id": "F-010",
        "name": "合成路径",
        "category": "合成方式",
        "key": "synthesis_method",
        "unit": "文本",
        "required": True,
        "notes": "沉淀/浸渍/溶胶-凝胶等",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "SynthesisRun.route",
        "training_available": False,
    },
    {
        "id": "F-011",
        "name": "前驱体",
        "category": "合成方式",
        "key": "precursor",
        "unit": "文本",
        "required": False,
        "notes": "化学品与纯度",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "SynthesisRun.precursors",
        "training_available": False,
    },
    {
        "id": "F-012",
        "name": "前驱体配比",
        "category": "合成方式",
        "key": "precursor_ratio",
        "unit": "文本",
        "required": False,
        "notes": "标注计量基准",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "SynthesisRun.steps[].parameters.precursor_ratio",
        "training_available": False,
    },
    {
        "id": "F-013",
        "name": "制备pH",
        "category": "合成方式",
        "key": "synthesis_ph",
        "unit": "pH",
        "required": False,
        "notes": "共沉淀等适用",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "SynthesisRun.steps[].parameters.synthesis_ph",
        "training_available": False,
    },
    {
        "id": "F-014",
        "name": "老化温度",
        "category": "合成方式",
        "key": "aging_temp_c",
        "unit": "℃",
        "required": False,
        "notes": "注明时间",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "SynthesisRun.steps[].parameters.aging_temp_c",
        "training_available": False,
    },
    {
        "id": "F-015",
        "name": "干燥条件",
        "category": "合成方式",
        "key": "drying_protocol",
        "unit": "文本",
        "required": False,
        "notes": "温度、时间及气氛",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "SynthesisRun.steps[].parameters.drying_protocol",
        "training_available": False,
    },
    {
        "id": "F-016",
        "name": "焙烧温度",
        "category": "合成方式",
        "key": "calcination_c",
        "unit": "℃",
        "required": False,
        "notes": "注明时间、气氛和升温速率",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "SynthesisRun.steps[].parameters.calcination_c",
        "training_available": False,
    },
    {
        "id": "F-017",
        "name": "还原活化条件",
        "category": "合成方式",
        "key": "reduction_protocol",
        "unit": "文本",
        "required": False,
        "notes": "温度、时间及气氛",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "SynthesisRun.steps[].parameters.reduction_protocol",
        "training_available": False,
    },
    {
        "id": "F-018",
        "name": "反应温度",
        "category": "测试工况",
        "key": "temperature_c",
        "unit": "℃",
        "required": True,
        "notes": "保留原始单位后规范化",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "TestRun.temperature",
        "training_available": False,
    },
    {
        "id": "F-019",
        "name": "反应压力",
        "category": "测试工况",
        "key": "pressure_bar",
        "unit": "bar",
        "required": True,
        "notes": "表压/绝压需明确",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "TestRun.pressure",
        "training_available": False,
    },
    {
        "id": "F-020",
        "name": "空速GHSV",
        "category": "测试工况",
        "key": "ghsv_h",
        "unit": "h⁻¹",
        "required": True,
        "notes": "标况/床层体积基准须明确",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "TestRun.ghsv",
        "training_available": False,
    },
    {
        "id": "F-021",
        "name": "原料气组成",
        "category": "测试工况",
        "key": "feed_composition",
        "unit": "mol%",
        "required": True,
        "notes": "H₂/CO₂/CO/惰性气等",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "TestRun.feed",
        "training_available": False,
    },
    {
        "id": "F-022",
        "name": "催化剂装填量",
        "category": "测试工况",
        "key": "catalyst_mass_g",
        "unit": "g",
        "required": False,
        "notes": "筛分粒度及稀释方式",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "TestRun.catalyst_mass",
        "training_available": False,
    },
    {
        "id": "F-023",
        "name": "反应器类型",
        "category": "测试工况",
        "key": "reactor_type",
        "unit": "文本",
        "required": False,
        "notes": "固定床等",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "TestRun.reactor",
        "training_available": False,
    },
    {
        "id": "F-024",
        "name": "稳态与测试时间",
        "category": "测试工况",
        "key": "time_on_stream_h",
        "unit": "h",
        "required": False,
        "notes": "老化/稳态判据",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "TestRun.time_on_stream",
        "training_available": False,
    },
    {
        "id": "F-025",
        "name": "重复次数",
        "category": "测试工况",
        "key": "replicate_n",
        "unit": "次",
        "required": False,
        "notes": "独立重复与重复测量区分",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "extension.replicate_n",
        "training_available": False,
    },
    {
        "id": "F-026",
        "name": "CO₂转化率",
        "category": "性能",
        "key": "co2_conversion_pct",
        "unit": "%",
        "required": True,
        "notes": "明确基于进口CO₂摩尔流量",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "Observation[co2_conversion].value",
        "training_available": False,
    },
    {
        "id": "F-027",
        "name": "甲醇选择性",
        "category": "性能",
        "key": "meoh_selectivity_pct",
        "unit": "%",
        "required": True,
        "notes": "明确碳基选择性/口径",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "Observation[methanol_selectivity].value",
        "training_available": False,
    },
    {
        "id": "F-028",
        "name": "甲醇收率",
        "category": "性能",
        "key": "meoh_yield_pct",
        "unit": "%",
        "required": False,
        "notes": "只在转化率与选择性同基准时派生",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "Observation[methanol_yield].value",
        "training_available": False,
    },
    {
        "id": "F-029",
        "name": "甲醇时空产率",
        "category": "性能",
        "key": "meoh_sty",
        "unit": "g/(gcat·h)",
        "required": False,
        "notes": "若来源单位不同需显式换算",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "Observation[methanol_sty].value",
        "training_available": False,
    },
    {
        "id": "F-030",
        "name": "碳平衡闭合率",
        "category": "性能",
        "key": "carbon_balance_pct",
        "unit": "%",
        "required": False,
        "notes": "缺失时不得默认可信",
        "builtin": True,
        "data_type": "number",
        "version": 1,
        "domain_mapping": "Observation.carbon_balance",
        "training_available": False,
    },
    {
        "id": "F-031",
        "name": "稳定性/失活",
        "category": "性能",
        "key": "stability",
        "unit": "文本",
        "required": False,
        "notes": "采样周期与工况变化",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "extension.stability",
        "training_available": False,
    },
    {
        "id": "F-032",
        "name": "不确定度",
        "category": "性能",
        "key": "uncertainty",
        "unit": "文本",
        "required": False,
        "notes": "误差棒、重复性和报告口径",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "Measurement.uncertainty",
        "training_available": False,
    },
    {
        "id": "F-033",
        "name": "专家判断",
        "category": "专家知识",
        "key": "expert_note",
        "unit": "文本",
        "required": False,
        "notes": "经验性判断与观测事实分开",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "extension.expert_note",
        "training_available": False,
    },
    {
        "id": "F-034",
        "name": "机理假设",
        "category": "专家知识",
        "key": "mechanism_hypothesis",
        "unit": "文本",
        "required": False,
        "notes": "记录可证伪假设",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "extension.mechanism_hypothesis",
        "training_available": False,
    },
    {
        "id": "F-035",
        "name": "约束/禁用工艺",
        "category": "专家知识",
        "key": "synthesis_constraint",
        "unit": "文本",
        "required": False,
        "notes": "设备、安全、成本约束",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "extension.synthesis_constraint",
        "training_available": False,
    },
    {
        "id": "F-036",
        "name": "知识证据来源",
        "category": "专家知识",
        "key": "knowledge_evidence",
        "unit": "文本",
        "required": False,
        "notes": "专家/文献/实验及日期",
        "builtin": True,
        "data_type": "string",
        "version": 1,
        "domain_mapping": "extension.knowledge_evidence",
        "training_available": False,
    },
]
