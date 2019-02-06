#!/usr/bin/env python

import hmac
import hashlib
import requests
import simplejson as json
import logging
from logging.handlers import WatchedFileHandler
import time
import configuration
import sys

config = configuration.select('marvinctld')
log = logging.getLogger('Inventory')
log.addHandler(WatchedFileHandler(config['log']['file']))
log.setLevel(config['log']['level'])

def n2_inventory_api(route, data=None, method='GET'):
    # STEP 1 - OAUTH API access
    oauth_data={
                        'audience': config['inventory']['auth0_resource_server'],
                        'grant_type': 'client_credentials',
                        'client_id': config['inventory']['auth0_client_id'],
                        'client_secret': config['inventory']['auth0_client_secret']
    }
    r = requests.post('https://' + config['inventory']['auth0_domain'] + '/oauth/token',
                      headers={'cache-control': 'no-cache', 'content-type': 'application/json'},
                      json=oauth_data)
    result = r.json()
    token = result['access_token']

    r = None
    if (method=='GET'):
      r = requests.get('https://' + config['inventory']['url'] + route,
                       headers={'Authorization': 'Bearer '+token}, json=data)

    try:
      result = r.json()
      log.debug("Reply: %s" % json.dumps(result))
      return result
    except:
      log.error("Could not authenticate with inventory.")
      print r.status_code
      print r.text
      return None
