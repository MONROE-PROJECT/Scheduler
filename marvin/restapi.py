#!/usr/bin/env python

"""
Marvinctld (MONROE scheduler) REST API.
Copyright (c) 2015 Celerway, Thomas Hirsch <thomas.hirsch@celerway.com>.
All rights reserved.

Allows to schedule tasks through a REST API interface.
"""

import logging
from logging.handlers import WatchedFileHandler
import configuration

import simplejson as json
import time
import web
import scheduler

config = configuration.select('marvinctld')

log = logging.getLogger('REST API')
log.addHandler(WatchedFileHandler(config['log']['file']))
log.setLevel(config['log']['level'])


API_VERSION = "1.0"
# NOTE: major versions will be reflected in the URL
#       minor versions will increase after first deployment, and should not
#       break compatibility with prior minor versions.

PREFETCH_COUNT = 3         # number of schedules returned to URLs (default)
PREFETCH_LIMIT = 24 * 3600 # maximum prefetch time window (fixed)


def dumps(data):
    return json.dumps(data, sort_keys=True, indent='  ')


def error(message, code=None, extra={}):
    if code is not None:
        extra["code"] = code
    return dumps(dict({"message": message}, **extra))


def set_headers(web):
    web.header('Content-type', 'application/json')
    web.header('API-Version', API_VERSION)


class ApiServer(web.application):
    def run(self, port=config['rest_api']['port'], *middleware):
        fn = self.wsgifunc(*middleware)
        return web.httpserver.runsimple(fn, (config['rest_api']['address'],
                                             config['rest_api']['port']))


class Version:
    def GET(self):
        set_headers(web)
        return dumps(API_VERSION)


# RESOURCE ##################################################################
class Resource:

    def GET(self, nodeid):
        role = rest_api.get_role(web.ctx)
        if role is None:
            web.ctx.status = '401 Unauthorized'
            return error("Please present a valid SSL client certificate "
                         "to access this information")

        data = None
        if nodeid in ["", "/"]:
            data = rest_api.scheduler.get_nodes()
        else:
            path = nodeid.split("/")
            if len(path) > 2 and path[2] == 'schedules':
                data = rest_api.scheduler.get_schedule(nodeid=path[1])
            elif len(path) > 2 and path[2] == 'journals':
                if len(path) > 3:
                  data = rest_api.scheduler.get_quota_journal(iccid=path[3])
                else:
                  data = rest_api.scheduler.get_quota_journal(nodeid=path[1])
            elif len(path) > 2 and path[2] == 'all':
                data = {
                  'schedules': rest_api.scheduler.get_schedule(nodeid=path[1]),
                  'experiments':
                  rest_api.scheduler.get_experiments(nodeid=path[1])
                }
            else:
                data = rest_api.scheduler.get_nodes(nodeid=path[1])

        if data is None:
            web.ctx.status = '404 Not Found'
            return error("Could not find resource with this id.")

        set_headers(web)
        return dumps(data)

    def PUT(self, nodeid):
        if nodeid in ["", "/"]:
            web.ctx.status = '404 Not Found'
            return error("Updating collection not allowed.")
        nodeid = nodeid[1:]
        data = web.input()

        uid, role, name = rest_api.get_user(web.ctx)
        if "pair" in data.keys():
            if role == scheduler.ROLE_ADMIN:
                tail = data['pair']
                if tail == 'delete':
                    tail = None
                result = rest_api.scheduler.set_node_pair(nodeid, tail)
                if result is 1:
                    return error("Node pair set.")
                else:
                    web.ctx.status = '404 Not Found'
                    return error(result)
            else:
                web.ctx.status = '401 Unauthorized'
                return error("You'd have to be an admin to do that")

        if "type" in data.keys():
            if role == scheduler.ROLE_ADMIN:
                result = rest_api.scheduler.set_node_types(nodeid,
                                                           data['type'])
                if result is True:
                    return error("Node type set.")
                else:
                    web.ctx.status = '404 Not Found'
                    return error(result)
            else:
                web.ctx.status = '401 Unauthorized'
                return error("You'd have to be an admin to do that")

        if "quota" in data.keys():
            if role == scheduler.ROLE_ADMIN:
                iccid  = data.keys.get('iccid')
                options = {} # reserved for future use, quota type etc.
                value  = data.keys.get('value')
                result = rest_api.scheduler.set_interface_quota(nodeid, iccid, options, value)
                if result > 0:
                    return error("Updated.")
                else:
                    web.ctx.status = '404 Not Found'
                    return error("User ID not found")
            else:
                web.ctx.status = '401 Unauthorized'
                return error("You'd have to be an admin to do that")


        if role == scheduler.ROLE_NODE:
            if name != ("Node %s" % nodeid):
                web.ctx.status = ''
                return error("Wrong user to update this status. (%s)" % name)
            now = int(time.time())
            maintenance = data.get('maintenance',0)
            interfaces=json.loads(data.get('interfaces','[]'))
            rest_api.scheduler.update_node_status(nodeid, now, maintenance, interfaces)

            limit = int(data.get("limit", PREFETCH_COUNT))
            data = rest_api.scheduler.get_schedule(nodeid=nodeid, limit=limit, interfaces=True,
                                                   stop=now + PREFETCH_LIMIT, private=True,
                                                   heartbeat=True)
            for task in data.get('tasks',[]):
                if task.get('status') == 'defined':
                    rest_api.scheduler.set_status(task.get('id'), 'requested')
            return dumps(data)
        else:
            web.ctx.status = '400 Bad Request'
            return error("Parameters missing: type\nIf you are a node, "
                         "you were identified as SSL_ID %s." %
                         web.ctx.env.get('HTTP_SSL_FINGERPRINT', None))

