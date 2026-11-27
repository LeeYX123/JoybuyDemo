"""商品 public_id 回退：JYP + 10 位随机 → 原 UUID（2026-11-27 回退）。

背景：2026-11-27 阶段 1 把商品编号也改成了 ``JYP`` 前缀；用户拍板商品编号不
采用 JY 格式，恢复原 UUID。订单/商家/用户/售后/支付/退款/物流的类型编号保持
JY 格式不变，本迁移**只回退商品域**。

1. 数据：按 ``spu_public_id_bak_20261127``（阶段 1 备份，列 ``id, public_id``，
   32 位无连字符十六进制）把 ``spu.public_id`` 按主键恢复。
2. 反向映射 ``JYP -> 原值`` 由 ``spu_public_id_bak_20261127 JOIN spu ON id`` 现算，
   再把历史引用换回（形态与回退前一致）：

   * ``spu_alias.old_public_id`` → 32 位无连字符（UUIDField 列形态）
   * ``spu_variant_archive.source_spu_public_id`` → 32 位无连字符
   * ``order_item.spu_public_id`` → 36 位带连字符（``str(uuid.UUID(hex))``，
     字段 ``max_length=36``，下单代码写的是 ``str(spu.public_id)``）
   * ``variant_family.family_key`` / ``product_search_document.family_key``
     内嵌的 ``merged:<spu_public_id>`` → 36 位带连字符（原生成代码是
     ``f"merged:{keep['public_id']}"``，UUID 对象 f-string 即带连字符）

3. 结构：三个列 ``varchar(32)`` → ``char(32)``（UUIDField 在 MySQL 的列型），
   与 0020 及更早的状态一致。

幂等：没有备份表（全新库/测试库）或没有 ``JYP+10`` 形态的值时数据步骤直接跳过，
结构步骤是 ``char(32)`` 原地等价变更。历史 dev 库已 apply 过被删除的
``0021_spu_public_id_jyp_format``（迁移文件已随本次回退删除，``django_migrations``
里那条记录会被 Django 忽略，不影响后续迁移）。
"""

import uuid

from django.db import migrations, models

BATCH_SIZE = 500
BACKUP_TABLE = "spu_public_id_bak_20261127"
#: 精确匹配 13 位的商品编号，避免误伤 ``JYPAY`` 支付编号（长度不同）。
JYP_REGEX = "^JYP[0-9A-Z]{10}$"


def _dashed(hex32: str) -> str:
    compact = hex32.replace("-", "").lower()
    return f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:32]}"


def _table_exists(connection, table: str) -> bool:
    with connection.cursor() as cursor:
        return table in connection.introspection.table_names(cursor)


def _fetch_reverse_map(connection) -> dict[str, str]:
    """``{当前 JYP 值: 原 32 位十六进制}``；无备份表时返回空。"""

    if not _table_exists(connection, BACKUP_TABLE):
        return {}
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT s.`public_id`, b.`public_id` FROM `{BACKUP_TABLE}` b "
            "JOIN `spu` s ON s.`id` = b.`id`"
        )
        rows = cursor.fetchall()
    mapping: dict[str, str] = {}
    for current, old in rows:
        if current is None or old is None:
            continue
        hex32 = str(old).replace("-", "").lower()
        if len(hex32) != 32:
            raise RuntimeError(f"备份值不是 32 位十六进制: id 行 {old!r}")
        mapping[str(current)] = hex32
    return {key: value for key, value in mapping.items() if key.startswith("JYP")}


def _restore_spu_public_id(connection, mapping: dict[str, str]) -> int:
    """``spu.public_id`` 按主键恢复为原 32 位十六进制，分批并逐批校验。"""

    if not mapping:
        return 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT `id`, `public_id` FROM `spu` ORDER BY `id`")
        rows = cursor.fetchall()
    payload = [(mapping[str(current)], pk) for pk, current in rows if str(current) in mapping]
    if len(payload) != len(rows):
        raise RuntimeError(f"spu 有 {len(rows) - len(payload)} 行无法映射回原号，中止")
    updated = 0
    with connection.cursor() as cursor:
        for start in range(0, len(payload), BATCH_SIZE):
            chunk = payload[start : start + BATCH_SIZE]
            cursor.executemany(
                "UPDATE `spu` SET `public_id` = %s WHERE `id` = %s",
                chunk,
            )
            if cursor.rowcount not in (len(chunk), 0):
                raise RuntimeError(f"spu 批次更新行数异常: {cursor.rowcount} != {len(chunk)}")
            updated += len(chunk)
    return updated


def _restore_reference(
    connection,
    *,
    table: str,
    column: str,
    mapping: dict[str, str],
    dashed: bool,
    prefix: str = "",
) -> int:
    """把一列里的 JYP 值换回原号（``dashed`` 决定 36 位带连字符 / 32 位无连字符）。"""

    if not mapping:
        return 0
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT `id`, `{column}` FROM `{table}`")
        rows = cursor.fetchall()
    payload = []
    for pk, value in rows:
        current = str(value)
        if current.startswith(prefix):
            current = current[len(prefix) :]
        if current not in mapping:
            continue
        target = _dashed(mapping[current]) if dashed else mapping[current]
        payload.append((f"{prefix}{target}", pk))
    if not payload:
        return 0
    with connection.cursor() as cursor:
        for start in range(0, len(payload), BATCH_SIZE):
            cursor.executemany(
                f"UPDATE `{table}` SET `{column}` = %s WHERE `id` = %s",
                payload[start : start + BATCH_SIZE],
            )
    return len(payload)


