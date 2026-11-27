"""迁移期回填辅助（2026-11-27「全站编号改造」阶段 1 专用）。

只被 5 个 public_id 数据迁移引用：

* :func:`backfill_public_id`：按 pk 升序整表换新号（先写临时列 ``public_id_new``），
  分批 500 行 ``executemany`` 更新，每批在内存里校验不重号，最后返回
  ``{旧号: 新号}`` 映射供同一迁移重写历史引用。
* :func:`rewrite_thread_keys` / :func:`update_reference_column`：用映射批量替换
  历史引用（订单商品快照、商品别名、变体档案、族键、Crisp 线程键）。
* :func:`verify_public_ids`：``COUNT(*) = COUNT(DISTINCT public_id)``、全行正则匹配、
  无 32 位十六进制残留。

为什么不直接 ``AlterField``：dev 库是 MySQL，历史事故（merchants/0009）证明对
char(32) 的编号列做原地类型变更/缩短有截断风险；统一按「加临时列 → 回填 →
删旧列 → rename → 加唯一约束」走，可回滚、可分批。
"""

from __future__ import annotations

import re

from common.ids import ID_PREFIX, new_public_id

BATCH_SIZE = 500
TEMP_FIELD = "public_id_new"


def normalize_old_id(value) -> str | None:
    """统一旧号形态：MySQL 的 UUIDField 列存 32 位无连字符，Python 侧是连字符形式。

    历史引用里两种形态都存在（``OrderItem.spu_public_id`` 存的是
    ``str(uuid)`` 连字符形式，而 ``SpuAlias.old_public_id`` 经驱动读出是 32 位
    十六进制），所以查映射前先归一。
    """

    if value is None:
        return None
    text = str(value)
    compact = text.replace("-", "")
    if len(compact) == 32 and all(char in "0123456789abcdefABCDEF" for char in compact):
        compact = compact.lower()
        return f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:32]}"
    return text


def table_exists(connection, table: str) -> bool:
    with connection.cursor() as cursor:
        return table in connection.introspection.table_names(cursor)


def backfill_public_id(
    apps,
    schema_editor,
    *,
    app_label: str,
    model_name: str,
    kind: str,
    temp_field: str = TEMP_FIELD,
) -> dict[str, str]:
    """按 pk 升序为整表生成新号写进临时列，返回 ``{旧号: 新号}``。"""

    model = apps.get_model(app_label, model_name)
    table = model._meta.db_table
    connection = schema_editor.connection
    rows = list(model.objects.order_by("pk").values_list("pk", "public_id"))
    mapping: dict[str, str] = {}
    seen: set[str] = set()

    with connection.cursor() as cursor:
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            payload = []
            for pk, old in batch:
                new = new_public_id(kind)
                # 每批（及跨批）在内存里先挡一次重号；DB unique 仍是最终防线。
                while new in seen:  # pragma: no cover - 36^6/36^10 空间，实际不会命中
                    new = new_public_id(kind)
                seen.add(new)
                mapping[str(old)] = new
                payload.append((new, pk))
            cursor.executemany(
                f"UPDATE `{table}` SET `{temp_field}` = %s WHERE `id` = %s",
                payload,
            )

    return mapping


def update_reference_column(
    schema_editor,
    *,
    table: str,
    column: str,
    mapping: dict[str, str],
) -> int:
    """把一列里出现的旧号替换成新号（只更新命中映射的行），返回更新行数。"""

    connection = schema_editor.connection
    updated = 0
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT `id`, `{column}` FROM `{table}`")
        rows = cursor.fetchall()
    payload = [
        (mapping[normalize_old_id(value)], pk)
        for pk, value in rows
        if normalize_old_id(value) in mapping
    ]
    if not payload:
        return 0
    with connection.cursor() as cursor:
        for start in range(0, len(payload), BATCH_SIZE):
            chunk = payload[start : start + BATCH_SIZE]
            cursor.executemany(f"UPDATE `{table}` SET `{column}` = %s WHERE `id` = %s", chunk)
            updated += len(chunk)
    return updated


