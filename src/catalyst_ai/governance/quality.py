import math
from decimal import Decimal, InvalidOperation
from typing import Literal

from catalyst_ai.config import Settings
from catalyst_ai.schemas.domain import (
    Component,
    Contract,
    ImportRecord,
    Measurement,
    ReviewStatus,
    ValueState,
)


class Issue(Contract):
    code: str
    severity: Literal["warning", "block"]
    path: str
    message: str


def measurements(value, path=""):
    """Walk numerical fields, including synthesis and characterization, without mixing layers."""
    if isinstance(value, Measurement):
        yield path, value
    elif isinstance(value, Contract):
        for name in type(value).model_fields:
            yield from measurements(getattr(value, name), f"{path}.{name}".lstrip("."))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from measurements(item, f"{path}[{i}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from measurements(item, f"{path}.{key}")


def govern(record: ImportRecord, settings: Settings) -> tuple[ImportRecord, list[Issue]]:
    record = record.model_copy(deep=True)
    issues = []

    def flag(code, path, message, severity="block", measurement=None):
        issues.append(Issue(code=code, path=path, message=message, severity=severity))
        if measurement is not None and code not in measurement.quality_flags:
            measurement.quality_flags.append(code)

    if record.source is None:
        flag("source_missing", "source", "来源文档缺失")
    elif record.source.kind == "literature" and not record.source.doi:
        flag("source_identifier_incomplete", "source.doi", "缺少DOI；须核查文献标识", "warning")
    elif record.source.kind == "internal" and not record.source.internal_reference:
        flag("source_identifier_incomplete", "source.internal_reference", "内部实验编号缺失")
    if record.source and record.source.license == "unknown":
        flag("license_unknown", "source.license", "未审计使用授权", "warning")
    if record.extraction is None:
        flag("locator_missing", "extraction", "缺少页/表/图/内部记录定位及抽取方法")
    elif not record.extraction.locator.strip():
        flag("locator_missing", "extraction.locator", "来源定位不得仅为空白")
    elif record.extraction.status != ReviewStatus.PENDING:
        flag("untrusted_review", "extraction.status", "导入文件不能自授核验状态")
        record.extraction.status = ReviewStatus.PENDING

    parsed = {}
    for path, m in measurements(record):
        if m.normalized_value is not None or m.normalized_unit is not None:
            flag("imported_normalization_ignored", path, "重算导入的标准值", "warning")
        m.normalized_value = None
        m.normalized_unit = None
        m.quality_flags = []
        if m.extraction_status != ReviewStatus.PENDING:
            flag("untrusted_review", path, "数值核验状态只能由人工审核建立", measurement=m)
        m.extraction_status = ReviewStatus.PENDING
        if m.source_locator is None:
            if m.raw_value is not None:
                flag("value_locator_missing", path, "已报告数值缺少来源定位", measurement=m)
        elif record.extraction is None or m.source_locator != record.extraction.extraction_id:
            flag("value_locator_mismatch", path, "数值定位未引用本记录抽取证据", measurement=m)
        if m.state not in {ValueState.REPORTED, ValueState.ZERO}:
            flag(
                "value_" + m.state.value,
                path,
                "保留原缺失/未知/无效语义，不填零",
                "block" if m.state == ValueState.INVALID else "warning",
                m,
            )
            continue
        try:
            number = Decimal(m.raw_value)
            if not number.is_finite() or not math.isfinite(float(number)):
                raise InvalidOperation
        except (InvalidOperation, ValueError, OverflowError):
            flag("invalid_number", path, "数值不是有限十进制数；不猜测范围或约数", measurement=m)
            continue
        if (number == 0) != (m.state == ValueState.ZERO):
            flag("zero_state_mismatch", path, "零必须显式使用zero状态", measurement=m)
            continue
        parsed[path] = number
        if m.raw_unit == "%":
            if not 0 <= number <= 100:
                flag("percentage_range", path, "百分数必须在[0,100]", measurement=m)
            else:
                m.normalized_value, m.normalized_unit = float(number), "%"
        elif m.raw_unit is None:
            flag("unit_unknown", path, "已报告数值必须注明单位；无量纲用1", measurement=m)
        elif m.raw_unit in {"1", "g", "h", "min", "nm", "m2/g", "g_MeOH/g_cat/h"}:
            m.normalized_value, m.normalized_unit = float(number), m.raw_unit
        # Field-specific physical units are handled below. Other units remain raw.

    def normalize(m, path, table, unit, lower_bound=None, strictly_positive=False):
        if path not in parsed:
            flag("critical_value_missing", path, "关键工况未报告或无效", measurement=m)
            return
        if m.raw_unit not in table:
            flag("unit_unknown", path, "单位不明或不适用于此字段，禁止猜测", measurement=m)
            m.normalized_value, m.normalized_unit = None, None
            return
        scale, offset = table[m.raw_unit]
        number = parsed[path] * Decimal(str(scale)) + Decimal(str(offset))
        if (lower_bound is not None and number < lower_bound) or (
            strictly_positive and number <= 0
        ):
            flag("physical_range", path, "超出基本物理范围", measurement=m)
            m.normalized_value, m.normalized_unit = None, None
            return
        if not math.isfinite(float(number)):
            flag("numeric_overflow", path, "单位转换溢出，保留原值", measurement=m)
            return
        m.normalized_value, m.normalized_unit = float(number), unit

    normalize(
        record.test.temperature,
        "test.temperature",
        {"K": (1, 0), "degC": (1, 273.15), "°C": (1, 273.15)},
        "K",
        Decimal("0"),
        strictly_positive=True,
    )
    if record.test.pressure_type != "absolute":
        flag(
            "pressure_basis_unknown",
            "test.pressure_type",
            "仅绝压可规范为bar(abs)",
            measurement=record.test.pressure,
        )
        record.test.pressure.normalized_value = None
        record.test.pressure.normalized_unit = None
    else:
        normalize(
            record.test.pressure,
            "test.pressure",
            {"bar": (1, 0), "MPa": (10, 0), "kPa": (0.01, 0), "Pa": (0.00001, 0)},
            "bar(abs)",
            Decimal("0"),
            strictly_positive=True,
        )
    mass_mode = (
        record.schema_version == "2" and record.test.flow_mode == "mass_normalized_reactants"
    )
    if not mass_mode:
        normalize(
            record.test.ghsv,
            "test.ghsv",
            {"h^-1": (1, 0), "1/h": (1, 0)},
            "h^-1",
            Decimal("0"),
            strictly_positive=True,
        )
        basis = record.test.ghsv_basis
        basis_valid = basis is not None
        if basis:
            normalize(
                basis.reference_temperature,
                "test.ghsv_basis.reference_temperature",
                {"K": (1, 0), "degC": (1, 273.15), "°C": (1, 273.15)},
                "K",
                strictly_positive=True,
            )
            if basis.reference_pressure_type == "absolute":
                normalize(
                    basis.reference_pressure,
                    "test.ghsv_basis.reference_pressure",
                    {"bar": (1, 0), "MPa": (10, 0), "kPa": (0.01, 0), "Pa": (0.00001, 0)},
                    "bar(abs)",
                    strictly_positive=True,
                )
            basis_valid = (
                basis.reference_temperature.normalized_value is not None
                and basis.reference_pressure.normalized_value is not None
                and basis.reference_pressure_type == "absolute"
                and basis.catalyst_volume_basis != "unknown"
            )
        if not basis_valid:
            flag(
                "ghsv_basis_unknown",
                "test.ghsv_basis",
                "须明确流量标准状态及催化剂体积基准",
                measurement=record.test.ghsv,
            )
            record.test.ghsv.normalized_value = None
            record.test.ghsv.normalized_unit = None

    else:
        flow = record.test.mass_normalized_volume_flow
        ratio = record.test.reactant_ratio
        if record.test.ghsv.raw_value is not None or record.test.ghsv_basis is not None:
            flag("conflicting_flow_modes", "test.ghsv", "质量流量模式不能同时声明体积GHSV")
        if flow is None:
            flag("mass_flow_missing", "test.mass_normalized_volume_flow", "????????")
        else:
            root = "test.mass_normalized_volume_flow"
            normalize(
                flow.value,
                root + ".value",
                {"NL/g_cat/h": (1, 0)},
                "NL/g_cat/h",
                strictly_positive=True,
            )
            normalize(
                flow.reference_temperature,
                root + ".reference_temperature",
                {"K": (1, 0)},
                "K",
                strictly_positive=True,
            )
            if flow.reference_pressure_type == "absolute":
                normalize(
                    flow.reference_pressure,
                    root + ".reference_pressure",
                    {"Pa": (0.00001, 0), "bar": (1, 0)},
                    "bar(abs)",
                    strictly_positive=True,
                )
            if (
                flow.reference_pressure_type != "absolute"
                or flow.reference_pressure.normalized_value is None
                or flow.reference_temperature.normalized_value is None
                or flow.mass_basis != "catalyst"
                or flow.gas_scope != "reactants_only"
                or not flow.definition_source
                or not flow.definition_source.strip()
            ):
                flag("mass_flow_basis_unknown", root, "???????????????????????")
                flow.value.normalized_value = flow.value.normalized_unit = None
        if ratio is None:
            flag("reactant_ratio_missing", "test.reactant_ratio", "???????")
        else:
            normalize(
                ratio.value, "test.reactant_ratio.value", {"1": (1, 0)}, "1", strictly_positive=True
            )
            if not ratio.definition_source or not ratio.definition_source.strip():
                flag("reactant_ratio_basis_unknown", "test.reactant_ratio", "?????????")
                ratio.value.normalized_value = ratio.value.normalized_unit = None
        if record.test.feed:
            closure_feed_later = True
        else:
            closure_feed_later = False
            flag("full_feed_not_reported", "test.feed", "?????????", "warning")

    def closure(items: list[Component], basis: str, root: str, scope=None):
        if not items:
            flag("composition_missing", root, "组成/进料缺失")
            return
        species = [c.species for c in items]
        if len(species) != len(set(species)):
            flag("duplicate_component", root, "同组分重复，须人工核实")
        for i, c in enumerate(items):
            path = f"{root}[{i}].amount"
            if path in parsed and parsed[path] < 0:
                flag("negative_composition", path, "组成/进料不得为负", measurement=c.amount)
            if root == "test.feed" and c.role != "gas":
                flag("feed_role_invalid", path, "进料组分role必须为gas")
        if basis in {"unknown", "ratio"}:
            flag(
                "closure_not_assessable",
                root,
                "未知或比例基准不执行百分比闭合检查",
                "block" if basis == "unknown" else "warning",
            )
            if basis == "ratio":
                ratio_values = []
                for i, c in enumerate(items):
                    path = f"{root}[{i}].amount"
                    if path not in parsed or c.amount.raw_unit != "1":
                        flag(
                            "ratio_incomplete",
                            path,
                            "比例须全部为已报告无量纲数",
                            measurement=c.amount,
                        )
                    else:
                        ratio_values.append(parsed[path])
                if len(ratio_values) == len(items) and sum(ratio_values) <= 0:
                    flag("ratio_zero_total", root, "组成比例总量必须大于零")
            return
        if root == "recipe.components" and not scope:
            flag("composition_scope_missing", root, "未说明组成归一范围")
        values = []
        for i, c in enumerate(items):
            path = f"{root}[{i}].amount"
            if path not in parsed or c.amount.raw_unit != "%":
                flag(
                    "closure_incomplete", path, "百分比闭合需要全部有效百分比", measurement=c.amount
                )
            else:
                values.append(parsed[path])
        if len(values) == len(items) and abs(sum(values) - 100) > Decimal(
            str(settings.closure_tolerance_pct)
        ):
            flag("closure_failed", root, "组成之和超出100%允许误差；不自动归一化")

    if record.schema_version == "2":
        if record.recipe.composition_available != "yes":
            flag(
                "composition_availability_unconfirmed",
                "recipe.composition_available",
                "组成可用性未确认",
            )
        if not record.recipe.composition_definition_source:
            flag(
                "composition_definition_missing",
                "recipe.composition_definition_source",
                "组成定义来源缺失",
            )
        if record.recipe.orphan_amount_fields:
            flag("orphan_composition_amount", "recipe.orphan_amount_fields", "含量缺少对应材料物种")
    closure(
        record.recipe.components,
        record.recipe.composition_basis,
        "recipe.components",
        record.recipe.composition_scope,
    )
    if not mass_mode or closure_feed_later:
        closure(record.test.feed, record.test.feed_basis, "test.feed")
    for i, obs in enumerate(record.observations):
        path = f"observations[{i}].value"
        if not obs.value.definition:
            flag("metric_definition_missing", path, "指标计量口径必须明确", measurement=obs.value)
        reported = obs.value.state in {ValueState.REPORTED, ValueState.ZERO}
        if reported and obs.metric in {"co2_conversion", "methanol_selectivity", "methanol_yield"}:
            if obs.value.raw_unit != "%":
                flag(
                    "metric_unit_unknown",
                    path,
                    "此最小适配器要求百分比单位%",
                    measurement=obs.value,
                )
        if reported and obs.metric == "methanol_sty" and obs.value.raw_unit != "g_MeOH/g_cat/h":
            flag(
                "sty_basis_unknown", path, "STY基准或单位不受支持，保留原值", measurement=obs.value
            )
        if path in parsed and parsed[path] < 0:
            flag("negative_performance", path, "性能值为负，须人工核查", measurement=obs.value)
    # Unsupported synthesis/characterization units are retained and explicitly flagged.
    for path, m in measurements(record):
        if path in parsed and m.normalized_value is None and not m.quality_flags:
            flag("unit_not_normalized", path, "暂不规范此单位，原值保留", "warning", m)
    return record, issues
