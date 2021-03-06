# Marvin MONROE - a scheduling daemon

This package includes a relatively generic task scheduling daemon.

It is built to fulfill requirements of the European project MONROE, but
should be suitable in other types of distributed network with a central
controller.

## Installation

> python setup.py install

Copy and adjust the configuration files marvind.conf (on the node)
or marvinctld.conf (on the scheduling server).

## marvinctld

When started

  * synchronizes with an inventory REST API to retrieve node status.
  * opens the following control ports:
    * REST API

All state changes are stored in a SQLite database on disk, and will be
recovered on restart.

### REST endpoints

    routes = (
      '/version'          - protocol version number (GET)
      '/resources(|/.*)'   - node, type and status (GET, PUT)
      '/users(|/.*)'       - users (GET, PUT, POST, DELETE)
      '/experiments(|/.*)' - task definitions (GET, POST, DELETE)
      '/schedules(|/.*)'   - scheduled tasks (GET, PUT)
      '/backend(/.*)'     - backend actions (various)
    )

#### Terminology:

  * resource   (a node, with a node/resource id)
  * user       (a user, with a user id)
  * experiment (the definition of a task to be run on one or more nodes, with id)
  * schedules  (the n:m mapping of experiments to nodes, with id, start and stop time)

#### Access levels:
'#' is a placeholder for a node id, task id, user id, iccid or scheduling id

for everyone:

  * GET version
  * GET backend/auth [verify SSL certificate]
  * GET backend/activity [show activity statistics]
  * GET backend/pubkeys [show public keys for running experiments]

for all authenticated clients:

  * GET resources
  * GET resources/#
  * GET resources/#/schedules
  * GET resources/#/experiments
  * GET resources/#/all
  * GET resources/#/journals
  * GET resources/#(nodeid)/journals/#(iccid)
  * GET users
  * GET users/#
  * GET users/#/schedules
  * GET users/#/experiments
  * GET users/#/journals
  * GET schedules?start=...&stop=...
  * GET schedules/#
  * GET schedules/find?nodecount=...&duration=...&start=...&nodetypes=...&nodes=...&pair=0|1
  * GET experiments
  * GET experiments/#             (returns experiment summary)
  * GET experiments/#/schedules   (returns detailed task status)
  * GET experiments/#/schedules/#

only for users (role: user)

  * POST experiments      (+experiment and scheduling parameters)
  * DELETE experiments/#  (delete an experiment and its schedule entries)
  * PUT experiments/#/#  [name=...]   (merge tasks from expid2 into expid1)

only for administrators (role: admin)

  * PUT  resources/#      type=tag:value[,tag:value,...]   (set nodetypes for filtering, overriding inventory)
  * PUT  resources/#      pair=#|delete                    (associate with another node as head/tail pair)
  * PUT  resources/#      iccid=&quota=                    (update interface quotas)
  * POST users            role=&name=&project=&ssl=        (create new users)
  * PUT  users/#          data=&time=&storage=             (update user quotas)
  * PUT  users/#          ssl=                             (update user ssl fingerprint)
  * DELETE users/#

only for a node with the given id # (role: node)

  * GET resources/#/schedules
  * PUT resources/#       [send heartbeat]
  * PUT schedules/#       [status code or JSON traffic report, see below.]

To update the node status, send the schedules/# PUT request with the following
fields:

  * schedid    - the scheduling ID of the task
  * status     - the status code, see below. (text)

Valid status codes are:

  * defined    - experiment is created in the scheduler
  * deployed   - node has deployed the experiment, scheduled a start time
  * started    - node has successfully started the experiment
  * restarted  - node has restarted the experiment after a node failure
  * delayed    - the deployment or start failed for a temporary reason.

These status codes are final and cannot be overridden:

  * stopped    - experiment stopped by scheduler
  * finished   - experiment completed, exited before being stopped
  * failed     - scheduling process failed
  * canceled   - user deleted experiment, task not deployed (but some were)
  * aborted    - user deleted experiment, task had been deployed

All status codes can be suffixed with ; and a reason (free text).

A valid traffic report is a JSON dictionary, and will overwrite the last
traffic report for the same scheduling ID. To send a traffic report, provide
the keys

  * schedid    - the scheduling ID of the task
  * report     - the traffic report as JSON dictionary.

The traffic report may contain arbitrary keys and values. It is planned to
recognize the following keys for quota reimbursements:

  * results    - bytes of result data transferred (via ssh + compression)
  * deployment - bytes of deployment data transferred (via https + compression)
  * [iccid]    - traffic transferred over an interface with the given ICCID.

Quota reimbursements are not implemented yet.

## Experiment and scheduling parameters:

