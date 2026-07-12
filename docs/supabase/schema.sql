-- EV Charging Aggregator Platform — Supabase schema setup
--
-- Generated from evagg.models (the same SQLAlchemy metadata Alembic's
-- migrations use), so this matches the real schema exactly rather than
-- being hand-transcribed.
--
-- Paste this whole file into the Supabase SQL Editor (dashboard -> SQL
-- Editor -> New query) and run it once. This could not be verified against
-- your actual Supabase project from this session -- this sandbox's egress
-- policy blocks all of *.supabase.co, on every port (confirmed for both
-- :5432 and :443). It IS verified against a local Postgres 16 instance in
-- this same session (24 tables, all create cleanly) -- just not Supabase
-- itself. Report back if anything here errors when you run it.
--
-- What this does NOT do, deliberately:
--   - No TimescaleDB hypertable/continuous-aggregate/retention conversion
--     (Alembic's 8679657fe757/112b9fa6c114) -- Supabase does not offer the
--     timescaledb extension, so meter_value/status_log stay plain tables
--     here, same as this session's local sandbox Postgres fallback.
--   - No Postgres-role-based RLS (Alembic's cb7ac4e49b9a) -- that migration's
--     RLS policies key off current_setting('app.current_tenant'), a
--     session-level GUC set per-connection by evagg.core.tenancy. PostgREST
--     is stateless per-request and authenticates this app as the `anon`
--     role via the publishable API key (not a per-user JWT with tenant
--     claims), so that session-GUC approach does not apply here. Tenant
--     isolation is instead enforced at the application layer: every
--     Supabase-backed repository (evagg.persistence.supabase_*) includes an
--     explicit tenant_id=eq.<id> filter on every request. This is a real
--     gap versus the SQLAlchemy path's defense-in-depth RLS -- see
--     docs/production_readiness.md.
--
-- Safe to re-run: every CREATE TABLE/EXTENSION uses IF NOT EXISTS.

create extension if not exists pgcrypto;


CREATE TABLE IF NOT EXISTS carbon_zone (
	country_code VARCHAR(2) NOT NULL, 
	area_code VARCHAR(50) NOT NULL, 
	provider_zone_id VARCHAR(50) NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_carbon_zone PRIMARY KEY (id), 
	CONSTRAINT uq_carbon_zone_country_area UNIQUE (country_code, area_code)
);

CREATE TABLE IF NOT EXISTS charger (
	charge_point_id VARCHAR(255) NOT NULL, 
	vendor VARCHAR(100), 
	model VARCHAR(100), 
	firmware_version VARCHAR(50), 
	status VARCHAR(20) NOT NULL, 
	visibility VARCHAR(20) NOT NULL, 
	ws_credential_hash VARCHAR(255), 
	last_boot_at TIMESTAMP WITH TIME ZONE, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_charger PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS credential (
	subject_type VARCHAR(20) NOT NULL, 
	subject_id UUID NOT NULL, 
	credential_type VARCHAR(20) NOT NULL, 
	password_hash VARCHAR(255), 
	sso_provider VARCHAR(50), 
	sso_subject_id VARCHAR(255), 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_credential PRIMARY KEY (id), 
	CONSTRAINT uq_credential_subject_type UNIQUE (subject_type, subject_id, credential_type)
);

CREATE TABLE IF NOT EXISTS driver (
	email VARCHAR(255) NOT NULL, 
	phone VARCHAR(32), 
	full_name VARCHAR(255) NOT NULL, 
	autocharge_mac VARCHAR(17), 
	carbon_country_code VARCHAR(2), 
	carbon_area_code VARCHAR(50), 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_driver PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS invoice (
	account_id UUID NOT NULL, 
	period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	period_end TIMESTAMP WITH TIME ZONE NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	total_minor_units INTEGER NOT NULL, 
	due_at TIMESTAMP WITH TIME ZONE, 
	pdf_url VARCHAR(500), 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_invoice PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS ocpi_partner (
	party_id VARCHAR(3) NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	negotiated_version VARCHAR(10), 
	base_url VARCHAR(500) NOT NULL, 
	token_a VARCHAR(255), 
	token_b VARCHAR(255), 
	token_c VARCHAR(255), 
	status VARCHAR(20) NOT NULL, 
	last_handshake_at TIMESTAMP WITH TIME ZONE, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_ocpi_partner PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS ocpi_role_config (
	role VARCHAR(10) NOT NULL, 
	party_id VARCHAR(3) NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_ocpi_role_config PRIMARY KEY (id), 
	CONSTRAINT uq_ocpi_role_config_tenant_role UNIQUE (tenant_id, role)
);

CREATE TABLE IF NOT EXISTS operator_user (
	email VARCHAR(255) NOT NULL, 
	full_name VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_operator_user PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS organization (
	name VARCHAR(255) NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_organization PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS payout (
	operator_id UUID NOT NULL, 
	period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	period_end TIMESTAMP WITH TIME ZONE NOT NULL, 
	amount_minor_units INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_payout PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS tariff (
	name VARCHAR(255) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_tariff PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS command_log (
	charger_id UUID NOT NULL, 
	command_id UUID NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	requested_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	responded_at TIMESTAMP WITH TIME ZONE, 
	result JSONB, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_command_log PRIMARY KEY (id), 
	CONSTRAINT fk_command_log_charger_id_charger FOREIGN KEY(charger_id) REFERENCES charger (id)
);

CREATE TABLE IF NOT EXISTS connector (
	charger_id UUID NOT NULL, 
	connector_id INTEGER NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	error_code VARCHAR(50), 
	max_power_watts INTEGER, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_connector PRIMARY KEY (id), 
	CONSTRAINT uq_connector_charger_connector_id UNIQUE (charger_id, connector_id), 
	CONSTRAINT fk_connector_charger_id_charger FOREIGN KEY(charger_id) REFERENCES charger (id)
);

CREATE TABLE IF NOT EXISTS driver_daily_usage (
	driver_id UUID NOT NULL, 
	usage_date DATE NOT NULL, 
	session_count INTEGER NOT NULL, 
	kwh_total INTEGER NOT NULL, 
	cost_total_minor_units INTEGER NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_driver_daily_usage PRIMARY KEY (id), 
	CONSTRAINT uq_driver_daily_usage_driver_date UNIQUE (driver_id, usage_date), 
	CONSTRAINT fk_driver_daily_usage_driver_id_driver FOREIGN KEY(driver_id) REFERENCES driver (id)
);

CREATE TABLE IF NOT EXISTS firmware_update (
	charger_id UUID NOT NULL, 
	version VARCHAR(50) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_firmware_update PRIMARY KEY (id), 
	CONSTRAINT fk_firmware_update_charger_id_charger FOREIGN KEY(charger_id) REFERENCES charger (id)
);

CREATE TABLE IF NOT EXISTS invoice_adjustment (
	invoice_id UUID NOT NULL, 
	amount_minor_units INTEGER NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_invoice_adjustment PRIMARY KEY (id), 
	CONSTRAINT fk_invoice_adjustment_invoice_id_invoice FOREIGN KEY(invoice_id) REFERENCES invoice (id)
);

CREATE TABLE IF NOT EXISTS site (
	org_id UUID NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	address VARCHAR(500), 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_site PRIMARY KEY (id), 
	CONSTRAINT fk_site_org_id_organization FOREIGN KEY(org_id) REFERENCES organization (id)
);

CREATE TABLE IF NOT EXISTS status_log (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	tenant_id UUID NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	charger_id UUID NOT NULL, 
	connector_id INTEGER NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	error_code VARCHAR(50), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_status_log PRIMARY KEY (id, ts), 
	CONSTRAINT fk_status_log_charger_id_charger FOREIGN KEY(charger_id) REFERENCES charger (id)
);

CREATE TABLE IF NOT EXISTS tariff_component (
	tariff_id UUID NOT NULL, 
	type VARCHAR(10) NOT NULL, 
	price_minor_units INTEGER NOT NULL, 
	step_size INTEGER NOT NULL, 
	applies_after_minutes INTEGER, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_tariff_component PRIMARY KEY (id), 
	CONSTRAINT fk_tariff_component_tariff_id_tariff FOREIGN KEY(tariff_id) REFERENCES tariff (id)
);

CREATE TABLE IF NOT EXISTS tariff_version (
	tariff_id UUID NOT NULL, 
	version_no INTEGER NOT NULL, 
	effective_from TIMESTAMP WITH TIME ZONE NOT NULL, 
	effective_to TIMESTAMP WITH TIME ZONE, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_tariff_version PRIMARY KEY (id), 
	CONSTRAINT fk_tariff_version_tariff_id_tariff FOREIGN KEY(tariff_id) REFERENCES tariff (id)
);

CREATE TABLE IF NOT EXISTS transaction (
	charger_id UUID NOT NULL, 
	connector_id INTEGER NOT NULL, 
	id_tag VARCHAR(50) NOT NULL, 
	meter_start INTEGER NOT NULL, 
	meter_stop INTEGER, 
	start_timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
	stop_timestamp TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(20) NOT NULL, 
	stop_reason VARCHAR(50), 
	payment_status VARCHAR(20) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_transaction PRIMARY KEY (id), 
	CONSTRAINT fk_transaction_charger_id_charger FOREIGN KEY(charger_id) REFERENCES charger (id)
);

CREATE TABLE IF NOT EXISTS wallet (
	driver_id UUID NOT NULL, 
	balance_minor_units INTEGER NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_wallet PRIMARY KEY (id), 
	CONSTRAINT fk_wallet_driver_id_driver FOREIGN KEY(driver_id) REFERENCES driver (id)
);

CREATE TABLE IF NOT EXISTS meter_value (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	tenant_id UUID NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	transaction_id UUID NOT NULL, 
	charger_id UUID NOT NULL, 
	measurand VARCHAR(50) NOT NULL, 
	value FLOAT NOT NULL, 
	unit VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_meter_value PRIMARY KEY (id, ts), 
	CONSTRAINT fk_meter_value_transaction_id_transaction FOREIGN KEY(transaction_id) REFERENCES transaction (id), 
	CONSTRAINT fk_meter_value_charger_id_charger FOREIGN KEY(charger_id) REFERENCES charger (id)
);

CREATE TABLE IF NOT EXISTS ocpi_session (
	partner_id UUID NOT NULL, 
	local_transaction_id UUID, 
	external_session_id VARCHAR(36) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	kwh INTEGER NOT NULL, 
	start_datetime TIMESTAMP WITH TIME ZONE NOT NULL, 
	end_datetime TIMESTAMP WITH TIME ZONE, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_ocpi_session PRIMARY KEY (id), 
	CONSTRAINT fk_ocpi_session_partner_id_ocpi_partner FOREIGN KEY(partner_id) REFERENCES ocpi_partner (id), 
	CONSTRAINT fk_ocpi_session_local_transaction_id_transaction FOREIGN KEY(local_transaction_id) REFERENCES transaction (id)
);

CREATE TABLE IF NOT EXISTS payment_method (
	wallet_id UUID NOT NULL, 
	type VARCHAR(20) NOT NULL, 
	psp_token VARCHAR(255), 
	is_default BOOLEAN NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_payment_method PRIMARY KEY (id), 
	CONSTRAINT fk_payment_method_wallet_id_wallet FOREIGN KEY(wallet_id) REFERENCES wallet (id)
);

CREATE TABLE IF NOT EXISTS payout_rule (
	operator_id UUID NOT NULL, 
	site_id UUID, 
	split_type VARCHAR(10) NOT NULL, 
	value INTEGER NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_payout_rule PRIMARY KEY (id), 
	CONSTRAINT fk_payout_rule_site_id_site FOREIGN KEY(site_id) REFERENCES site (id)
);

CREATE TABLE IF NOT EXISTS promotion (
	code VARCHAR(50), 
	discount_type VARCHAR(10) NOT NULL, 
	value INTEGER NOT NULL, 
	valid_from TIMESTAMP WITH TIME ZONE NOT NULL, 
	valid_to TIMESTAMP WITH TIME ZONE NOT NULL, 
	usage_limit INTEGER, 
	site_id UUID, 
	operator_id UUID, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_promotion PRIMARY KEY (id), 
	CONSTRAINT fk_promotion_site_id_site FOREIGN KEY(site_id) REFERENCES site (id)
);

CREATE TABLE IF NOT EXISTS team (
	org_id UUID NOT NULL, 
	site_id UUID, 
	name VARCHAR(255) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_team PRIMARY KEY (id), 
	CONSTRAINT fk_team_org_id_organization FOREIGN KEY(org_id) REFERENCES organization (id), 
	CONSTRAINT fk_team_site_id_site FOREIGN KEY(site_id) REFERENCES site (id)
);

CREATE TABLE IF NOT EXISTS wallet_ledger (
	wallet_id UUID NOT NULL, 
	amount_minor_units INTEGER NOT NULL, 
	type VARCHAR(20) NOT NULL, 
	reference_id VARCHAR(255) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_wallet_ledger PRIMARY KEY (id), 
	CONSTRAINT fk_wallet_ledger_wallet_id_wallet FOREIGN KEY(wallet_id) REFERENCES wallet (id)
);

CREATE TABLE IF NOT EXISTS charger_team_access (
	charger_id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_charger_team_access PRIMARY KEY (id), 
	CONSTRAINT uq_charger_team_access_charger_team UNIQUE (charger_id, team_id), 
	CONSTRAINT fk_charger_team_access_charger_id_charger FOREIGN KEY(charger_id) REFERENCES charger (id), 
	CONSTRAINT fk_charger_team_access_team_id_team FOREIGN KEY(team_id) REFERENCES team (id)
);

CREATE TABLE IF NOT EXISTS driver_team_membership (
	driver_id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_driver_team_membership PRIMARY KEY (id), 
	CONSTRAINT uq_driver_team_membership_driver_team UNIQUE (driver_id, team_id), 
	CONSTRAINT fk_driver_team_membership_driver_id_driver FOREIGN KEY(driver_id) REFERENCES driver (id), 
	CONSTRAINT fk_driver_team_membership_team_id_team FOREIGN KEY(team_id) REFERENCES team (id)
);

CREATE TABLE IF NOT EXISTS ocpi_cdr (
	session_id UUID NOT NULL, 
	cdr_uid VARCHAR(36) NOT NULL, 
	total_cost_minor_units INTEGER NOT NULL, 
	kwh INTEGER NOT NULL, 
	correction_of UUID, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_ocpi_cdr PRIMARY KEY (id), 
	CONSTRAINT fk_ocpi_cdr_session_id_ocpi_session FOREIGN KEY(session_id) REFERENCES ocpi_session (id), 
	CONSTRAINT fk_ocpi_cdr_correction_of_ocpi_cdr FOREIGN KEY(correction_of) REFERENCES ocpi_cdr (id)
);

CREATE TABLE IF NOT EXISTS promotion_redemption (
	promotion_id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_promotion_redemption PRIMARY KEY (id), 
	CONSTRAINT uq_promotion_redemption_promotion_session UNIQUE (promotion_id, session_id), 
	CONSTRAINT fk_promotion_redemption_promotion_id_promotion FOREIGN KEY(promotion_id) REFERENCES promotion (id)
);

CREATE TABLE IF NOT EXISTS team_driver_daily_usage (
	team_id UUID NOT NULL, 
	driver_id UUID NOT NULL, 
	site_id UUID, 
	usage_date DATE NOT NULL, 
	session_count INTEGER NOT NULL, 
	kwh_total INTEGER NOT NULL, 
	cost_total_minor_units INTEGER NOT NULL, 
	is_complete BOOLEAN NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_team_driver_daily_usage PRIMARY KEY (id), 
	CONSTRAINT uq_team_driver_daily_usage_team_driver_date UNIQUE (team_id, driver_id, usage_date), 
	CONSTRAINT fk_team_driver_daily_usage_team_id_team FOREIGN KEY(team_id) REFERENCES team (id), 
	CONSTRAINT fk_team_driver_daily_usage_driver_id_driver FOREIGN KEY(driver_id) REFERENCES driver (id), 
	CONSTRAINT fk_team_driver_daily_usage_site_id_site FOREIGN KEY(site_id) REFERENCES site (id)
);

CREATE TABLE IF NOT EXISTS team_invite (
	code VARCHAR(16) NOT NULL, 
	team_id UUID NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	max_uses INTEGER NOT NULL, 
	used_count INTEGER NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_team_invite PRIMARY KEY (id), 
	CONSTRAINT fk_team_invite_team_id_team FOREIGN KEY(team_id) REFERENCES team (id)
);

CREATE TABLE IF NOT EXISTS ocpi_reconciliation_result (
	partner_id UUID NOT NULL, 
	local_cdr_id UUID, 
	partner_cdr_uid VARCHAR(36) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	delta_minor_units INTEGER, 
	tenant_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_ocpi_reconciliation_result PRIMARY KEY (id), 
	CONSTRAINT fk_ocpi_reconciliation_result_partner_id_ocpi_partner FOREIGN KEY(partner_id) REFERENCES ocpi_partner (id), 
	CONSTRAINT fk_ocpi_reconciliation_result_local_cdr_id_ocpi_cdr FOREIGN KEY(local_cdr_id) REFERENCES ocpi_cdr (id)
);

-- Grant the `anon` role (the identity PostgREST authenticates this app as,
-- via the publishable API key) full CRUD on every table above. RLS is left
-- disabled on all of them -- see the header note on why tenant isolation is
-- enforced in the application layer instead for this access pattern.
grant usage on schema public to anon;
grant select, insert, update, delete on public.carbon_zone to anon;
grant select, insert, update, delete on public.charger to anon;
grant select, insert, update, delete on public.credential to anon;
grant select, insert, update, delete on public.driver to anon;
grant select, insert, update, delete on public.invoice to anon;
grant select, insert, update, delete on public.ocpi_partner to anon;
grant select, insert, update, delete on public.ocpi_role_config to anon;
grant select, insert, update, delete on public.operator_user to anon;
grant select, insert, update, delete on public.organization to anon;
grant select, insert, update, delete on public.payout to anon;
grant select, insert, update, delete on public.tariff to anon;
grant select, insert, update, delete on public.command_log to anon;
grant select, insert, update, delete on public.connector to anon;
grant select, insert, update, delete on public.driver_daily_usage to anon;
grant select, insert, update, delete on public.firmware_update to anon;
grant select, insert, update, delete on public.invoice_adjustment to anon;
grant select, insert, update, delete on public.site to anon;
grant select, insert, update, delete on public.status_log to anon;
grant select, insert, update, delete on public.tariff_component to anon;
grant select, insert, update, delete on public.tariff_version to anon;
grant select, insert, update, delete on public.transaction to anon;
grant select, insert, update, delete on public.wallet to anon;
grant select, insert, update, delete on public.meter_value to anon;
grant select, insert, update, delete on public.ocpi_session to anon;
grant select, insert, update, delete on public.payment_method to anon;
grant select, insert, update, delete on public.payout_rule to anon;
grant select, insert, update, delete on public.promotion to anon;
grant select, insert, update, delete on public.team to anon;
grant select, insert, update, delete on public.wallet_ledger to anon;
grant select, insert, update, delete on public.charger_team_access to anon;
grant select, insert, update, delete on public.driver_team_membership to anon;
grant select, insert, update, delete on public.ocpi_cdr to anon;
grant select, insert, update, delete on public.promotion_redemption to anon;
grant select, insert, update, delete on public.team_driver_daily_usage to anon;
grant select, insert, update, delete on public.team_invite to anon;
grant select, insert, update, delete on public.ocpi_reconciliation_result to anon;
