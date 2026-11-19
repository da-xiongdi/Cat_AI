"""Research roadmap nodes and task associations."""

import hashlib
import json
import re

from catalyst_ai.storage.workbench import connect, now
from catalyst_ai.workbench.adapters import safe_path
from catalyst_ai.workbench.deliveries import _inspect
from catalyst_ai.workbench.service import Conflict, Missing, _json, _text, _write


def _save(db, table, project_id, entity_id, values, expected, reason, actor):
    old = db.execute(f"SELECT * FROM {table} WHERE id=?", (entity_id,)).fetchone()
    if old and old["project_id"] != project_id:
        raise ValueError("entity belongs to another project")
    if (old["revision"] if old else 0) != expected:
        raise Conflict("revision conflict")
    if old and all(old[k] == v for k, v in values.items()):
        return dict(old)
    revision = expected + 1
    if old:
        assignments = ",".join(f"{k}=?" for k in values)
        db.execute(
            f"UPDATE {table} SET {assignments},revision=? WHERE id=?",
            (*values.values(), revision, entity_id),
        )
    else:
        columns = ",".join(values)
        marks = ",".join("?" for _ in values)
        db.execute(
            f"INSERT INTO {table}(id,project_id,{columns},revision) VALUES(?,?,{marks},?)",
            (entity_id, project_id, *values.values(), revision),
        )
    new = dict(db.execute(f"SELECT * FROM {table} WHERE id=?", (entity_id,)).fetchone())
    db.execute(
        f"INSERT INTO {table}_revision VALUES(?,?,?,?,?,?,?,?)",
        (
            entity_id,
            project_id,
            revision,
            _json(dict(old)) if old else None,
            _json(new),
            reason,
            actor,
            now(),
        ),
    )
    db.execute(
        "INSERT INTO activity(project_id,task_id,action,actor,created_at,summary) "
        "VALUES(?,?,?,?,?,?)",
        (
            project_id,
            values.get("task_id"),
            table + "_saved",
            actor,
            now(),
            _json({"id": entity_id, "revision": revision, "reason": reason}),
        ),
    )
    return new


def save_research_node(
    path, project_id, node_id, data, expected_revision, reason, *, request_id, actor
):
    node_id, reason = _text(node_id, "node_id"), _text(reason, "reason")
    values = {
        k: data.get(k)
        for k in (
            "stage",
            "parent_id",
            "sort_order",
            "source_path",
            "source_section",
            "source_sha256",
            "active",
        )
    }
    values["active"] = data.get("active", 1)
    if (
        values["stage"] not in ("A", "B", "C", "D", "E", "F")
        or not isinstance(values["sort_order"], int)
        or values["active"] not in (0, 1)
    ):
        raise ValueError("invalid node fields")
    for key in ("source_path", "source_section", "source_sha256"):
        values[key] = _text(values[key], key)
    if not re.fullmatch(r"[0-9a-f]{64}", values["source_sha256"]):
        raise ValueError("invalid source hash")

    def run(db, actor):
        if not db.execute("SELECT 1 FROM project WHERE id=?", (project_id,)).fetchone():
            raise Missing("project not found")
        workspace = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        previous = db.execute("SELECT * FROM research_node WHERE id=?", (node_id,)).fetchone()
        retiring = (
            previous is not None
            and previous["project_id"] == project_id
            and not values["active"]
            and all(
                previous[key] == values[key]
                for key in (
                    "stage",
                    "parent_id",
                    "sort_order",
                    "source_path",
                    "source_section",
                    "source_sha256",
                )
            )
        )
        if not retiring and (
            not workspace
            or _inspect(
                workspace["root"],
                values["source_path"],
                values["source_section"],
                values["source_sha256"],
            )
            != "valid"
        ):
            raise Conflict("node source requires review")
        if previous and previous["project_id"] == project_id and previous["parent_id"] is None:
            if (
                values["parent_id"] is not None
                or values["stage"] != previous["stage"]
                or values["sort_order"] != previous["sort_order"]
                or not values["active"]
            ):
                raise ValueError("stage root identity and order cannot change")
        elif previous and values["stage"] != previous["stage"]:
            raise ValueError("node cannot move across stages")
        if previous and previous["parent_id"] and not values["parent_id"]:
            raise ValueError("branch requires a parent")
        parent = values["parent_id"]
        seen = {node_id}
        while parent:
            if parent in seen:
                raise ValueError("node cycle")
            seen.add(parent)
            row = db.execute("SELECT * FROM research_node WHERE id=?", (parent,)).fetchone()
            if (
                not row
                or row["project_id"] != project_id
                or not row["active"]
                or row["stage"] != values["stage"]
            ):
                raise ValueError("invalid parent or stage")
            parent = row["parent_id"]
        if db.execute(
            "SELECT 1 FROM research_node WHERE parent_id=? AND active=1 AND (stage<>? OR ?=0)",
            (node_id, values["stage"], values["active"]),
        ).fetchone():
            raise ValueError("active children require active parent in same stage")
        if db.execute(
            "SELECT 1 FROM task_node_link l JOIN task t ON t.id=l.task_id WHERE "
            "l.node_id=? AND l.active=1 AND (?=0 OR NOT EXISTS "
            "(SELECT 1 FROM json_each(t.stages) WHERE value=?))",
            (node_id, values["active"], values["stage"]),
        ).fetchone():
            raise ValueError("active task links incompatible with node")
        return _save(
            db, "research_node", project_id, node_id, values, expected_revision, reason, actor
        )

    return _write(
        path,
        request_id,
        actor,
        "save_research_node",
        [project_id, node_id, values, expected_revision, reason],
        run,
    )


