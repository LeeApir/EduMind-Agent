"""Immutable shared plans and nullable legacy-compatible candidate bindings."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0026_learning_plans"
down_revision = "0025_animation_dsl_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_operation_target", "learning_operations", ["user_id", "learning_unit_id", "id"]
    )
    op.create_table(
        "learning_plan_versions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("learning_unit_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("origin_operation_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("plan_json", pg.JSONB(), nullable=False),
        *[
            sa.Column(k, pg.JSONB(), nullable=False)
            for k in ("input_snapshot", "references_snapshot", "policy_snapshot")
        ],
        *[
            sa.Column(k, sa.String(64), nullable=False)
            for k in ("plan_digest", "input_digest", "references_digest", "policy_digest")
        ],
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "learning_unit_id", "version"),
        sa.UniqueConstraint("user_id", "learning_unit_id", "id"),
        sa.UniqueConstraint("learning_unit_id", "id"),
        sa.CheckConstraint("version >= 1"),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "origin_operation_id"],
            [
                "learning_operations.user_id",
                "learning_operations.learning_unit_id",
                "learning_operations.id",
            ],
            ondelete="CASCADE",
        ),
    )
    for table in ("learning_scenes", "generated_resources"):
        op.add_column(table, sa.Column("plan_id", pg.UUID(as_uuid=True)))
        op.add_column(table, sa.Column("dependency_digest", sa.String(64)))
    op.add_column("generated_resources", sa.Column("content_digest", sa.String(64)))
    op.create_unique_constraint(
        "uq_scene_plan", "learning_scenes", ["learning_unit_id", "id", "plan_id"]
    )
    op.create_foreign_key(
        "fk_scene_plan",
        "learning_scenes",
        "learning_plan_versions",
        ["learning_unit_id", "plan_id"],
        ["learning_unit_id", "id"],
    )
    op.create_foreign_key(
        "fk_resource_plan",
        "generated_resources",
        "learning_plan_versions",
        ["user_id", "learning_unit_id", "plan_id"],
        ["user_id", "learning_unit_id", "id"],
    )
    op.create_foreign_key(
        "fk_resource_scene_plan",
        "generated_resources",
        "learning_scenes",
        ["learning_unit_id", "scene_id", "plan_id"],
        ["learning_unit_id", "id", "plan_id"],
    )
    op.create_check_constraint(
        "ck_scene_plan_fields",
        "learning_scenes",
        "(plan_id IS NULL AND dependency_digest IS NULL) OR "
        "(plan_id IS NOT NULL AND dependency_digest IS NOT NULL AND dependency_digest ~ '^[0-9a-f]{64}$' "
        "AND scene_key IN ('explanation','code','exercise'))",
    )
    op.create_check_constraint(
        "ck_resource_plan_fields",
        "generated_resources",
        "(plan_id IS NULL AND dependency_digest IS NULL AND content_digest IS NULL) OR "
        "(plan_id IS NOT NULL AND dependency_digest IS NOT NULL AND dependency_digest ~ '^[0-9a-f]{64}$' "
        "AND content_digest IS NOT NULL AND content_digest ~ '^[0-9a-f]{64}$')",
    )
    op.execute("""CREATE FUNCTION immutable_learning_plan() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'immutable planned snapshot' USING ERRCODE='23514'; END; $$""")
    op.execute(
        "CREATE TRIGGER immutable_plan BEFORE UPDATE ON learning_plan_versions "
        "FOR EACH ROW EXECUTE FUNCTION immutable_learning_plan()"
    )
    for table in ("learning_scenes", "generated_resources"):
        columns = ["plan_id", "dependency_digest", "learning_unit_id", "id", "version"]
        columns += (
            ["content", "content_digest", "scene_id", "user_id", "resource_type", "metadata"]
            if table == "generated_resources"
            else ["input_snapshot", "scene_key", "scene_type", "scene_order"]
        )
        changed = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in columns)
        op.execute(f"""CREATE FUNCTION protect_{table}_plan() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF (OLD.plan_id IS NOT NULL AND ({changed})) OR
             (OLD.plan_id IS NULL AND NEW.plan_id IS NOT NULL) THEN
            RAISE EXCEPTION 'immutable planned candidate' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END; $$""")
        op.execute(
            f"CREATE TRIGGER protect_plan BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION protect_{table}_plan()"
        )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM learning_plan_versions) THEN
        RAISE EXCEPTION 'planned data prevents downgrade'; END IF; END $$""")
    for table in ("learning_scenes", "generated_resources"):
        op.execute(f"DROP TRIGGER protect_plan ON {table}")
        op.execute(f"DROP FUNCTION protect_{table}_plan()")
    op.execute("DROP TRIGGER immutable_plan ON learning_plan_versions")
    op.execute("DROP FUNCTION immutable_learning_plan()")
    for name in ("fk_resource_scene_plan", "fk_resource_plan", "ck_resource_plan_fields"):
        op.drop_constraint(name, "generated_resources")
    op.drop_constraint("fk_scene_plan", "learning_scenes")
    op.drop_constraint("ck_scene_plan_fields", "learning_scenes")
    op.drop_constraint("uq_scene_plan", "learning_scenes")
    for table in ("learning_scenes", "generated_resources"):
        op.drop_column(table, "plan_id")
        op.drop_column(table, "dependency_digest")
    op.drop_column("generated_resources", "content_digest")
    op.drop_table("learning_plan_versions")
    op.drop_constraint("uq_operation_target", "learning_operations")
