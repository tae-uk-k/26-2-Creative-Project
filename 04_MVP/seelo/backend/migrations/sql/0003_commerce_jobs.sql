-- 쇼핑몰 브라우저·AI 작업 상태와 위임 가게 식별값. 기존 쇼핑몰·지도 데이터는 바꾸지 않는다.

ALTER TABLE commerce_shops ADD COLUMN delegation JSONB DEFAULT '{}' NOT NULL;

CREATE TABLE commerce_jobs (
	id BIGINT GENERATED ALWAYS AS IDENTITY,
	shop_id BIGINT NOT NULL,
	product_id BIGINT,
	plan_id BIGINT,
	kind TEXT NOT NULL,
	status TEXT DEFAULT 'queued' NOT NULL,
	dedupe_key TEXT NOT NULL,
	input JSONB DEFAULT '{}' NOT NULL,
	result JSONB DEFAULT '{}' NOT NULL,
	error_code TEXT,
	requested_by BIGINT,
	queue_job_id BIGINT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT ck_commerce_job_kind CHECK (kind IN ('collect','apply','rollback','verify','catalog','prepare','forget_session')),
	CONSTRAINT ck_commerce_job_status CHECK (status IN ('queued','running','succeeded','failed')),
	FOREIGN KEY(shop_id) REFERENCES commerce_shops (id) ON DELETE CASCADE,
	FOREIGN KEY(product_id) REFERENCES commerce_products (id) ON DELETE CASCADE,
	FOREIGN KEY(plan_id) REFERENCES commerce_plans (id) ON DELETE CASCADE,
	FOREIGN KEY(requested_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_commerce_jobs_shop ON commerce_jobs (shop_id, id);
CREATE INDEX ix_commerce_jobs_plan ON commerce_jobs (plan_id);
-- 같은 상품 수집·같은 정비안 저장을 동시에 두 번 등록하지 않는다.
CREATE UNIQUE INDEX uq_commerce_active_job ON commerce_jobs (shop_id, dedupe_key) WHERE status IN ('queued','running');
