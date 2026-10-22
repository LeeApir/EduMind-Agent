"""Add owner-private immutable course snapshots without rewriting legacy records."""

from alembic import op

revision = "0034_free_course_snapshots"
down_revision = "0033_learning_shared_budget"
branch_labels = None
depends_on = None

# Fixed DDL, independent of future ORM revisions.
TABLE_DDL = [
    """CREATE TABLE free_courses (
	user_id UUID NOT NULL,
	original_goal TEXT NOT NULL,
	teaching_language VARCHAR(16) DEFAULT 'zh-CN' NOT NULL,
	code_language VARCHAR(16),
	head_version_id UUID,
	course_kind VARCHAR(24) DEFAULT 'ai_draft' NOT NULL,
	endorsement VARCHAR(24) DEFAULT 'unendorsed' NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_free_course_owner UNIQUE (user_id, id),
	CONSTRAINT ck_free_course_goal CHECK (length(btrim(original_goal)) BETWEEN 1 AND 4000),
        CONSTRAINT ck_free_course_language CHECK (teaching_language = 'zh-CN' AND
    (code_language IS NULL OR code_language = 'C')),
	CONSTRAINT ck_free_course_draft CHECK (course_kind = 'ai_draft' AND endorsement = 'unendorsed'),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_free_course_owner_created ON free_courses (user_id, created_at, id)""",
    """CREATE TABLE free_course_requests (
	digest VARCHAR(64) NOT NULL,
	parent_request_id UUID,
	kind VARCHAR(24) NOT NULL,
	request_text TEXT NOT NULL,
	profile_id UUID,
	profile_version INTEGER,
	evidence_snapshot JSONB NOT NULL,
	nonsecret_config_snapshot JSONB NOT NULL,
	course_id UUID NOT NULL,
	version INTEGER NOT NULL,
	schema_version VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_fc_request_identity UNIQUE (user_id, course_id, id),
	CONSTRAINT uq_fc_request_version UNIQUE (user_id, course_id, version),
        CONSTRAINT fk_fc_request_course FOREIGN KEY(user_id, course_id) REFERENCES
    free_courses (user_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT ck_fc_request_positive CHECK (version >= 1),
	CONSTRAINT ck_fc_request_digest CHECK (digest ~ '^[0-9a-f]{64}$'),
        CONSTRAINT fk_fc_request_parent FOREIGN KEY(user_id, course_id, parent_request_id)
    REFERENCES free_course_requests (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_fc_request_profile FOREIGN KEY(user_id, profile_id, profile_version)
    REFERENCES student_profiles (user_id, id, version) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT ck_fc_request_profile_pair CHECK ((profile_id IS NULL) = (profile_version IS NULL)),
        CONSTRAINT ck_fc_request_kind CHECK ((kind = 'original' AND version = 1 AND
    parent_request_id IS NULL) OR (kind = 'adjustment' AND version > 1 AND parent_request_id
    IS NOT NULL))
)""",
    """CREATE TABLE free_course_scenes (
	course_id UUID NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_fc_scene_identity UNIQUE (user_id, course_id, id),
        CONSTRAINT fk_fc_scene_course FOREIGN KEY(user_id, course_id) REFERENCES free_courses
    (user_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE free_course_plans (
	digest VARCHAR(64) NOT NULL,
	request_id UUID NOT NULL,
	plan_json JSONB NOT NULL,
	course_id UUID NOT NULL,
	version INTEGER NOT NULL,
	schema_version VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_fc_plan_identity UNIQUE (user_id, course_id, id),
	CONSTRAINT uq_fc_plan_version UNIQUE (user_id, course_id, version),
        CONSTRAINT fk_fc_plan_course FOREIGN KEY(user_id, course_id) REFERENCES free_courses
    (user_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT ck_fc_plan_positive CHECK (version >= 1),
	CONSTRAINT ck_fc_plan_digest CHECK (digest ~ '^[0-9a-f]{64}$'),
        CONSTRAINT fk_fc_plan_request FOREIGN KEY(user_id, course_id, request_id) REFERENCES
    free_course_requests (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE free_course_scene_versions (
	scene_id UUID NOT NULL,
	plan_id UUID NOT NULL,
	content_json JSONB NOT NULL,
	actions_json JSONB NOT NULL,
	dependency_bindings JSONB NOT NULL,
	content_digest VARCHAR(64) NOT NULL,
	course_id UUID NOT NULL,
	version INTEGER NOT NULL,
	schema_version VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_fc_scene_version_identity UNIQUE (user_id, course_id, id),
	CONSTRAINT uq_fc_scene_version_number UNIQUE (user_id, course_id, scene_id, version),
	CONSTRAINT ck_fc_scene_version_positive CHECK (version >= 1),
	CONSTRAINT ck_fc_scene_content_digest CHECK (content_digest ~ '^[0-9a-f]{64}$'),
        CONSTRAINT fk_fc_scene_version_scene FOREIGN KEY(user_id, course_id, scene_id)
    REFERENCES free_course_scenes (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
    INITIALLY DEFERRED,
        CONSTRAINT fk_fc_scene_version_plan FOREIGN KEY(user_id, course_id, plan_id)
    REFERENCES free_course_plans (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE free_course_versions (
	plan_id UUID NOT NULL,
	digest VARCHAR(64) NOT NULL,
	manifest_json JSONB NOT NULL,
	course_id UUID NOT NULL,
	version INTEGER NOT NULL,
	schema_version VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_fc_version_identity UNIQUE (user_id, course_id, id),
	CONSTRAINT uq_fc_version_version UNIQUE (user_id, course_id, version),
        CONSTRAINT fk_fc_version_course FOREIGN KEY(user_id, course_id) REFERENCES
    free_courses (user_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT ck_fc_version_positive CHECK (version >= 1),
	CONSTRAINT ck_fc_version_digest CHECK (digest ~ '^[0-9a-f]{64}$'),
        CONSTRAINT fk_fc_version_plan FOREIGN KEY(user_id, course_id, plan_id) REFERENCES
    free_course_plans (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED
)""",
    """CREATE TABLE free_course_node_links (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	course_id UUID NOT NULL,
	course_version_id UUID NOT NULL,
	scene_id UUID,
	node_id VARCHAR(64) NOT NULL,
	graph_version VARCHAR(64) NOT NULL,
	relation VARCHAR(24) NOT NULL,
	source VARCHAR(32) NOT NULL,
	evidence_refs JSONB NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_link_version FOREIGN KEY(user_id, course_id, course_version_id)
    REFERENCES free_course_versions (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
    INITIALLY DEFERRED,
        CONSTRAINT fk_fc_link_scene FOREIGN KEY(user_id, course_id, scene_id) REFERENCES
    free_course_scenes (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT ck_fc_link_known_node CHECK ((graph_version = 'mvp-0.2.0' AND node_id IN
    ('array', 'c-pointer', 'circular- queue', 'linked-list-concept', 'linked-list-deletion',
    'linked-list- insertion', 'linked-list-traversal', 'queue', 'single-linked-list',
    'stack')) OR (graph_version = 'phase-1.1.0' AND node_id IN ('array', 'array-stack',
    'balanced-binary-search-tree', 'binary-heap', 'binary-search-tree', 'binary- tree',
    'binary-tree-traversal', 'breadth-first-search', 'bubble-sort', 'c-pointer',
    'circular-linked-list', 'circular-queue', 'depth-first-search', 'doubly-linked-list',
    'graph-representation', 'heap-sort', 'insertion-sort', 'linked-list-concept',
    'linked-list-deletion', 'linked-list-insertion', 'linked-list-traversal', 'linked-stack',
    'merge-sort', 'queue', 'quick-sort', 'selection-sort', 'single-linked-list',
    'sorting-comparison', 'stack', 'tree- concept'))),
	CONSTRAINT ck_fc_link_relation CHECK (relation IN ('target','supporting')),
	CONSTRAINT ck_fc_link_source CHECK (source IN ('user_selected','planner_suggestion'))
)""",
    """CREATE UNIQUE INDEX uq_fc_link_course_node ON free_course_node_links (user_id,
    course_version_id, node_id) WHERE scene_id IS NULL""",
    """CREATE UNIQUE INDEX uq_fc_link_scene_node ON free_course_node_links (user_id,
    course_version_id, scene_id, node_id) WHERE scene_id IS NOT NULL""",
]


