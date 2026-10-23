-- TrustVault model schema snapshot generated from backend/app/main.py.
-- Review/migration notes: DATABASE_SCHEMA.md. This is a schema snapshot, not a migration history.
-- Audit triggers are appended below. Test changes against a fresh and an upgraded database.
BEGIN;
CREATE TABLE audit_chain_head (
	id SERIAL NOT NULL, 
	last_event_id INTEGER NOT NULL, 
	head_hash VARCHAR(64) NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	username VARCHAR(32) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	system_role VARCHAR(16) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE documents (
	id SERIAL NOT NULL, 
	owner_id INTEGER NOT NULL, 
	filename VARCHAR(200) NOT NULL, 
	category VARCHAR(80) NOT NULL, 
	storage_key VARCHAR(80) NOT NULL, 
	content_type VARCHAR(150) NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE, 
	UNIQUE (storage_key)
);

CREATE INDEX ix_documents_owner_id ON documents (owner_id);

CREATE TABLE audit_events (
	id SERIAL NOT NULL, 
	actor_id INTEGER, 
	document_id INTEGER, 
	action VARCHAR(40) NOT NULL, 
	target_username VARCHAR(32), 
	details VARCHAR(500) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	actor_username_snapshot VARCHAR(32) NOT NULL, 
	document_ref VARCHAR(80), 
	document_name_snapshot VARCHAR(200), 
	previous_hash VARCHAR(64) NOT NULL, 
	event_hash VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_events_document_id ON audit_events (document_id);

CREATE INDEX ix_audit_events_action ON audit_events (action);

CREATE INDEX ix_audit_events_actor_id ON audit_events (actor_id);

CREATE TABLE document_shares (
	id SERIAL NOT NULL, 
	document_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	granted_by INTEGER NOT NULL, 
	role VARCHAR(10) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_document_share_user UNIQUE (document_id, user_id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(granted_by) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_document_shares_document_id ON document_shares (document_id);

CREATE INDEX ix_document_shares_user_id ON document_shares (user_id);

CREATE OR REPLACE FUNCTION trustvault_block_audit_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_events is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trustvault_audit_immutable ON audit_events;
CREATE TRIGGER trustvault_audit_immutable BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION trustvault_block_audit_mutation();
COMMIT;
