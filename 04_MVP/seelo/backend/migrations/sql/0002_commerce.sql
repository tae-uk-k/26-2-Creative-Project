-- 쇼핑몰 독립 스키마. 기존 지도 테이블은 유지한다.

CREATE TABLE commerce_shops (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	owner_id BIGINT NOT NULL,
	platform TEXT NOT NULL,
	external_id TEXT NOT NULL,
	shop_no BIGINT NOT NULL,
	name TEXT NOT NULL,
	manager_status TEXT DEFAULT 'not_requested' NOT NULL,
	api_status TEXT DEFAULT 'not_connected' NOT NULL,
	credentials BYTEA,
	scopes JSONB DEFAULT '[]' NOT NULL,
	access_expires_at TIMESTAMP WITH TIME ZONE,
	oauth_state_hash TEXT,
	oauth_expires_at TIMESTAMP WITH TIME ZONE,
	read_verified_at TIMESTAMP WITH TIME ZONE,
	write_verified_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_commerce_platform CHECK (platform IN ('cafe24', 'smartstore')),
	CONSTRAINT ck_commerce_shop_no CHECK (shop_no > 0),
	CONSTRAINT ck_commerce_manager_status CHECK (manager_status IN ('not_requested','invited','verified','revoked')),
	CONSTRAINT ck_commerce_api_status CHECK (api_status IN ('not_connected','authorized','read_verified','write_verified','revoked')),
	CONSTRAINT uq_commerce_shop UNIQUE (owner_id, platform, external_id, shop_no),
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE commerce_products (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	shop_id BIGINT NOT NULL,
	external_id TEXT NOT NULL,
	name TEXT NOT NULL,
	identity TEXT NOT NULL,
	snapshot JSONB NOT NULL,
	snapshot_hash TEXT NOT NULL,
	snapshot_source TEXT NOT NULL,
	facts JSONB DEFAULT '[]' NOT NULL,
	asked_fields JSONB DEFAULT '[]' NOT NULL,
	collected_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_commerce_product UNIQUE (shop_id, external_id),
	FOREIGN KEY(shop_id) REFERENCES commerce_shops (id) ON DELETE CASCADE
);

CREATE TABLE commerce_plans (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	product_id BIGINT NOT NULL,
	status TEXT DEFAULT 'draft' NOT NULL,
	snapshot_hash TEXT NOT NULL,
	changes JSONB NOT NULL,
	questions JSONB DEFAULT '[]' NOT NULL,
	deferred JSONB DEFAULT '[]' NOT NULL,
	approval JSONB DEFAULT '{}' NOT NULL,
	model_id TEXT,
	approved_at TIMESTAMP WITH TIME ZONE,
	applied_at TIMESTAMP WITH TIME ZONE,
	publication JSONB DEFAULT '{}' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_commerce_plan_status CHECK (status IN ('draft','approved','no_changes','applying','applied','pending_reflection','uncertain','conflict','rejected','manual_required','manual_recorded','rolled_back','superseded')),
	FOREIGN KEY(product_id) REFERENCES commerce_products (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX uq_commerce_active_plan ON commerce_plans (product_id) WHERE status IN ('approved','applying','pending_reflection','uncertain');

CREATE TABLE commerce_writes (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	plan_id BIGINT NOT NULL,
	action TEXT NOT NULL,
	status TEXT NOT NULL,
	before JSONB NOT NULL,
	after JSONB NOT NULL,
	error_code TEXT,
	note TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	finished_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_commerce_write_action CHECK (action IN ('apply','rollback')),
	FOREIGN KEY(plan_id) REFERENCES commerce_plans (id) ON DELETE CASCADE
);