def _verify(connection) -> None:
    """回退后校验：6 个商品号列 0 条 JYP+10 残留、spu 不重号、引用能关联。"""

    specs = (
        ("spu", "public_id"),
        ("spu_alias", "old_public_id"),
        ("spu_variant_archive", "source_spu_public_id"),
        ("order_item", "spu_public_id"),
    )
    with connection.cursor() as cursor:
        for table, column in specs:
            cursor.execute(
                f"SELECT COUNT(*) FROM `{table}` WHERE `{column}` REGEXP %s", [JYP_REGEX]
            )
            residue = cursor.fetchone()[0]
            if residue:
                raise RuntimeError(f"回退残留 {table}.{column}: {residue} 行仍是 JYP 形态")
        for table in ("variant_family", "product_search_document"):
            cursor.execute(
                f"SELECT COUNT(*) FROM `{table}` WHERE `family_key` REGEXP %s",
                ["^merged:JYP[0-9A-Z]{10}$"],
            )
            residue = cursor.fetchone()[0]
            if residue:
                raise RuntimeError(f"回退残留 {table}.family_key: {residue} 行仍是 JYP 形态")

        cursor.execute("SELECT COUNT(*), COUNT(DISTINCT `public_id`) FROM `spu`")
        total, distinct = cursor.fetchone()
        if total != distinct:
            raise RuntimeError(f"spu.public_id 重号: total={total} distinct={distinct}")

        cursor.execute(
            "SELECT COUNT(*) FROM `order_item` oi "
            "LEFT JOIN `spu` s ON s.`public_id` = REPLACE(oi.`spu_public_id`, '-', '') "
            "WHERE s.`id` IS NULL"
        )
        broken = cursor.fetchone()[0]
        if broken:
            raise RuntimeError(f"order_item.spu_public_id 无法关联 spu: {broken} 行")


def restore(apps, schema_editor):
    connection = schema_editor.connection
    mapping = _fetch_reverse_map(connection)
    if not mapping:
        return  # 全新库：从未改造过，保持原 UUID
    restored = _restore_spu_public_id(connection, mapping)
    _restore_reference(
        connection, table="spu_alias", column="old_public_id", mapping=mapping, dashed=False
    )
    _restore_reference(
        connection,
        table="spu_variant_archive",
        column="source_spu_public_id",
        mapping=mapping,
        dashed=False,
    )
    _restore_reference(
        connection, table="order_item", column="spu_public_id", mapping=mapping, dashed=True
    )
    for table in ("variant_family", "product_search_document"):
        _restore_reference(
            connection,
            table=table,
            column="family_key",
            mapping=mapping,
            dashed=True,
            prefix="merged:",
        )
    if restored:
        _verify(connection)


#: 需要把 ``varchar(32)`` 改回 ``char(32)``（UUIDField 在 MySQL 的列型）的列。
#: 长度 32 → 32，直接 ``MODIFY`` 不涉及截断，无需临时列。
UUID_COLUMNS = (
    ("spu", "public_id"),
    ("spu_alias", "old_public_id"),
    ("spu_variant_archive", "source_spu_public_id"),
)


def restore_column_types(apps, schema_editor):
    """MySQL：被阶段 1 改成 ``varchar(32)`` 的 UUID 列恢复成 ``char(32)``。

    迁移状态在 0020 就已是 ``UUIDField``（阶段 1 的 0021 已删除），所以
    ``AlterField`` 不会产生 DDL；这里用显式 ``ALTER TABLE ... MODIFY`` 把列型
    也恢复成原样。非 MySQL（sqlite / 测试）类型亲和性相同，直接跳过。
    """

    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return
    with connection.cursor() as cursor:
        for table, column in UUID_COLUMNS:
            cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", [column])
            row = cursor.fetchone()
            if row is None:
                continue
            column_type = str(row[1]).strip().lower()
            if column_type == "char(32)":
                continue
            if column_type not in {"varchar(32)", "char(32)"}:
                raise RuntimeError(f"{table}.{column} 列型异常: {column_type}")
            cursor.execute(f"ALTER TABLE `{table}` MODIFY COLUMN `{column}` char(32) NOT NULL")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0020_variant_family"),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(restore, reverse_code=migrations.RunPython.noop),
        # DDL 在 MySQL 上会隐式提交，单独一步并关闭事务包裹。
        migrations.RunPython(
            restore_column_types,
            reverse_code=migrations.RunPython.noop,
            atomic=False,
        ),
        migrations.AlterField(
            model_name="spu",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="spualias",
            name="old_public_id",
            field=models.UUIDField(unique=True),
        ),
        migrations.AlterField(
            model_name="spuvariantarchive",
            name="source_spu_public_id",
            field=models.UUIDField(),
        ),
    ]
