import contextlib
import getpass
import logging
import subprocess
import sys

from dbus import SystemBus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
import openvpn3
import requests


MINOR_MAP = {
    2: 'Config parsed',
    6: 'Connecting',
    7: 'Connected',
    8: 'Disconnecting',
    9: 'Disconnected',
    11: 'Authentication failed',
    12: 'Reconnecting',
    16: 'Connecion done',
}


def status_change_handler(status_major: int, status_minor: int, message: str):
    if status_major != 2 or status_minor not in MINOR_MAP:
        # For status_major values consult https://codeberg.org/OpenVPN/openvpn3-linux/src/commit/fe2645567c9875509d8c3c3d88b22c4939779f8c/src/dbus/constants.hpp#L45
        # For status_minor values consult https://codeberg.org/OpenVPN/openvpn3-linux/src/commit/fe2645567c9875509d8c3c3d88b22c4939779f8c/src/dbus/constants.hpp#L90
        logging.warning(f'Status Change: {status_major}, {status_minor}, {message}.')
    else:
        if minor_message := MINOR_MAP[status_minor]:
           logging.info(f'Status Change: {minor_message}.')
        if status_minor in [9, 11]:
            start_new_session()


def attention_required_handler(attention_type: int, attention_group: int, message: str):
    logging.warning(f'Attention Required: {attention_type}, {attention_group}, {message}')


session: openvpn3.Session = None


def start_new_session():
    global session
    disconnect_session()
    session = session_manager.NewTunnel(configuration)
    session.StatusChangeCallback(status_change_handler)
    session.AttentionRequiredCallback(attention_required_handler)
    user_input_slots = session.FetchUserInputSlots()
    for user_input_slot in user_input_slots:
        if user_input_slot.GetVariableName() == 'username':
            user_input_slot.ProvideInput(credentials['username'])
        elif user_input_slot.GetVariableName() == 'password':
            user_input_slot.ProvideInput(credentials['password'])
        else:
            completed_process = subprocess.run(('oathtool', '--totp', '-d6', '-b', credentials['secret']), stdout=subprocess.PIPE)
            user_input_slot.ProvideInput(completed_process.stdout)
    session.Connect()


def disconnect_session():
    global session
    if session:
        session.Disconnect()
        session = None
        logging.info(f'{MINOR_MAP[9]}.')


def read_credentials():
    credentials = {}
    credentials_path = sys.argv[1]
    with open(credentials_path, encoding='utf8') as credentials_file:
        while line := credentials_file.readline():
            if line[-1] == '\n':
                line = line[:-1]
            key, value = line.split('=')
            credentials[key] = value
    return credentials


BITWARDEN_BASE_URL = 'http://localhost:8087'


def update_credentials_from_bitwarden(credentials):
    if 'username-item' not in credentials and 'secret-item' not in credentials:
        return
    requests.post(f'{BITWARDEN_BASE_URL}/sync')
    r = requests.get(f'{BITWARDEN_BASE_URL}/status')
    r.raise_for_status()
    if r.json()['data']['template']['status'] == 'locked':
        password = getpass.getpass('Bitwarden master password: ')
        requests.post(f'{BITWARDEN_BASE_URL}/unlock', json={'password': password}).raise_for_status()
    if 'username-item' in credentials:
        item = find_item(credentials['username-item'])
        credentials['username'] = item['login']['username']
        credentials['password'] = item['login']['password']
    if 'secret-item' in credentials:
        credentials['secret'] = find_item(credentials['secret-item'])['login']['totp']


def find_item(item_name: str):
    r = requests.get(f'{BITWARDEN_BASE_URL}/list/object/items', params={'search': item_name})
    r.raise_for_status()
    for item in r.json()['data']['data']:
        if item['name'] == item_name:
            return item


credentials = read_credentials()
logging.basicConfig(format=f'%(asctime)s:{credentials["config"]}:%(levelname)s:%(message)s', level=logging.INFO)
update_credentials_from_bitwarden(credentials)
DBusGMainLoop(set_as_default=True)
bus = SystemBus()
configuration_manager = openvpn3.ConfigurationManager(bus)
path = configuration_manager.LookupConfigName(credentials['config'])[0]
configuration = configuration_manager.Retrieve(path)
session_manager = openvpn3.SessionManager(bus)
with contextlib.suppress(KeyboardInterrupt):
    try:
        start_new_session()
        GLib.MainLoop().run()
    finally:
        disconnect_session()