def save_task_node_link(
    path, project_id, link_id, data, expected_revision, reason, *, request_id, actor
):
    link_id, reason = _text(link_id, "link_id"), _text(reason, "reason")
    values = {k: data.get(k) for k in ("task_id", "node_id", "role")}
    values["active"] = data.get("active", 1)
    if values["role"] not in ("primary", "reference") or values["active"] not in (0, 1):
        raise ValueError("invalid link")

    def run(db, actor):
        task = db.execute("SELECT * FROM task WHERE id=?", (values["task_id"],)).fetchone()
        node = db.execute("SELECT * FROM research_node WHERE id=?", (values["node_id"],)).fetchone()
        if (
            not task
            or not node
            or task["project_id"] != project_id
            or node["project_id"] != project_id
        ):
            raise ValueError("task and node must belong to project")
        if values["active"] and (
            task["category"] != "research"
            or not node["active"]
            or node["stage"] not in json.loads(task["stages"])
        ):
            raise ValueError("task category or stage incompatible")
        if (
            values["active"]
            and db.execute(
                "SELECT 1 FROM task_node_link WHERE active=1 AND task_id=? AND id<>? AND "
                "((node_id=? AND role=?) OR (role='primary' AND ?='primary'))",
                (values["task_id"], link_id, values["node_id"], values["role"], values["role"]),
            ).fetchone()
        ):
            raise Conflict("duplicate link or primary")
        return _save(
            db, "task_node_link", project_id, link_id, values, expected_revision, reason, actor
        )

    return _write(
        path,
        request_id,
        actor,
        "save_task_node_link",
        [project_id, link_id, values, expected_revision, reason],
        run,
    )


def move_primary_to_reference(
    path,
    project_id,
    primary_id,
    primary_revision,
    reference_id,
    reference_revision,
    reason,
    *,
    request_id,
    actor,
):
    """Move a primary to its existing reference, retiring the reference atomically."""
    reason = _text(reason, "reason")
    primary_id = _text(primary_id, "primary link ID")
    reference_id = _text(reference_id, "reference link ID")

    def run(db, actor):
        primary = db.execute("SELECT * FROM task_node_link WHERE id=?", (primary_id,)).fetchone()
        reference = db.execute(
            "SELECT * FROM task_node_link WHERE id=?", (reference_id,)
        ).fetchone()
        if (
            not primary
            or not reference
            or any(row["project_id"] != project_id for row in (primary, reference))
        ):
            raise Missing("link not found")
        if primary["revision"] != primary_revision or reference["revision"] != reference_revision:
            raise Conflict("link revision conflict")
        if (
            not primary["active"]
            or not reference["active"]
            or primary["role"] != "primary"
            or reference["role"] != "reference"
            or primary["task_id"] != reference["task_id"]
        ):
            raise ValueError("active primary and reference for the same task required")
        node = db.execute(
            "SELECT * FROM research_node WHERE id=?", (reference["node_id"],)
        ).fetchone()
        task = db.execute("SELECT * FROM task WHERE id=?", (primary["task_id"],)).fetchone()
        if (
            not node
            or not node["active"]
            or node["project_id"] != project_id
            or not task
            or task["category"] != "research"
            or node["stage"] not in json.loads(task["stages"])
        ):
            raise ValueError("task category or stage incompatible")
        retired = _save(
            db,
            "task_node_link",
            project_id,
            reference_id,
            {
                "task_id": reference["task_id"],
                "node_id": reference["node_id"],
                "role": "reference",
                "active": 0,
            },
            reference_revision,
            reason,
            actor,
        )
        moved = _save(
            db,
            "task_node_link",
            project_id,
            primary_id,
            {
                "task_id": primary["task_id"],
                "node_id": reference["node_id"],
                "role": "primary",
                "active": 1,
            },
            primary_revision,
            reason,
            actor,
        )
        return {"primary": moved, "reference": retired}

    return _write(
        path,
        request_id,
        actor,
        "move_primary_to_reference",
        [project_id, primary_id, primary_revision, reference_id, reference_revision, reason],
        run,
    )


