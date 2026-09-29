-- BLUEBAN 813 operational database.
--
-- One schema, two engines: SQLite locally (services/api, default
-- data/blueban.sqlite) and Cloudflare D1 for the hosted deployment (D1 is
-- SQLite). Large rasters never live here; rows point at files under outputs/.
--
-- Conventions
--   * ids are TEXT, timestamps are ISO-8601 UTC strings.
--   * JSON columns are TEXT containing JSON.
--   * Predictions and reviews are APPEND-ONLY. A historical prediction is never
--     edited: re-scoring an incident with a new model adds a row.
--   * Every write goes through the audit log, which is hash-chained so any
--     after-the-fact edit of an audit row breaks the chain.

CREATE TABLE IF NOT EXISTS aois (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  emirate       TEXT,
  coast         TEXT,
  bbox          TEXT NOT NULL,              -- JSON [minlon, minlat, maxlon, maxlat]
  optical_regime TEXT,
  status        TEXT NOT NULL DEFAULT 'MONITORING',
  created_at    TEXT NOT NULL,
  created_by    TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS observations (
  id              TEXT PRIMARY KEY,         -- aoi|sensor|datetime|orbit
  aoi_id          TEXT NOT NULL REFERENCES aois(id),
  sensor          TEXT NOT NULL,            -- Sentinel-2 L2A, Sentinel-3 OLCI WFR, ...
  acquired_at     TEXT NOT NULL,
  scene_ids       TEXT NOT NULL,            -- JSON list
  processing      TEXT,                     -- JSON: baselines, level
  valid_fraction  REAL,
  water_px        INTEGER,
  cloud_fraction  REAL,
  stats           TEXT,                     -- JSON zone statistics
  created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_aoi_time ON observations(aoi_id, acquired_at);

CREATE TABLE IF NOT EXISTS models (
  id                        TEXT PRIMARY KEY,   -- e.g. triage-1.3.0
  task                      TEXT NOT NULL,      -- triage | quantify:<parameter>
  version                   TEXT NOT NULL,
  model_type                TEXT NOT NULL,      -- rules | logistic_l2 | ridge_log | ...
  created_at                TEXT NOT NULL,
  training_dataset_version  TEXT,
  validation_dataset_hash   TEXT,
  feature_set               TEXT NOT NULL,      -- JSON list
  params                    TEXT,               -- JSON
  artifact                  TEXT,               -- JSON coefficients / rule table
  status                    TEXT NOT NULL,      -- TRAINING CANDIDATE REJECTED STAGING PRODUCTION RETIRED
  parent_model              TEXT,
  notes                     TEXT,
  gate                      TEXT,               -- JSON gate report
  promoted_by               TEXT,
  promoted_at               TEXT
);
CREATE INDEX IF NOT EXISTS idx_models_task_status ON models(task, status);

CREATE TABLE IF NOT EXISTS model_metrics (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  model_id  TEXT NOT NULL REFERENCES models(id),
  split     TEXT NOT NULL,                  -- validation | cv | train
  subgroup  TEXT NOT NULL DEFAULT 'all',    -- all | aoi:<id> | source:<label source>
  metric    TEXT NOT NULL,
  value     REAL,
  ci_low    REAL,
  ci_high   REAL,
  n         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_metrics_model ON model_metrics(model_id);

CREATE TABLE IF NOT EXISTS incidents (
  id                     TEXT PRIMARY KEY,  -- BB-UAE-2026-001
  aoi_id                 TEXT NOT NULL,
  status                 TEXT NOT NULL,     -- MONITORING DETECTED UNDER_REVIEW FIELD_VALIDATION_REQUIRED CONFIRMED FALSE_POSITIVE RESOLVED
  detected_at            TEXT NOT NULL,
  observation_time       TEXT NOT NULL,
  event_type_hypothesis  TEXT NOT NULL,
  severity               REAL,
  confidence             REAL,
  priority               TEXT,
  model_id               TEXT,              -- model that raised it
  geometry               TEXT,              -- GeoJSON geometry
  centroid_lon           REAL,
  centroid_lat           REAL,
  area_km2               REAL,
  role                   TEXT NOT NULL DEFAULT 'operational', -- operational | negative_control | benchmark
  disposition            TEXT,
  payload                TEXT NOT NULL,     -- JSON evidence package (see pipeline/incidents.py)
  created_at             TEXT NOT NULL,
  updated_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);

CREATE TABLE IF NOT EXISTS predictions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id  TEXT NOT NULL REFERENCES incidents(id),
  model_id     TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  output       TEXT NOT NULL                -- JSON
);
CREATE INDEX IF NOT EXISTS idx_pred_incident ON predictions(incident_id);

CREATE TABLE IF NOT EXISTS reviews (
  id                   TEXT PRIMARY KEY,
  incident_id          TEXT NOT NULL REFERENCES incidents(id),
  reviewer             TEXT NOT NULL,
  created_at           TEXT NOT NULL,
  model_id             TEXT,
  previous_hypothesis  TEXT,
  decision             TEXT NOT NULL,       -- CONFIRM FALSE_POSITIVE RECLASSIFY NEEDS_FIELD_SAMPLE INSUFFICIENT_EVIDENCE
  new_hypothesis       TEXT,
  note                 TEXT,
  evidence_viewed      TEXT,                -- JSON list of evidence section keys
  status_before        TEXT NOT NULL,
  status_after         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_incident ON reviews(incident_id);

CREATE TABLE IF NOT EXISTS samples (
  id            TEXT PRIMARY KEY,           -- <incident>-S01
  incident_id   TEXT NOT NULL REFERENCES incidents(id),
  code          TEXT NOT NULL,              -- S01
  role          TEXT NOT NULL,              -- CORE EDGE BACKGROUND UNCERTAINTY ASSET_BOUNDARY
  lon           REAL NOT NULL,
  lat           REAL NOT NULL,
  status        TEXT NOT NULL,              -- PLANNED COLLECTED LAB_PENDING RESULT_RECEIVED REMOVED
  question      TEXT,
  analytes      TEXT,                       -- JSON list
  rationale     TEXT,
  planned_by    TEXT,
  planned_at    TEXT,
  collected_by  TEXT,
  collected_at  TEXT,
  updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_incident ON samples(incident_id);

CREATE TABLE IF NOT EXISTS measurements (
  id            TEXT PRIMARY KEY,
  incident_id   TEXT NOT NULL REFERENCES incidents(id),
  sample_id     TEXT REFERENCES samples(id),
  parameter     TEXT NOT NULL,              -- chlorophyll_a, turbidity, tss, temperature, salinity, ...
  value         REAL NOT NULL,
  unit          TEXT NOT NULL,
  method        TEXT,
  measured_at   TEXT,
  lab           TEXT,
  qc_flag       TEXT NOT NULL DEFAULT 'UNCHECKED',
  source        TEXT NOT NULL,              -- manual | lab_csv
  entered_by    TEXT NOT NULL,
  entered_at    TEXT NOT NULL,
  raw           TEXT
);
CREATE INDEX IF NOT EXISTS idx_meas_incident ON measurements(incident_id);

CREATE TABLE IF NOT EXISTS labels (
  id               TEXT PRIMARY KEY,
  task             TEXT NOT NULL,           -- triage | quantify:<parameter>
  incident_id      TEXT,
  aoi_id           TEXT,
  target           TEXT NOT NULL,           -- JSON: {"y": 1, "class": "BLOOM_LIKE"} or {"y": 4.2, "unit": "mg m-3"}
  features         TEXT NOT NULL,           -- JSON feature vector frozen at label time
  source           TEXT NOT NULL,           -- analyst_review | field_measurement | in_situ_archive | cross_sensor_reference
  source_ref       TEXT,                    -- review / measurement / record id
  weight           REAL NOT NULL DEFAULT 1.0,
  split            TEXT NOT NULL,           -- train | validation
  group_key        TEXT,                    -- spatial/temporal group for grouped validation
  created_at       TEXT NOT NULL,
  created_by       TEXT NOT NULL,
  superseded_by    TEXT
);
CREATE INDEX IF NOT EXISTS idx_labels_task ON labels(task, split);

CREATE TABLE IF NOT EXISTS training_jobs (
  id                  TEXT PRIMARY KEY,
  task                TEXT NOT NULL,
  requested_by        TEXT NOT NULL,
  created_at          TEXT NOT NULL,
  started_at          TEXT,
  finished_at         TEXT,
  status              TEXT NOT NULL,        -- QUEUED RUNNING SUCCEEDED FAILED
  dataset_version     TEXT,
  n_train             INTEGER,
  n_validation        INTEGER,
  candidate_model_id  TEXT,
  log                 TEXT,                 -- JSON list of steps
  error               TEXT
);

CREATE TABLE IF NOT EXISTS assets (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  type         TEXT NOT NULL,
  lon          REAL NOT NULL,
  lat          REAL NOT NULL,
  aoi_id       TEXT,
  sensitivity  REAL,
  source       TEXT NOT NULL,               -- osm:<element> | operator
  notes        TEXT,
  created_at   TEXT NOT NULL,
  created_by   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
  id           TEXT PRIMARY KEY,
  incident_id  TEXT,
  aoi_id       TEXT,
  level        TEXT NOT NULL,               -- INFO REVIEW_REQUIRED FIELD_REQUIRED
  message      TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  acknowledged_by TEXT,
  acknowledged_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  at           TEXT NOT NULL,
  actor        TEXT NOT NULL,
  action       TEXT NOT NULL,
  entity_type  TEXT NOT NULL,
  entity_id    TEXT NOT NULL,
  detail       TEXT,
  prev_hash    TEXT NOT NULL,
  hash         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
  key    TEXT PRIMARY KEY,
  value  TEXT NOT NULL
);