FUNCTION_DDL = [
    """CREATE FUNCTION fc_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP = 'DELETE' AND NOT EXISTS(SELECT 1 FROM users WHERE id=OLD.user_id) THEN
   RETURN OLD;
 END IF;
 RAISE EXCEPTION 'free course snapshot is append only' USING ERRCODE='23514';
END; $$""",
    """CREATE FUNCTION fc_course_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
   IF NOT EXISTS(SELECT 1 FROM users WHERE id=OLD.user_id) THEN RETURN OLD; END IF;
   RAISE EXCEPTION 'free course identity is immutable' USING ERRCODE='23514';
 END IF;
 IF (to_jsonb(NEW)-'head_version_id') IS DISTINCT FROM (to_jsonb(OLD)-'head_version_id') THEN
   RAISE EXCEPTION 'free course origin is immutable' USING ERRCODE='23514';
 END IF;
 IF NEW.head_version_id IS DISTINCT FROM OLD.head_version_id AND OLD.head_version_id IS NOT NULL
 AND (NEW.head_version_id IS NULL OR NOT EXISTS(
   SELECT 1 FROM free_course_versions n JOIN free_course_versions o ON o.id=OLD.head_version_id
   WHERE n.id=NEW.head_version_id AND n.user_id=OLD.user_id AND n.course_id=OLD.id
   AND n.version>o.version)) THEN
   RAISE EXCEPTION 'free course head cannot move backwards' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$""",
    """CREATE FUNCTION fc_snapshot_sequence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE last_version integer;
BEGIN
 PERFORM 1 FROM free_courses WHERE user_id=NEW.user_id AND id=NEW.course_id FOR UPDATE;
 IF TG_TABLE_NAME='free_course_scene_versions' THEN
   SELECT max(version) INTO last_version FROM free_course_scene_versions
   WHERE user_id=NEW.user_id AND course_id=NEW.course_id AND scene_id=NEW.scene_id;
 ELSE
   EXECUTE format('SELECT max(version) FROM %I WHERE user_id=$1 AND course_id=$2',TG_TABLE_NAME)
   INTO last_version USING NEW.user_id,NEW.course_id;
 END IF;
 IF NEW.version<=coalesce(last_version,0) THEN
   RAISE EXCEPTION 'free course version must increase' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$""",
    """CREATE FUNCTION fc_request_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF jsonb_typeof(NEW.evidence_snapshot) IS DISTINCT FROM 'object'
 OR jsonb_typeof(NEW.nonsecret_config_snapshot) IS DISTINCT FROM 'object'
 OR length(btrim(NEW.request_text))=0 THEN
   RAISE EXCEPTION 'invalid request snapshot' USING ERRCODE='23514';
 END IF;
 IF NEW.kind='original' AND NOT EXISTS(SELECT 1 FROM free_courses
   WHERE id=NEW.course_id AND user_id=NEW.user_id AND original_goal=NEW.request_text) THEN
   RAISE EXCEPTION 'original request must preserve goal' USING ERRCODE='23514';
 END IF;
 IF NEW.parent_request_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM free_course_requests
   WHERE id=NEW.parent_request_id AND user_id=NEW.user_id AND course_id=NEW.course_id
   AND version<NEW.version) THEN
   RAISE EXCEPTION 'invalid request parent' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$""",
    """CREATE FUNCTION fc_plan_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE entry jsonb; dep text; seen text[] := '{}'; sid uuid;
BEGIN
 IF jsonb_typeof(NEW.plan_json->'scenes') IS DISTINCT FROM 'array' THEN
   RAISE EXCEPTION 'plan scenes required' USING ERRCODE='23514';
 END IF;
 IF jsonb_array_length(NEW.plan_json->'scenes') NOT BETWEEN 1 AND 8 THEN
   RAISE EXCEPTION 'plan size invalid' USING ERRCODE='23514';
 END IF;
 FOR entry IN SELECT value FROM jsonb_array_elements(NEW.plan_json->'scenes') LOOP
   sid := (entry->>'scene_id')::uuid;
   IF sid IS NULL OR sid::text=ANY(seen) OR NOT EXISTS(SELECT 1 FROM free_course_scenes
     WHERE user_id=NEW.user_id AND course_id=NEW.course_id AND id=sid)
     OR jsonb_typeof(entry->'depends_on') IS DISTINCT FROM 'array' THEN
     RAISE EXCEPTION 'invalid plan scene binding' USING ERRCODE='23514';
   END IF;
   IF (SELECT count(*) FROM jsonb_array_elements_text(entry->'depends_on')) <>
      (SELECT count(DISTINCT value) FROM jsonb_array_elements_text(entry->'depends_on')) THEN
     RAISE EXCEPTION 'duplicate dependency' USING ERRCODE='23514';
   END IF;
   FOR dep IN SELECT value FROM jsonb_array_elements_text(entry->'depends_on') LOOP
     IF NOT dep=ANY(seen) THEN
       RAISE EXCEPTION 'dependency must precede scene' USING ERRCODE='23514';
     END IF;
   END LOOP;
   seen := array_append(seen,sid::text);
 END LOOP;
 RETURN NEW;
END; $$""",
    """CREATE FUNCTION fc_scene_version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE entry jsonb; dep jsonb; expected jsonb; seen text[] := '{}';
BEGIN
 SELECT value INTO entry FROM free_course_plans p,
   jsonb_array_elements(p.plan_json->'scenes')
 WHERE p.id=NEW.plan_id AND p.user_id=NEW.user_id AND p.course_id=NEW.course_id
 AND value->>'scene_id'=NEW.scene_id::text;
 IF entry IS NULL OR jsonb_typeof(NEW.content_json) IS DISTINCT FROM 'object'
 OR jsonb_typeof(NEW.actions_json) IS DISTINCT FROM 'array'
 OR jsonb_typeof(NEW.dependency_bindings) IS DISTINCT FROM 'array' THEN
   RAISE EXCEPTION 'invalid scene plan or payload' USING ERRCODE='23514';
 END IF;
 expected := entry->'depends_on';
 IF jsonb_array_length(expected)<>jsonb_array_length(NEW.dependency_bindings) THEN
   RAISE EXCEPTION 'dependency binding incomplete' USING ERRCODE='23514';
 END IF;
 FOR dep IN SELECT value FROM jsonb_array_elements(NEW.dependency_bindings) LOOP
   IF dep->>'scene_id' IS NULL OR dep->>'scene_id'=ANY(seen)
     OR NOT expected ? (dep->>'scene_id') OR NOT EXISTS(
       SELECT 1 FROM free_course_scene_versions v WHERE v.user_id=NEW.user_id
       AND v.course_id=NEW.course_id AND v.plan_id=NEW.plan_id
       AND v.scene_id=(dep->>'scene_id')::uuid
       AND v.id=(dep->>'scene_version_id')::uuid
       AND v.content_digest=dep->>'content_digest') THEN
     RAISE EXCEPTION 'invalid exact upstream version' USING ERRCODE='23514';
   END IF;
   seen := array_append(seen,dep->>'scene_id');
 END LOOP;
 RETURN NEW;
END; $$""",
    """CREATE FUNCTION fc_manifest_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE planned jsonb; entry jsonb; content free_course_scene_versions%ROWTYPE;
        dep jsonb; idx integer := 0; seen jsonb := '{}'::jsonb;
BEGIN
 SELECT plan_json->'scenes' INTO planned FROM free_course_plans
 WHERE id=NEW.plan_id AND user_id=NEW.user_id AND course_id=NEW.course_id;
 IF planned IS NULL OR jsonb_typeof(NEW.manifest_json->'scenes') IS DISTINCT FROM 'array' THEN
   RAISE EXCEPTION 'manifest plan missing' USING ERRCODE='23514';
 END IF;
 IF jsonb_array_length(planned)<>jsonb_array_length(NEW.manifest_json->'scenes') THEN
   RAISE EXCEPTION 'manifest must include all planned scenes' USING ERRCODE='23514';
 END IF;
 FOR entry IN SELECT value FROM jsonb_array_elements(NEW.manifest_json->'scenes') LOOP
   IF entry->>'scene_id' IS DISTINCT FROM planned->idx->>'scene_id'
     OR NOT entry ? 'scene_version_id' THEN
     RAISE EXCEPTION 'manifest scene order mismatch' USING ERRCODE='23514';
   END IF;
   IF entry->>'scene_version_id' IS NOT NULL THEN
     SELECT * INTO content FROM free_course_scene_versions
     WHERE id=(entry->>'scene_version_id')::uuid
       AND user_id=NEW.user_id AND course_id=NEW.course_id AND plan_id=NEW.plan_id
       AND scene_id=(entry->>'scene_id')::uuid;
     IF NOT FOUND THEN
       RAISE EXCEPTION 'manifest content binding invalid' USING ERRCODE='23514';
     END IF;
     FOR dep IN SELECT value FROM jsonb_array_elements(content.dependency_bindings) LOOP
       IF seen->>(dep->>'scene_id') IS DISTINCT FROM dep->>'scene_version_id' THEN
         RAISE EXCEPTION 'manifest upstream version mismatch' USING ERRCODE='23514';
       END IF;
     END LOOP;
   END IF;
   seen := seen || jsonb_build_object(entry->>'scene_id',entry->'scene_version_id');
   idx := idx+1;
 END LOOP;
 RETURN NEW;
END; $$""",
    """CREATE FUNCTION fc_node_link_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE manifest jsonb; version_xid text;
BEGIN
 SELECT manifest_json,xmin::text INTO manifest,version_xid FROM free_course_versions
 WHERE id=NEW.course_version_id AND user_id=NEW.user_id AND course_id=NEW.course_id;
 IF manifest IS NULL OR version_xid IS DISTINCT FROM
   mod(pg_current_xact_id()::text::numeric,4294967296)::text THEN
   RAISE EXCEPTION 'links must be written with new manifest' USING ERRCODE='23514';
 END IF;
 IF NEW.scene_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(manifest->'scenes')
   WHERE value->>'scene_id'=NEW.scene_id::text) THEN
   RAISE EXCEPTION 'linked scene absent from manifest' USING ERRCODE='23514';
 END IF;
 IF jsonb_typeof(NEW.evidence_refs) IS DISTINCT FROM 'array' THEN
   RAISE EXCEPTION 'invalid link evidence' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$""",
]

