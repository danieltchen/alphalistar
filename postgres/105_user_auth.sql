BEGIN;

SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));

-- Extend existing USERS table with authentication columns
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS password_hash TEXT,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Backfill updated_at for any legacy rows that might still be NULL
UPDATE users
   SET updated_at = COALESCE(updated_at, created_at, NOW());

COMMENT ON COLUMN users.password_hash IS 'BCrypt-hashed password';
COMMENT ON COLUMN users.is_active IS 'Soft delete / invitation status flag';
COMMENT ON COLUMN users.updated_at IS 'Last profile update timestamp';

COMMIT;