# SCHEDULE ##################################################################


class Schedule:

    def GET(self, resource):
        role = rest_api.get_role(web.ctx)
        if role is None:
            web.ctx.status = '401 Unauthorized'
            return error("Please present a valid SSL client certificate to"
                         "access this information")

        params = web.input()
        if resource in ["", "/"]:
            tasks = rest_api.scheduler.get_schedule(past=False, compact=True)
        elif resource == "/find":
            nodes = params.get('nodes', None)
            selection = nodes.split(",") if nodes is not None else None
            if selection is None:
                nodetypes = params.get('nodetypes','')
                new_nodes = 'model:apu2' in nodetypes
                ifCount = int(params.get('interfaceCount', 1))
                tail = new_nodes and (ifCount != 2)
                head = new_nodes and (ifCount >= 2)
                pair = new_nodes and (ifCount >= 3)
            else:
                nodetypes = ""
                tail = True
                head = True
                pair = False
            tasks, errmsg = rest_api.scheduler.find_slot(
                        nodecount=params.get('nodecount', 1),
                        duration=params.get('duration', 1),
                        start=params.get('start', 0),
                        nodetypes=nodetypes,
                        results=params.get('results', 1),
                        nodes=selection,
                        head=head, tail=tail, pair=pair
                    )
            if tasks is None:
                web.ctx.status = '409 Conflict'
                return error(errmsg)
        else:
            schedid = resource[1:]
            tasks = rest_api.scheduler.get_schedule(schedid=schedid, past=True)
            if tasks is not None and len(tasks)>0:
                tasks = tasks[0]

        if tasks is None:
            web.ctx.status = '404 Not Found'
            return error("Could not find schedule entry with this id.")

        set_headers(web)
        return dumps(tasks)

    def PUT(self, schedid):
        uid, role, name = rest_api.get_user(web.ctx)
        if role != scheduler.ROLE_NODE:
            web.ctx.status = '401 Unauthorized'
            return error("You'd have to be a node to do that")
        params = None
        try:
            params = json.loads(web.data().strip())
        except:
            pass
        if params is None or not params:
            params = web.input()
        if schedid in ["", "/"]:
            web.ctx.status = '400 Bad Request'
            return error("Scheduling id missing.")
        schedid = schedid[1:]
        tasks = rest_api.scheduler.get_schedule(schedid=schedid, past=True, lpq=True)
        if len(tasks) == 0:
            web.ctx.status = '404 Not Found'
            return error("Could not find schedule entry with this id.")
        nodeid = tasks[0]['nodeid']
        if name != ("Node %i" % nodeid):
            web.ctx.status = '401 Unauthorized'
            return error("Wrong user to updated this status (%s)" % name)
        if 'status' in params:
            status = params.get('status','').strip()
            code = status.split(";")[0]
            if code in scheduler.TASK_STATUS_CODES:
                result, errmsg = rest_api.scheduler.set_status(
                    schedid=schedid,
                    status=status)
                if result:
                    return error("Ok.")
                else:
                    web.ctx.status = '400 Bad request'
                    return error(errmsg)
            else:
                web.ctx.status = '400 Bad Request'
                return error("Unknown status code (%s)." % status)
        elif 'traffic' in params:
            try:
                traffic = json.loads(params.get('traffic',''))
            except:
                web.ctx.status = '400 Bad Request'
                return error("Count not parse JSON code for traffic parameter")
            result, errmsg = rest_api.scheduler.report_traffic(
                    schedid=schedid,
                    traffic=traffic)
            if result:
                return error("Ok.")
            else:
                web.ctx.status = '400 Bad request'
                return error(errmsg)
        else:
            web.ctx.status = '400 Bad Request'
            return error("Parameters missing (required: status, or traffic)")

