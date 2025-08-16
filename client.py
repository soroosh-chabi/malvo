import contextlib
import getpass
import logging
import subprocess
import sys
import os
import base64
import json

from dbus import SystemBus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
import openvpn3
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


SALT_LENGTH = 16  # Length of the salt in bytes

MINOR_MAP = {
    2: None,
    6: 'Connecting',
    7: 'Connected',
    8: 'Disconnecting',
    9: 'Disconnected',
    11: None,
    12: 'Reconnecting',
    16: 'Connecion done',
}


def status_change_handler(status_major: int, status_minor: int, message: str):
    log_prefix = 'Status Change: '
    if status_major != 2 or status_minor not in MINOR_MAP:
        # For status_major values consult https://codeberg.org/OpenVPN/openvpn3-linux/src/commit/fe2645567c9875509d8c3c3d88b22c4939779f8c/src/dbus/constants.hpp#L45
        # For status_minor values consult https://codeberg.org/OpenVPN/openvpn3-linux/src/commit/fe2645567c9875509d8c3c3d88b22c4939779f8c/src/dbus/constants.hpp#L90
        logging.warning(f'{log_prefix}{status_major}, {status_minor}, {message}.')
    else:
        if status_minor == 11:
            change_prefix = 'Authentication failed'
            try:
                session.Ready()
            except Exception as e:
                logging.error(f'{log_prefix}{change_prefix} because session is not ready: {e}')
            else:
                logging.info(f'{log_prefix}{change_prefix}.')
            disconnect_session()
        elif minor_message := MINOR_MAP[status_minor]:
            logging.info(f'{log_prefix}{minor_message}.')
        if status_minor in [9, 11]:
            start_new_session()


def attention_required_handler(attention_type: int, attention_group: int, message: str):
    logging.warning(f'Attention Required: {attention_type}, {attention_group}, {message}')


session: openvpn3.Session = None


def start_new_session():
    global session
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


def get_encryption_key(salt):
    while True:
        password = getpass.getpass('Enter password: ')
        if not password:
            print('Password cannot be empty')
            continue
        break
    password = password.encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=1_200_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password))
    return Fernet(key)


def read_credentials():
    credentials = {}
    credentials_path = sys.argv[1]
    try:
        with open(credentials_path, 'rb') as credentials_file:
            salt = credentials_file.read(SALT_LENGTH)
            encrypted_data = credentials_file.read()
            fernet = get_encryption_key(salt)
            decrypted_data = fernet.decrypt(encrypted_data).decode('utf-8')
            credentials = json.loads(decrypted_data)
    except FileNotFoundError:
        credentials = {
            'username': input('Enter username: '),
            'password': getpass.getpass('Enter password: '),
            'secret': getpass.getpass('Enter TOTP secret: '),
            'config': input('Enter config name: ')
        }
        salt = os.urandom(SALT_LENGTH)
        fernet = get_encryption_key(salt)
        encrypted_data = fernet.encrypt(json.dumps(credentials).encode('utf-8'))
        with open(credentials_path, 'wb') as credentials_file:
            credentials_file.write(salt)
            credentials_file.write(encrypted_data)
    return credentials


credentials = read_credentials()
logging.basicConfig(format=f'%(asctime)s:{credentials["config"]}:%(levelname)s:%(message)s', level=logging.INFO)
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
