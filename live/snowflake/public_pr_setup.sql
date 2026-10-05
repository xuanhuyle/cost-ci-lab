-- Cost CI live phase, adapted to the PUBLIC PR CORPUS (tuva-health/tuva-core).
-- Status: PREPARED, NOT EXECUTED. UNVALIDATED (written without account access).
--
-- Why this replaces live/snowflake/setup.sql for the live phase:
--   setup.sql provisions TPC-H for the previous stage's 26 hand-written scenarios. The question
--   that matters now is transfer on NATURAL PRs, so the live phase must run the same public
--   corpus the local phase ran. The corpus project (Tuva Core) supports Snowflake natively and
--   loads its data from the SAME public S3 bucket by COPY INTO with no credentials, so nothing
--   has to be ported: the corpus runs unchanged.
--
-- Run as a role with CREATE WAREHOUSE / CREATE DATABASE in a TRIAL or sandbox account.
-- Everything is created under COSTCI_* names and removed by teardown.sql.

-- Two dedicated, pinned, single-cluster warehouses. The CI/production SIZE gap is the variable
-- E3 (E-039) showed can distort and even flip ratios, so it is the first thing to test live.
CREATE WAREHOUSE IF NOT EXISTS COSTCI_CI_WH
  WAREHOUSE_SIZE = 'XSMALL' GENERATION = '1' MAX_CLUSTER_COUNT = 1 MIN_CLUSTER_COUNT = 1
  AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  ENABLE_QUERY_ACCELERATION = FALSE STATEMENT_TIMEOUT_IN_SECONDS = 3600
  COMMENT = 'Cost CI public-PR experiment: pre-merge CI runs';
CREATE WAREHOUSE IF NOT EXISTS COSTCI_PROD_WH
  WAREHOUSE_SIZE = 'SMALL' GENERATION = '1' MAX_CLUSTER_COUNT = 1 MIN_CLUSTER_COUNT = 1
  AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  ENABLE_QUERY_ACCELERATION = FALSE STATEMENT_TIMEOUT_IN_SECONDS = 7200
  COMMENT = 'Cost CI public-PR experiment: shadow production runs';

-- Hard spend cap for the whole experiment. Set CREDIT_QUOTA to the approved budget and no more.
CREATE RESOURCE MONITOR IF NOT EXISTS COSTCI_CAP WITH CREDIT_QUOTA = 60
  TRIGGERS ON 50 PERCENT DO NOTIFY
           ON 80 PERCENT DO NOTIFY
           ON 100 PERCENT DO SUSPEND_IMMEDIATE;
ALTER WAREHOUSE COSTCI_CI_WH   SET RESOURCE_MONITOR = COSTCI_CAP;
ALTER WAREHOUSE COSTCI_PROD_WH SET RESOURCE_MONITOR = COSTCI_CAP;

-- One database for the whole experiment. Tuva Core creates its own schemas inside it
-- (input_layer, normalized_layer, claims_preprocessing, core, data_quality, terminology, ...).
CREATE DATABASE IF NOT EXISTS COSTCI_TUVA;
USE DATABASE COSTCI_TUVA;
USE WAREHOUSE COSTCI_PROD_WH;

-- Measurement hygiene: never serve a result from cache, and tag every statement so the
-- experiment's queries can be separated from everything else in ACCOUNT_USAGE.
ALTER SESSION SET USE_CACHED_RESULT = FALSE;
ALTER SESSION SET QUERY_TAG = 'costci:public_pr:setup';

-- No data loading is needed here. Tuva Core's own `snowflake__load_seed` macro issues
--     COPY INTO <seed> FROM s3://tuva-public-resources/... FILE_FORMAT = (TYPE = CSV ...)
-- with no CREDENTIALS clause, against a publicly readable bucket, so `dbt build` populates the
-- source data itself. Nothing in the corpus project is modified.

-- Telemetry access for the experiment role (run as ACCOUNTADMIN; least privilege via DB roles):
--   GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER      TO ROLE COSTCI_ROLE;  -- metering, attribution
--   GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE COSTCI_ROLE;  -- query + access history