def list_research_nodes(path, project_id):
    db = connect(path)
    try:
        workspace = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        nodes = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM research_node WHERE project_id=? AND active=1 ORDER BY "
                "stage,sort_order,id",
                (project_id,),
            )
        ]
        links = [
            dict(r)
            for r in db.execute(
                "SELECT l.*,t.status FROM task_node_link l JOIN task t ON t.id=l.task_id "
                "WHERE l.project_id=? AND l.active=1 AND t.category='research'",
                (project_id,),
            )
        ]
        for node in nodes:
            node["source_status"] = (
                _inspect(
                    workspace["root"],
                    node["source_path"],
                    node["source_section"],
                    node["source_sha256"],
                )
                if workspace
                else "missing_or_invalid"
            )
            descendants = {node["id"]}
            while True:
                expanded = descendants | {n["id"] for n in nodes if n["parent_id"] in descendants}
                if expanded == descendants:
                    break
                descendants = expanded
            tasks = {
                link["task_id"]: link["status"] for link in links if link["node_id"] in descendants
            }
            node["task_count"] = len(tasks)
            node["done_count"] = sum(s == "done" for s in tasks.values())
            node["complete"] = bool(tasks) and node["done_count"] == len(tasks)
        unlinked = [
            dict(r)
            for r in db.execute(
                "SELECT id,title,category FROM task WHERE project_id=? AND (category IS "
                "NULL OR (category='research' AND NOT EXISTS "
                "(SELECT 1 FROM task_node_link WHERE task_id=task.id "
                "AND role='primary' AND active=1))) ORDER BY id",
                (project_id,),
            )
        ]
        return {"nodes": nodes, "links": links, "pending": unlinked}
    finally:
        db.close()


def preview_research_nodes(path, project_id):
    db = connect(path)
    try:
        workspace = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        if not workspace:
            raise Missing("workspace not configured")
        source = "docs/architecture/system_design.md"
        raw = safe_path(workspace["root"], source).read_bytes()
        section = "5. 一条实施主线与三种编号"
        if section not in raw.decode("utf-8-sig"):
            raise ValueError("source section missing")
        digest = hashlib.sha256(raw).hexdigest()
        tasks = [
            dict(r)
            for r in db.execute(
                "SELECT id,title,category,stages,primary_stage,revision FROM task "
                "WHERE project_id=? ORDER BY id",
                (project_id,),
            )
        ]
        existing = {
            row["id"]: dict(row)
            for row in db.execute("SELECT * FROM research_node WHERE project_id=?", (project_id,))
        }
        nodes = [
            {
                "id": f"{project_id}:stage:{stage}",
                "stage": stage,
                "parent_id": None,
                "sort_order": i,
                "source_path": source,
                "source_section": section,
                "source_sha256": digest,
            }
            for i, stage in enumerate("ABCDEF")
        ]
        warnings = []
        task_sections = {}
        for source_path in (
            "docs/s2_implementation_plan.md",
            "docs/feature_engineering_plan_v0.1.md",
        ):
            try:
                source_bytes = safe_path(workspace["root"], source_path).read_bytes()
                source_text = source_bytes.decode("utf-8-sig")
            except (OSError, ValueError, UnicodeError):
                warnings.append({"source_path": source_path, "reason": "missing_or_invalid"})
                continue
            source_hash = hashlib.sha256(source_bytes).hexdigest()
            headings = re.findall(r"^#{2,3}\s+(.+?)\s*#*\s*$", source_text, re.MULTILINE)
            for heading in headings:
                match = re.match(r"(?:\d+\.\s*)?(S[23]-\d{2})[\uFF1A:]", heading)
                if not match:
                    continue
                task_id = match.group(1)
                if headings.count(heading) != 1 or task_id in task_sections:
                    warnings.append({"task_id": task_id, "reason": "ambiguous_section"})
                    task_sections[task_id] = None
                    continue
                task_sections[task_id] = {
                    "id": f"{project_id}:task-branch:{task_id}",
                    "stage": "C",
                    "parent_id": f"{project_id}:stage:C",
                    "sort_order": len(task_sections),
                    "source_path": source_path,
                    "source_section": heading,
                    "source_sha256": source_hash,
                }
        candidates = []
        for task in tasks:
            task["stages"] = json.loads(task["stages"])
            branch = task_sections.get(task["id"])
            if task["category"] == "research" and "C" in task["stages"] and branch:
                nodes.append(branch)
                candidates.append(
                    {
                        "task_id": task["id"],
                        "node_id": branch["id"],
                        "role": "primary",
                        "task_revision": task["revision"],
                        "basis": "Task ID and C stage match the plan section; review required",
                    }
                )
        for node in nodes:
            old = existing.get(node["id"])
            node["expected_revision"] = old["revision"] if old else 0
            node["registration"] = "existing" if old else "pending"
        return {
            "nodes": nodes,
            "tasks": tasks,
            "link_candidates": candidates,
            "warnings": warnings,
            "note": "Review candidates manually; no changes are applied automatically",
        }
    finally:
        db.close()