# EXPERIMENT ################################################################


class Experiment:

    def GET(self, task):
        role = rest_api.get_role(web.ctx)
        if role is None:
            web.ctx.status = '401 Unauthorized'
            return error("Please present a valid SSL client certificate to "
                         "access this information")

        if task in ["", "/"]:
            params = web.input()
            showHidden = params.get("showHidden","0")=="1"
            tasks = rest_api.scheduler.get_experiments(archived=showHidden)
        else:
            path = task.split("/")
            expid = path[1]
            schedid = None
            if len(path)>2 and path[2] in ["schedule","schedules"]:
                if len(path)>3:
                    schedid=path[3]
                else:
                    schedid=-1
            tasks = rest_api.scheduler.get_experiments(expid=expid, schedid=schedid, archived=True)
            if tasks is not None:
                tasks = tasks[0]

        if tasks is None:
            web.ctx.status = '404 Not Found'
            return error("Could not find experiment with this id.")

        set_headers(web)
        return dumps(tasks)

    def POST(self, ignored):
        user, role, name = rest_api.get_user(web.ctx)
        if role != scheduler.ROLE_USER:
            web.ctx.status = '401 Unauthorized'
            return error("You'd have to be a user to do that.")

        params = {}
        try:
            params = json.loads(web.data())
        except:
            params = web.input()
        required = ['name', 'nodecount', 'nodetypes', 'script']
        optional = ['options', 'start', 'stop', 'duration']
        if set(required).issubset(set(params.keys())):
            start = params.get('start', 0)
            stop = params.get('stop', 0)
            duration = params.get('duration', stop-start)
            scripts = params.get('script','').split('|')
            options = params.get('options','')
            selection = None
            try:
                selection = json.loads(options).get('nodes') or None
            except:
                pass

            if selection is None:
                nodetypes = params.get('nodetypes','')
                new_nodes = 'model:apu2' in nodetypes
                ifCount = params.get('interfaceCount', 1)
                tail = new_nodes and (ifCount != 2)
                head = new_nodes and (ifCount >= 2)
                pair = new_nodes and (ifCount >= 3)
            else:
                nodetypes = ''
                head = True
                tail = True
                pair = False

            alloc, errmsg, extra = rest_api.scheduler.allocate(
                                   user, params['name'],
                                   start, duration,
                                   params['nodecount'], nodetypes,
                                   scripts, params.get('options', ''),
                                   head=head, tail=tail, pair=pair)
            if alloc is not None:
                web.header('Location', "/schedules/%i" % alloc)
                web.ctx.status = '201 Created'
                return error("Allocated task %s." % alloc, extra=extra)
            else:
                web.ctx.status = '409 Conflict'
                return error("Could not allocate. %s" % errmsg, extra=extra)
        else:
            web.ctx.status = '400 Bad Request'
            return error("Parameters missing "
                         "(required: %s | optional: %s, provided: %s)."
                         % (str(required), str(optional), str(params.keys())))

    def DELETE(self, path):
        uid, role, name = rest_api.get_user(web.ctx)
        if role not in [scheduler.ROLE_USER, scheduler.ROLE_ADMIN]:
            web.ctx.status = '401 Unauthorized'
            return error("You'd have to be a user or admin to do that")

        if path in ["", "/"]:
            web.ctx.status = '400 Bad Request'
            return error("Experiment id missing.")
        expid=path.split("/")[1]
        experiments = rest_api.scheduler.get_experiments(expid=expid)
        if role != scheduler.ROLE_ADMIN and \
           experiments[0]['ownerid'] != uid:
            web.ctx.status = '401 Unauthorized'
            return error("Only admins and user %i can do this" % experiments[0]['ownerid'])
        else:
            result, message, extra = \
                rest_api.scheduler.delete_experiment(expid)
            log.debug("Delete result: %s rows deleted" % result)
            if result > 0:
                return error(message, extra=extra)
            else:
                web.ctx.status = '404 Not Found'
                return error("Could not find experiment id.")

    def PUT(self, path):
        uid, role, name = rest_api.get_user(web.ctx)
        if role not in [scheduler.ROLE_USER, scheduler.ROLE_ADMIN]:
            web.ctx.status = '401 Unauthorized'
            return error("You'd have to be a user to do that")
        if path in ["", "/"]:
            web.ctx.status = '400 Bad Request'
            return error("Experiment id missing.")
        path = path.split("/")
        if len(path) < 2:
            web.ctx.status = '400 Bad Request'
            return error("Second experiment id missing.")
        expid_into=path[1]
        expid2=path[2]
        try:
            params = json.loads(web.data())
        except:
            params = web.input()

        exp_into = rest_api.scheduler.get_experiments(expid=expid_into)
        exp2 = rest_api.scheduler.get_experiments(expid=expid2)
        if exp_into is None or exp2 is None:
            web.ctx.status = '404 Not found'
            return error("Experiment does not exist.")
        if (exp_into[0]['ownerid'] != uid) or (exp2[0]['ownerid'] != uid):
            web.ctx.status = '401 Unauthorized'
            return error("Only user %i can do this" % uid)
        else:
            name=params.get('name')
            count = rest_api.scheduler.merge_experiments(
                        expid_into, expid2, name)
            return error("Merged %s tasks from experiment %s into %s" % (count, expid2, expid_into))


