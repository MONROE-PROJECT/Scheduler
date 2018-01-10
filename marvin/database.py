DB_TABLES = [ "nodes", "node_type", "node_interface", "owners",
                        "experiments", "schedule", "deployment_options",
                       "quota_owner_time", "quota_owner_data",
                       "quota_owner_storage", "quota_journal",
                       "traffic_reports", "node_pair"
            ]

DB_STRUCTURE = """
CREATE TABLE IF NOT EXISTS nodes (id INTEGER PRIMARY KEY ASC,
    hostname TEXT NOT NULL, status TEXT, heartbeat INTEGER);
CREATE TABLE IF NOT EXISTS node_type (nodeid INTEGER NOT NULL,
    tag TEXT NOT NULL, type TEXT NOT NULL, volatile INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (nodeid) REFERENCES nodes(id),
    PRIMARY KEY (nodeid, tag));
CREATE TABLE IF NOT EXISTS node_pair (headid INTEGER NOT NULL,
    tailid INTEGER NOT NULL,
    FOREIGN KEY (headid) REFERENCES nodes(id),
    FOREIGN KEY (tailid) REFERENCES nodes(id));
CREATE TABLE IF NOT EXISTS node_interface (nodeid INTEGER NOT NULL,
    imei TEXT NOT NULL, mccmnc TEXT NOT NULL,
    operator TEXT NOT NULL, iccid TEXT NOT NULL,
    quota_current INTEGER NOT NULL,
    quota_reset_value INTEGER, quota_type INTEGER NOT NULL,
    quota_reset_date  INTEGER, quota_last_reset INTEGER NOT NULL,
    status TEXT NOT NULL, heartbeat INTEGER, opname TEXT,
    PRIMARY KEY (nodeid, imei, iccid));
CREATE TABLE IF NOT EXISTS owners (id INTEGER PRIMARY KEY ASC,
    name TEXT NOT NULL, ssl_id TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL, project TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS k_owners ON owners(name, project);
CREATE TABLE IF NOT EXISTS quota_owner_time (ownerid INTEGER PRIMARY KEY,
    current INTEGER NOT NULL, reset_value INTEGER NOT NULL,
    reset_date INTEGER NOT NULL, last_reset INTEGER,
    FOREIGN KEY (ownerid) REFERENCES owners(id));
CREATE TABLE IF NOT EXISTS quota_owner_data (ownerid INTEGER PRIMARY KEY,
    current INTEGER NOT NULL, reset_value INTEGER NOT NULL,
    reset_date INTEGER NOT NULL, last_reset INTEGER,
    FOREIGN KEY (ownerid) REFERENCES owners(id));
CREATE TABLE IF NOT EXISTS quota_owner_storage (ownerid INTEGER PRIMARY KEY,
    current INTEGER NOT NULL, reset_value INTEGER NOT NULL,
    reset_date INTEGER NOT NULL, last_reset INTEGER,
    FOREIGN KEY (ownerid) REFERENCES owners(id));
CREATE TABLE IF NOT EXISTS experiments (id INTEGER PRIMARY KEY ASC,
    name TEXT NOT NULL, ownerid INTEGER NOT NULL, type TEXT NOT NULL,
    script TEXT NOT NULL, start INTEGER NOT NULL, stop INTEGER NOT NULL,
    recurring_until INTEGER NOT NULL, options TEXT,
    status TEXT,
    FOREIGN KEY (ownerid) REFERENCES owners(id));
CREATE TABLE IF NOT EXISTS deployment_options (id INTEGER PRIMARY KEY ASC,
    json TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS schedule (id TEXT PRIMARY KEY ASC,
    nodeid INTEGER, expid INTEGER, start INTEGER, stop INTEGER,
    status TEXT NOT NULL, shared INTEGER, deployment_options INT,
    FOREIGN KEY (nodeid) REFERENCES nodes(id),
    FOREIGN KEY (deployment_options) REFERENCES deployment_options(id),
    FOREIGN KEY (expid) REFERENCES experiments(id));
CREATE TABLE IF NOT EXISTS traffic_reports (schedid TEXT,
    meter TEXT NOT NULL, value INTEGER NOT NULL, refunded INT default 0,
    FOREIGN KEY (schedid) REFERENCES schedule(id));
CREATE UNIQUE INDEX IF NOT EXISTS k_all ON traffic_reports(schedid, meter);
CREATE INDEX IF NOT EXISTS k_iccid      ON node_interface(iccid);
CREATE TABLE IF NOT EXISTS quota_journal (timestamp INTEGER,
    quota TEXT NOT NULL, ownerid INTEGER, iccid TEXT,
    new_value INTEGER NOT NULL,
    reason TEXT NOT NULL,
    FOREIGN KEY (ownerid) REFERENCES owners(id),
    FOREIGN KEY (iccid) REFERENCES node_interface(iccid));
CREATE TABLE IF NOT EXISTS key_pairs (
    private TEXT NOT NULL, public TEXT NOT NULL,
    expires INTEGER NOT NULL);

CREATE INDEX IF NOT EXISTS k_status     ON nodes(status);
CREATE INDEX IF NOT EXISTS k_heartbeat  ON nodes(heartbeat);
CREATE INDEX IF NOT EXISTS k_type       ON node_type(type);
CREATE INDEX IF NOT EXISTS k_ssl_id     ON owners(ssl_id);
CREATE INDEX IF NOT EXISTS k_recurring  ON experiments(recurring_until);
CREATE INDEX IF NOT EXISTS k_start      ON schedule(start);
CREATE INDEX IF NOT EXISTS k_stop       ON schedule(stop);
CREATE INDEX IF NOT EXISTS k_expid      ON schedule(expid);
CREATE INDEX IF NOT EXISTS k_times      ON quota_journal(timestamp);
CREATE INDEX IF NOT EXISTS k_expires    ON key_pairs(expires);

"""
