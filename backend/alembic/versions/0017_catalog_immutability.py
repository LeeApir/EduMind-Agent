"""Keep catalog provenance immutable; withdrawal never permits reapproval."""

from alembic import op

revision = "0017_catalog_immutability"
down_revision = "0016_catalog_releases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION prevent_catalog_release_update() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF (to_jsonb(NEW) - 'status' - 'revoked_at') IS DISTINCT FROM
               (to_jsonb(OLD) - 'status' - 'revoked_at')
               OR OLD.status = 'revoked'
               OR (NEW.status = 'approved' AND NEW.revoked_at IS NOT NULL)
               OR (NEW.status = 'revoked' AND NEW.revoked_at IS NULL) THEN
                RAISE EXCEPTION 'catalog release provenance is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_catalog_release_immutable BEFORE UPDATE ON catalog_releases
        FOR EACH ROW EXECUTE FUNCTION prevent_catalog_release_update()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_catalog_release_immutable ON catalog_releases")
    op.execute("DROP FUNCTION prevent_catalog_release_update()")