# USER ######################################################################


class User:
    def GET(self, userid):
        role = rest_api.get_role(web.ctx)
        if role is None:
            web.ctx.status = '401 Unauthorized'
            return error("Please present a valid SSL client certificate to "
                         "access this information")

        data = None
        log.debug(userid)
        if userid in ["", "/"]:
            data = rest_api.scheduler.get_users()
        else:
            path = userid.split("/")
            if len(path) > 2 and path[2] == 'schedules':
                data = rest_api.scheduler.get_schedule(userid=path[1])
            elif len(path) > 2 and path[2] == 'experiments':
                params = web.input()
                showHidden = params.get("showHidden","0")=="1"
                data = rest_api.scheduler.get_experiments(userid=path[1], archived=showHidden)
            elif len(path) > 2 and path[2] == 'journals':
                data = rest_api.scheduler.get_quota_journal(userid=path[1])
            else:
                data = rest_api.scheduler.get_users(path[1])

        if data is None:
            web.ctx.status = '404 Not Found'
            return error("Could not find user with this id.")

        set_headers(web)
        return dumps(data)

    def PUT(self, userid):
          if userid in ["", "/"]:
              web.ctx.status = '404 Not Found'
              return error("Updating collection not allowed.")
          userid = userid[1:]
          data = web.input()

          uid, role, name = rest_api.get_user(web.ctx)
          if "time" in data.keys() or \
             "data" in data.keys() or \
             "storage" in data.keys():
              if role == scheduler.ROLE_ADMIN:
                  result = rest_api.scheduler.set_time_quota(userid, data.get('time')) \
                         + rest_api.scheduler.set_data_quota(userid, data.get('data')) \
                         + rest_api.scheduler.set_storage_quota(userid, data.get('storage'))
                  if result > 0:
                      return error("Updated.")
                  else:
                      web.ctx.status = '404 Not Found'
                      return error("Could not find user ID.")
              else:
                  web.ctx.status = '401 Unauthorized'
                  return error("You'd have to be an admin to do that")

    def POST(self, ignored):
        role = rest_api.get_role(web.ctx)
        if role != scheduler.ROLE_ADMIN:
            web.ctx.status = '401 Unauthorized'
            return error("You'd have to be an admin to do that (%s, %s)" %
                         (role, scheduler.ROLE_ADMIN))

        data = web.input()
        if "name" in data and "ssl" in data and "role" in data:
            userid, errmsg = rest_api.scheduler.create_user(
                data['name'].strip(), data['ssl'].strip(),
                data['role'].strip(), data.get('project','').strip())
            if userid is not None:
                web.ctx.status = '201 Created'
                web.header('Location', "/user/%i" % userid)
                return error("User %s created." % userid)
            else:
                web.ctx.status = '409 Conflict'
                return error(errmsg)
        else:
            web.ctx.status = '400 Bad Request'
            return error("Parameters missing (name, ssl, role), optional: project.")

    def DELETE(self, userid):
        role = rest_api.get_role(web.ctx)
        if role != scheduler.ROLE_ADMIN:
            web.ctx.status = '401 Unauthorized'
            return error("You'd have to be an admin to do that")

        if userid in ["", "/"]:
            web.ctx.status = '400 Bad Request'
            return error("Userid missing.")
        else:
            result = rest_api.scheduler.delete_user(userid[1:])
            log.debug("Delete result: %s" % result)
            if result is True:
                return error("Ok. Invalidated user certificate.")
            else:
                web.ctx.status = '404 Not Found'
                return error("Could not find user with that id.")