def apply_research_initialization(path, project_id, nodes, links, reason, *, request_id, actor):
    """Atomically apply reviewed initialization candidates against their observed versions."""
    reason = _text(reason, "reason")
    if len({n["id"] for n in nodes}) != len(nodes) or len({link["id"] for link in links}) != len(
        links
    ):
        raise ValueError("duplicate initialization IDs")

    def run(db, actor):
        workspace = db.execute(
            "SELECT root FROM index_workspace WHERE project_id=?", (project_id,)
        ).fetchone()
        if not workspace:
            raise Missing("workspace not configured")
        saved_nodes = []
        for node in nodes:
            node_id = _text(node.get("id"), "node ID")
            values = {
                k: node.get(k)
                for k in (
                    "stage",
                    "parent_id",
                    "sort_order",
                    "source_path",
                    "source_section",
                    "source_sha256",
                )
            }
            values["active"] = 1
            if (
                values["stage"] not in ("A", "B", "C", "D", "E", "F")
                or not isinstance(values["sort_order"], int)
                or not re.fullmatch(r"[0-9a-f]{64}", values["source_sha256"] or "")
            ):
                raise ValueError("invalid node")
            if (
                _inspect(
                    workspace["root"],
                    values["source_path"],
                    values["source_section"],
                    values["source_sha256"],
                )
                != "valid"
            ):
                raise Conflict("node source requires review")
            old = db.execute("SELECT * FROM research_node WHERE id=?", (node_id,)).fetchone()
            if old and (
                old["project_id"] != project_id or any(old[k] != v for k, v in values.items())
            ):
                raise Conflict("initialization cannot modify existing node")
            parent = values["parent_id"]
            if parent:
                parent_row = db.execute(
                    "SELECT * FROM research_node WHERE id=?", (parent,)
                ).fetchone()
                if (
                    not parent_row
                    or parent_row["project_id"] != project_id
                    or not parent_row["active"]
                    or parent_row["stage"] != values["stage"]
                    or parent == node_id
                ):
                    raise ValueError("invalid parent")
            saved_nodes.append(
                _save(
                    db,
                    "research_node",
                    project_id,
                    node_id,
                    values,
                    node["expected_revision"],
                    reason,
                    actor,
                )
            )
        saved_links = []
        for link in links:
            link_id = _text(link.get("id"), "link ID")
            values = {k: link.get(k) for k in ("task_id", "node_id", "role")}
            values["active"] = 1
            task = db.execute("SELECT * FROM task WHERE id=?", (values["task_id"],)).fetchone()
            node = db.execute(
                "SELECT * FROM research_node WHERE id=?", (values["node_id"],)
            ).fetchone()
            if (
                not task
                or task["project_id"] != project_id
                or not node
                or node["project_id"] != project_id
            ):
                raise ValueError("task and node must belong to project")
            if task["revision"] != link["task_revision"]:
                raise Conflict("task revision conflict")
            if (
                task["category"] != "research"
                or not node["active"]
                or node["stage"] not in json.loads(task["stages"])
                or values["role"] not in ("primary", "reference")
            ):
                raise ValueError("task category or stage incompatible")
            old = db.execute("SELECT * FROM task_node_link WHERE id=?", (link_id,)).fetchone()
            if old and (
                old["project_id"] != project_id or any(old[k] != v for k, v in values.items())
            ):
                raise Conflict("initialization cannot modify existing link")
            if db.execute(
                "SELECT 1 FROM task_node_link WHERE active=1 AND task_id=? AND id<>? AND "
                "((node_id=? AND role=?) OR (role='primary' AND ?='primary'))",
                (values["task_id"], link_id, values["node_id"], values["role"], values["role"]),
            ).fetchone():
                raise Conflict("duplicate link or primary")
            saved_links.append(
                _save(
                    db,
                    "task_node_link",
                    project_id,
                    link_id,
                    values,
                    link["expected_revision"],
                    reason,
                    actor,
                )
            )
        return {"nodes": saved_nodes, "links": saved_links}

    return _write(
        path,
        request_id,
        actor,
        "apply_research_initialization",
        [project_id, nodes, links, reason],
        run,
    )