TABLES = [
    "free_courses",
    "free_course_requests",
    "free_course_scenes",
    "free_course_plans",
    "free_course_scene_versions",
    "free_course_versions",
    "free_course_node_links",
]


def upgrade() -> None:
    op.execute(
        "ALTER TABLE student_profiles ADD CONSTRAINT uq_student_profiles_owner_id_version "
        "UNIQUE (user_id,id,version)"
    )
    for ddl in TABLE_DDL:
        op.execute(ddl)
    op.execute(
        "ALTER TABLE free_courses ADD CONSTRAINT fk_free_course_head "
        "FOREIGN KEY(user_id,id,head_version_id) "
        "REFERENCES free_course_versions(user_id,course_id,id) "
        "DEFERRABLE INITIALLY DEFERRED"
    )
    for ddl in FUNCTION_DDL:
        op.execute(ddl)
    op.execute(
        "CREATE TRIGGER fc_course_protect BEFORE UPDATE OR DELETE ON free_courses "
        "FOR EACH ROW EXECUTE FUNCTION fc_course_guard()"
    )
    for table in TABLES[1:]:
        op.execute(
            f"CREATE TRIGGER fc_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
        )
    for table in [
        "free_course_requests",
        "free_course_plans",
        "free_course_scene_versions",
        "free_course_versions",
    ]:
        op.execute(
            f"CREATE TRIGGER fc_00_sequence BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION fc_snapshot_sequence()"
        )
    for table, function in [
        ("free_course_requests", "fc_request_guard"),
        ("free_course_plans", "fc_plan_guard"),
        ("free_course_scene_versions", "fc_scene_version_guard"),
        ("free_course_versions", "fc_manifest_guard"),
        ("free_course_node_links", "fc_node_link_guard"),
    ]:
        op.execute(
            f"CREATE TRIGGER fc_validate BEFORE INSERT ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(
            f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM {table}) THEN "
            "RAISE EXCEPTION 'free course data prevents downgrade'; END IF; END $$"
        )
    op.execute("ALTER TABLE free_courses DROP CONSTRAINT fk_free_course_head")
    for table in reversed(TABLES):
        op.drop_table(table)
    for function in [
        "fc_node_link_guard",
        "fc_manifest_guard",
        "fc_scene_version_guard",
        "fc_plan_guard",
        "fc_request_guard",
        "fc_snapshot_sequence",
        "fc_course_guard",
        "fc_immutable",
    ]:
        op.execute(f"DROP FUNCTION {function}()")
    op.execute("ALTER TABLE student_profiles DROP CONSTRAINT uq_student_profiles_owner_id_version")
