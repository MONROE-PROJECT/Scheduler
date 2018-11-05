PRAGMA wal_checkpoint(TRUNCATE);

CREATE TABLE IF NOT EXISTS deployment_options (id INTEGER PRIMARY KEY ASC, json TEXT UNIQUE);

CREATE TABLE IF NOT EXISTS schedule_new (id TEXT PRIMARY KEY ASC,
    nodeid INTEGER, expid INTEGER, start INTEGER, stop INTEGER,
    status TEXT NOT NULL, shared INTEGER, deployment_options INT,
    FOREIGN KEY (nodeid) REFERENCES nodes(id),
    FOREIGN KEY (deployment_options) REFERENCES deployment_options(id),
    FOREIGN KEY (expid) REFERENCES experiments(id));

INSERT INTO deployment_options SELECT DISTINCT NULL, deployment_options FROM schedule;

INSERT INTO schedule_new SELECT s.id, nodeid, expid, start, stop, status, shared, o.id FROM schedule s, deployment_options o WHERE s.deployment_options = o.json;

DROP TABLE schedule;

ALTER TABLE schedule_new RENAME TO schedule;

VACUUM;

ANALYZE;

PRAGMA wal_checkpoint(TRUNCATE);