The following parameters are used to schedule an experiment:

  * taskname  - an arbitrary identifier
  * start     - a UNIX time stamp, the start time (may be left 0 to indicate ASAP, -1 for LPQ)
  * stop      - a UNIX time stamp, the stop time **OR**
  * duration  - runtime of the experiment in seconds.
  * nodecount - the number of nodes to allocate this experiment to
  * nodetypes - the type filter of required and rejected node types,
                Valid queries include a tag and value, e.g. type:testing
                Valid tags are [model, project, status, type]
                Supports the operators OR(|), NOT(-) and AND(,) in this strict order of precedence.
                EXAMPLE: type:testing,country:es,-model:apu2d
  * script    - the experiment to execute, in the form of one or two docker pull URL, pipe-separated
                If two URL are provided, the scheduler will select associated node pairs and
                send the first URL to the node head, the second URL to the node tail.

ASAP scheduling: The scheduler selects the next available time slot after now.

LPQ scheduling: Low priority, queued. No time slot is assigned to the task. Instead, whenever
the node is sending a heartbeat and has available capacity, this task will be immediately executed.
LPQ scheduling will ignore recurrence parameters.

These are defined as scheduling options, interpreted by the scheduling server:

* options   - (optional) additional scheduling options.
    * nodes         - a specific list of node ids to select for scheduling
    * shared        - (default 0) 1 if this is a passive measurement experiment
    * recurrence    - (default 0) 'simple' for a basic recurrence model
    * period        - experiment will be repeated with this interval, in seconds
    * until         - UNIX timestamp, experiment will not be repeated after this date
    * restart     - (default 1) 0 if the experiment is not to be restarted if the node is rebooted
    * storage     - (default 1GB - container size?) storage quota for experiment results.
    * traffic     - traffic quota, per interface, bidirectional
    * ssh         - if provided (any value), the scheduler generates a public/private key pair stored in the options ssh.public and _ssh.private

Options that are required to be known during deployment are passed to the node as
deployment parameters.

The options parameter should be x-www-form-urlencoded, that is separated by ampersands
and in the form key=value, or in the form of a JSON object.

#### Container parameters:

All options (including user provided keys that are not handled by the
scheduler) are passed to the container in the /monroe/config file.
Options prefixed with an underscore _ are hidden in the public user
interface and API, and only passed to the container.

#### Authentication:

This is based on client certificates. The server is supposed to be run behind a
HTTPS server (e.g. nginx) which will take care of verifying the certificate.
That server will then have to set the header HTTP_VERIFIED to NONE or SUCCESS
and the header HTTP_SSL_FINGERPRINT to the client certificate fingerprint

example nginx configuration:

    proxy_set_header  VERIFIED         $ssl_client_verify;
    proxy_set_header  SSL_FINGERPRINT  $ssl_client_fingerprint;

in order to use a web browser-based client, you also need to enable CORS headers, e.g.:

    add_header 'Access-Control-Allow-Origin' "$http_origin" always;
    add_header 'Access-Control-Allow-Credentials' 'true' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS, PUT, DELETE' always;
    add_header 'Access-Control-Allow-Headers' 'DNT,X-CustomHeader,Keep-Alive,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type' always;

    if ($request_method = 'OPTIONS') {
        add_header 'Content-Length' 0 always;
        return 204;
    }

To create an authority, server or client keys, follow this guide:
http://dst.lbl.gov/~boverhof/openssl_certs.html

### Configuration

An example configuration is provided in ./files/etc/marvinctld.conf

The files follow the YAML (http://yaml.org) syntax. The required keys are subject to change, but all keys should be mentioned in the example files.

## marvind

When started

  * attempts to synchronize state with a marvinctld node controller.

For every new task assigned:

  * If it seen for the first time, downloads the task and runs a deployment
    hook. The start hook is then added to the systems atq (cron at queue) to
    be run at the scheduled time.
  * A stop hook is added to the atq at the scheduled stop time.

Task status is reported back to the ctld.

### Configuration

An example configuration is provided in ./files/etc/marvind.conf

# EXAMPLE setup

On the scheduling server:

  * Copy marvinctld.conf to /etc/marvinctld.conf and adjust address and port
    numbers. Make sure these are only available on the local machine.
  * Run marvinctld
  * Configure nginx to act as HTTPS proxy, and expose the HTTPS ports to
    the outside, e.g. measurement nodes.

On the measurement node:

  * Make sure the node is registered in the MONROE inventory (see packages
    metadata-exporter and autotunnel)
  * Generate and install client certificates
  * Copy marvind.conf to /etc/marvind.conf and adjust addresses, port numbers
    and certificate locations.
  * Run marvind

From anywhere:

  * Send REST commands to http://marvinctld-server:port/, e.g.

POST /user
Parameters: name, ssl, role

Creates user 'name' authenticated by the given ssl fingerprint and one
of the valid roles (user, node, admin)

POST /experiment
Parameters:

  * user      - user running the task
  * taskname  - arbitrary identifier
  * start     - unix timestamp, start time of the task
  * stop      - unix timestamp, stop time of the task
  * nodecount - number of nodes to assign this task to
  * nodetype  - type of nodes to assign this task to
  * script    - file to be downloaded, and made available to the deployment hook

# REST Return values:

  * 200 Ok          - Ok.
  * 201 Created     - Ok, a resource was created.
  * 400 Bad Request - Parameters are missing.
  * 404 Not Found   - The request path is unknown.
  * 409 Conflict    - Resource reservation failed + Reason.