def rewrite_thread_keys(
    schema_editor,
    *,
    mapping: dict[str, str],
    mode: str,
    tables: tuple[str, ...] = ("crisp_mirror_session", "crisp_mirror_log"),
) -> int:
    """重写 Crisp 线程键里的一段 id。

    ``mode="buyer"``：``bp:<buyer>`` / ``bm:<buyer>:<merchant>`` 的买家段；
    ``mode="merchant"``：``merchant:<merchant>`` / ``bm:<buyer>:<merchant>`` 的商家段。
    映射是双射，唯一键不受影响。
    """

    connection = schema_editor.connection
    existing = set(connection.introspection.table_names())
    updated = 0
    for table in tables:
        if table not in existing:
            continue
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT `id`, `thread_key` FROM `{table}`")
            rows = cursor.fetchall()
        payload = []
        for pk, key in rows:
            new_key = _rewrite_one(key, mapping, mode)
            if new_key != key:
                payload.append((new_key, pk))
        if not payload:
            continue
        with connection.cursor() as cursor:
            cursor.executemany(f"UPDATE `{table}` SET `thread_key` = %s WHERE `id` = %s", payload)
        updated += len(payload)
    return updated


def _rewrite_one(key: str, mapping: dict[str, str], mode: str) -> str:
    if mode == "buyer":
        if key.startswith("bp:"):
            return "bp:" + mapping.get(normalize_old_id(key[3:]), key[3:])
        if key.startswith("bm:"):
            _, buyer, merchant = key.split(":", 2)
            return f"bm:{mapping.get(normalize_old_id(buyer), buyer)}:{merchant}"
        return key
    if key.startswith("merchant:"):
        return "merchant:" + mapping.get(normalize_old_id(key[9:]), key[9:])
    if key.startswith("bm:"):
        _, buyer, merchant = key.split(":", 2)
        return f"bm:{buyer}:{mapping.get(normalize_old_id(merchant), merchant)}"
    return key


def rewrite_family_key(schema_editor, *, table: str, mapping: dict[str, str]) -> int:
    """``merged:<spu_public_id>`` 内嵌号替换（VariantFamily / ProductSearchDocument）。"""

    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT `id`, `family_key` FROM `{table}` WHERE `family_key` LIKE 'merged:%'"
        )
        rows = cursor.fetchall()
    payload = []
    for pk, key in rows:
        embedded = key[len("merged:") :]
        normalized = normalize_old_id(embedded)
        if normalized in mapping:
            payload.append((f"merged:{mapping[normalized]}", pk))
    if not payload:
        return 0
    with connection.cursor() as cursor:
        for start in range(0, len(payload), BATCH_SIZE):
            chunk = payload[start : start + BATCH_SIZE]
            cursor.executemany(f"UPDATE `{table}` SET `family_key` = %s WHERE `id` = %s", chunk)
    return len(payload)


def verify_public_ids(
    schema_editor,
    *,
    table: str,
    field: str = "public_id",
    kind: str,
    sample: int = 2,
) -> dict[str, object]:
    """校验：无空值、无重号、全行匹配新格式、无 32 位十六进制残留。"""

    prefix = ID_PREFIX[kind]
    dated = kind in {"order", "after_sale"}
    pattern = re.compile(
        rf"^{prefix}\d{{8}}[0-9A-Z]{{6}}$" if dated else rf"^{prefix}[0-9A-Z]{{10}}$"
    )
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT `{field}`), "
            f"SUM(`{field}` IS NULL OR `{field}` = '') FROM `{table}`"
        )
        total, distinct, blanks = cursor.fetchone()
        cursor.execute(f"SELECT `{field}` FROM `{table}` ORDER BY `id`")
        values = [row[0] for row in cursor.fetchall()]

    offending = [value for value in values if not pattern.match(str(value))]
    hex_residue = [value for value in values if re.fullmatch(r"[0-9a-fA-F]{32}", str(value))]
    result = {
        "table": table,
        "total": total,
        "distinct": distinct,
        "blanks": int(blanks or 0),
        "invalid": len(offending),
        "hex_residue": len(hex_residue),
        "first": values[:sample],
        "last": values[-sample:] if values else [],
    }
    if total != distinct or result["blanks"] or offending or hex_residue:
        raise RuntimeError(f"public_id 校验失败 {table}: {result}")
    return result
