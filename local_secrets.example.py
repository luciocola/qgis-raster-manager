# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
local_secrets.example.py — Template for local credentials.

Copy this file to  local_secrets.py  (same directory) and fill in
your values.  local_secrets.py is listed in .gitignore and will
never be committed or published.
"""

# DJI Developer App Key
# Required to process DJI drone imagery.  Register a developer account and
# create an application at https://developer.dji.com/user/apps  to receive
# your App Key.  Without this key the DJI Drone tab will show a warning
# before scanning or processing images.
DJI_APP_KEY = ''                # e.g. 'a1b2c3d4e5f6...'

# NodeODM / WebODM cloud processing
NODEODM_URL = 'http://localhost:3000'
NODEODM_API_TOKEN = ''          # leave empty for local NodeODM

# IPFS Kubo HTTP API
IPFS_API = '/ip4/127.0.0.1/tcp/5001'

# MQTT streaming broker (OGC Connected Systems)
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883
MQTT_TOPIC = ''                 # auto-filled from deployment if empty
MQTT_USERNAME = ''              # leave empty if broker has no auth
MQTT_PASSWORD = ''              # leave empty if broker has no auth