# BACKEND ###################################################################


class Backend:

    def GET(self, action):
        verified = web.ctx.env.get('HTTP_VERIFIED', None)
        fingerprint = web.ctx.env.get('HTTP_SSL_FINGERPRINT', '')
        user = rest_api.scheduler.get_users(ssl=fingerprint)

        if user is None or user[0]["role"] == scheduler.ROLE_INVALID:
            web.ctx.status = '401 Unauthorized'
            # send auth report anyway, or error on other paths

        if action == "/auth":

            if user is not None:
                user = user[0]

            return dumps({
                         "verified": verified,
                         "fingerprint": fingerprint,
                         "user": user
                         })

        elif action == "/activity":
            if user is None or user[0]["role"] == scheduler.ROLE_INVALID:
                return error("Not authorized.")
            else:
                activity = rest_api.scheduler.get_activity()
                return dumps(activity)
        elif action == "/pubkeys":
            keys = rest_api.scheduler.get_public_keys()
            return dumps(keys)
        else:
            web.ctx.status = '404 Not Found'
            return error("Unknown request")

    def PUT(self, action):
        role = rest_api.get_role(web.ctx)
        if role != scheduler.ROLE_ADMIN:
            web.ctx.status = '401 Unauthorized'
            return error("You'd have to be an admin to do that")
        if action == "/sync":
            rest_api.scheduler.sync_inventory()
        pass


routes = (
  '/version', 'Version',
  '/v1/resources(|/.*)', 'Resource',
  '/v1/users(|/.*)', 'User',
  '/v1/experiments(|/.*)', 'Experiment',
  '/v1/schedules(|/.*)', 'Schedule',
  '/v1/backend(/.*)', 'Backend',
)


class RestAPI:

    def __init__(self, scheduler):
        global rest_api
        self.scheduler = scheduler
        rest_api = self

    def stop(self):
        log.debug("Web server might take a second to shut down.")
        self.app.stop()

    def start(self):
        web.config.debug = True
        self.app = ApiServer(routes, globals())
        self.app.run()

    def get_fingerprint(self, ctx):
        fingerprint = ctx.env.get('HTTP_SSL_FINGERPRINT', None)
        return fingerprint

    def get_role(self, ctx):
        role = self.scheduler.get_role(self.get_fingerprint(web.ctx))
        return role

    def get_user(self, ctx):
        user = self.scheduler.get_users(ssl=self.get_fingerprint(web.ctx))
        if user is None or len(user) == 0:
            return None, None, None
        return user[0]['id'], user[0]['role'], user[0]['name']
