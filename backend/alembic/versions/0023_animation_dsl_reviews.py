"""Immutable DSL review/candidate ledger and explicit policy admission (ADR-0010)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0023_animation_dsl_reviews"
down_revision = "0022_animation_attempts"
branch_labels = None
depends_on = None


def _target():
    return [
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("learning_unit_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("scene_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("scene_version", sa.Integer(), nullable=False),
    ]


def _time():
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def upgrade() -> None:
    op.execute("""CREATE FUNCTION edumind_dsl_positions(v jsonb) RETURNS boolean
        LANGUAGE SQL IMMUTABLE AS $$ SELECT jsonb_typeof(v)='array' AND
        jsonb_array_length(v)<=16 AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(v) AS x WHERE jsonb_typeof(x)!='object'
            OR NOT (x ?& ARRAY['area','severity','action_index'])
            OR (x - ARRAY['area','severity','action_index'])!='{}'::jsonb
            OR jsonb_typeof(x->'area')!='string'
            OR x->>'area' NOT IN ('reference','fact','complexity','caption','difficulty','safety')
            OR jsonb_typeof(x->'severity')!='string'
            OR x->>'severity' NOT IN ('minor','major','severe')
            OR NOT ((x->'action_index')='null'::jsonb OR
                (jsonb_typeof(x->'action_index')='number' AND
                 x->>'action_index' ~ '^[0-9]{1,3}$' AND
                 (x->>'action_index')::numeric<=119))) $$""")
    op.create_table(
        "animation_dsl_policies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("manifest", pg.JSONB(), nullable=False),
        sa.Column(
            "admitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("id ~ '^[0-9a-f]{64}$'", name="ck_dsl_policy_hash"),
        sa.CheckConstraint(
            "jsonb_typeof(manifest) = 'object' AND octet_length(manifest::text) <= 8192",
            name="ck_dsl_policy_manifest",
        ),
    )
    op.create_table(
        "animation_dsl_policy_revocations",
        sa.Column(
            "policy_id", sa.String(64), sa.ForeignKey("animation_dsl_policies.id"), primary_key=True
        ),
        sa.Column("reason_code", sa.String(32), nullable=False),
        _time(),
        sa.CheckConstraint(
            "reason_code IN ('SAFETY_WITHDRAWN','VERSION_RETIRED')",
            name="ck_dsl_policy_revoke_reason",
        ),
    )
    op.create_table(
        "animation_dsl_reviews",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        *_target(),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("binding_sha256", sa.String(64), nullable=False),
        sa.Column("review_sha256", sa.String(64), nullable=False),
        sa.Column("evidence", pg.JSONB(), nullable=False),
        sa.Column("issue_positions", pg.JSONB(), nullable=False),
        sa.Column("error_code", sa.String(32)),
        _time(),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["learning_unit_id", "scene_id", "scene_version"],
            ["learning_scenes.learning_unit_id", "learning_scenes.id", "learning_scenes.version"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "user_id",
            "learning_unit_id",
            "scene_id",
            "scene_version",
            "id",
            "verdict",
            "binding_sha256",
            name="uq_dsl_review_bound_pass",
        ),
        sa.CheckConstraint(
            "verdict IN ('pass','revise','reject','unavailable')", name="ck_dsl_review_verdict"
        ),
        sa.CheckConstraint(
            "binding_sha256 ~ '^[0-9a-f]{64}$' AND review_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_dsl_review_hashes",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'object' AND octet_length(evidence::text)<=8192",
            name="ck_dsl_review_evidence",
        ),
        sa.CheckConstraint(
            "edumind_dsl_positions(issue_positions) AND "
            "jsonb_array_length(issue_positions)<=16 AND "
            "(verdict != 'pass' OR issue_positions='[]'::jsonb)",
            name="ck_dsl_review_positions",
        ),
        sa.CheckConstraint(
            "(verdict='unavailable' AND error_code='DSL_REVIEW_UNAVAILABLE') OR "
            "(verdict!='unavailable' AND error_code IS NULL)",
            name="ck_dsl_review_error",
        ),
    )
    op.create_table(
        "animation_dsl_candidates",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        *_target(),
        sa.Column("review_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("binding_sha256", sa.String(64), nullable=False),
        sa.Column(
            "policy_id", sa.String(64), sa.ForeignKey("animation_dsl_policies.id"), nullable=False
        ),
        sa.Column("canonical_dsl", sa.Text(), nullable=False),
        sa.Column("trace_json", sa.Text(), nullable=False),
        sa.Column("dsl_sha256", sa.String(64), nullable=False),
        sa.Column("trace_sha256", sa.String(64), nullable=False),
        _time(),
        sa.UniqueConstraint("user_id", "id", name="uq_dsl_candidate_owner_id"),
        sa.UniqueConstraint(
            "user_id",
            "learning_unit_id",
            "scene_id",
            "scene_version",
            "id",
            name="uq_dsl_candidate_owner_target",
        ),
        sa.ForeignKeyConstraint(
            [
                "user_id",
                "learning_unit_id",
                "scene_id",
                "scene_version",
                "review_id",
                "verdict",
                "binding_sha256",
            ],
            [
                "animation_dsl_reviews.user_id",
                "animation_dsl_reviews.learning_unit_id",
                "animation_dsl_reviews.scene_id",
                "animation_dsl_reviews.scene_version",
                "animation_dsl_reviews.id",
                "animation_dsl_reviews.verdict",
                "animation_dsl_reviews.binding_sha256",
            ],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("verdict='pass'", name="ck_dsl_candidate_pass"),
        sa.CheckConstraint(
            "octet_length(canonical_dsl)<=65536 AND octet_length(trace_json)<=1048576",
            name="ck_dsl_candidate_limits",
        ),
        sa.CheckConstraint(
            "dsl_sha256=encode(sha256(convert_to(canonical_dsl,'UTF8')),'hex') AND "
            "trace_sha256=encode(sha256(convert_to(trace_json,'UTF8')),'hex')",
            name="ck_dsl_candidate_content_hash",
        ),
    )
    op.execute("""CREATE FUNCTION edumind_dsl_candidate_bound() RETURNS trigger
        LANGUAGE plpgsql AS $$ DECLARE e jsonb; p jsonb;
        BEGIN SELECT evidence INTO e FROM animation_dsl_reviews WHERE id=NEW.review_id;
        SELECT manifest INTO p FROM animation_dsl_policies WHERE id=NEW.policy_id;
        IF e IS NULL OR p IS NULL OR e->>'dsl' IS DISTINCT FROM NEW.dsl_sha256
            OR e->>'trace' IS DISTINCT FROM NEW.trace_sha256
            OR e->>'schema' IS DISTINCT FROM p->>'schema'
            OR e->>'validator' IS DISTINCT FROM p->>'validator'
            OR e->>'semantic_policy' IS DISTINCT FROM p->>'semantic_policy'
            OR e->>'compiler' IS DISTINCT FROM p->>'compiler'
            OR e->>'compiler_policy' IS DISTINCT FROM p->>'compiler_policy'
            OR e->>'reviewer' IS DISTINCT FROM p->>'reviewer'
            OR e->>'review_prompt' IS DISTINCT FROM p->>'review_prompt'
            OR e->>'review_schema' IS DISTINCT FROM p->>'review_schema'
        THEN RAISE EXCEPTION 'DSL_BINDING_MISMATCH'; END IF; RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER dsl_insert_bound BEFORE INSERT ON animation_dsl_candidates "
        "FOR EACH ROW EXECUTE FUNCTION edumind_dsl_candidate_bound()"
    )
    op.create_table(
        "animation_dsl_candidate_revocations",
        sa.Column("candidate_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        _time(),
        sa.ForeignKeyConstraint(
            ["user_id", "candidate_id"],
            ["animation_dsl_candidates.user_id", "animation_dsl_candidates.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "reason_code IN ('SAFETY_WITHDRAWN','VERSION_RETIRED')",
            name="ck_dsl_candidate_revoke_reason",
        ),
    )
    op.execute("""CREATE FUNCTION edumind_dsl_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'DSL_IMMUTABLE'; END $$""")
    for table in (
        "policies",
        "policy_revocations",
        "reviews",
        "candidates",
        "candidate_revocations",
    ):
        op.execute(
            f"CREATE TRIGGER dsl_no_update BEFORE UPDATE ON animation_dsl_{table} "
            "FOR EACH ROW EXECUTE FUNCTION edumind_dsl_immutable()"
        )
    # Revocations cannot be removed to revive data. Owner/target cascading deletion remains legal.
    op.execute("""CREATE FUNCTION edumind_dsl_no_revival() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF pg_trigger_depth() > 1 THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'DSL_REVOCATION_IMMUTABLE'; END $$""")
    for table in ("policy_revocations", "candidate_revocations"):
        op.execute(
            f"CREATE TRIGGER dsl_no_delete BEFORE DELETE ON animation_dsl_{table} "
            "FOR EACH ROW EXECUTE FUNCTION edumind_dsl_no_revival()"
        )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM animation_dsl_reviews)")):
        raise RuntimeError("DSL_CANDIDATES_REQUIRE_DRAIN")
    for table in (
        "candidate_revocations",
        "candidates",
        "reviews",
        "policy_revocations",
        "policies",
    ):
        op.drop_table(f"animation_dsl_{table}")
    op.execute("DROP FUNCTION edumind_dsl_candidate_bound()")
    op.execute("DROP FUNCTION edumind_dsl_positions(jsonb)")
    op.execute("DROP FUNCTION edumind_dsl_no_revival()")
    op.execute("DROP FUNCTION edumind_dsl_immutable()")
