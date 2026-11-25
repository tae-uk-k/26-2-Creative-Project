-- 쇼핑몰 AI 노출 진단. 지도 베타의 측정 테이블과 분리한다. 질문 세트는 수정하지 않고 새 버전으로 만든다.

ALTER TABLE commerce_jobs DROP CONSTRAINT ck_commerce_job_kind;
ALTER TABLE commerce_jobs ADD CONSTRAINT ck_commerce_job_kind
	CHECK (kind IN ('collect','apply','rollback','verify','catalog','prepare','forget_session','measure'));

CREATE TABLE commerce_measure_sets (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	product_id BIGINT NOT NULL,
	name TEXT NOT NULL,
	common_suffix TEXT NOT NULL,
	queries JSONB NOT NULL,
	targets JSONB NOT NULL,
	created_by BIGINT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(product_id) REFERENCES commerce_products (id) ON DELETE CASCADE,
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_commerce_measure_sets_product ON commerce_measure_sets (product_id);

CREATE TABLE commerce_measure_runs (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	set_id BIGINT NOT NULL,
	product_id BIGINT NOT NULL,
	label TEXT NOT NULL,
	status TEXT DEFAULT 'queued' NOT NULL,
	condition JSONB NOT NULL,
	snapshot_hash TEXT NOT NULL,
	plan_id BIGINT,
	created_by BIGINT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_commerce_measure_run_status CHECK (status IN ('queued','running','completed','partial','failed')),
	FOREIGN KEY(set_id) REFERENCES commerce_measure_sets (id) ON DELETE CASCADE,
	FOREIGN KEY(product_id) REFERENCES commerce_products (id) ON DELETE CASCADE,
	FOREIGN KEY(plan_id) REFERENCES commerce_plans (id) ON DELETE SET NULL,
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_commerce_measure_runs_product ON commerce_measure_runs (product_id, id);

CREATE TABLE commerce_measure_answers (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	run_id BIGINT NOT NULL,
	query_id TEXT NOT NULL,
	repeat INTEGER NOT NULL,
	attempt INTEGER NOT NULL,
	status TEXT NOT NULL,
	error_code TEXT,
	prompt TEXT NOT NULL,
	raw_text TEXT,
	sources JSONB DEFAULT '[]' NOT NULL,
	model_id TEXT,
	identified BOOLEAN,
	recommended BOOLEAN,
	rank INTEGER,
	target_url_cited BOOLEAN,
	evaluation JSONB DEFAULT '{}' NOT NULL,
	measured_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_commerce_measure_answer_status CHECK (status IN ('ok','failed')),
	CONSTRAINT uq_commerce_measure_answer UNIQUE (run_id, query_id, repeat, attempt),
	FOREIGN KEY(run_id) REFERENCES commerce_measure_runs (id) ON DELETE CASCADE
);
