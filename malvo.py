#!/usr/bin/env python3
import asyncio
import base64
import contextlib
import enum
import getpass
import json
import logging
import os
import signal
import sys
import time

from gi.events import GLibEventLoopPolicy
from gi.repository import GLib, Gio
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from xdg.BaseDirectory import save_data_path


class CredentialStore:
    SALT_LENGTH = 16

    def __init__(self, config: str):
        self.config = config
        credentials = self._read_credentials()
        self.username = credentials['username']
        self.password = credentials['password']
        self.secret = credentials['secret']

    def _get_encryption_key(self, salt):
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

    def _read_credentials(self):
        credentials_path = os.path.join(save_data_path('malvo'), self.config)
        try:
            with open(credentials_path, 'rb') as credentials_file:
                salt = credentials_file.read(self.SALT_LENGTH)
                encrypted_data = credentials_file.read()
                fernet = self._get_encryption_key(salt)
                decrypted_data = fernet.decrypt(encrypted_data).decode('utf-8')
                credentials = json.loads(decrypted_data)
        except FileNotFoundError:
            credentials = {
                'username': input('Enter username: '),
                'password': getpass.getpass('Enter password: '),
                'secret': getpass.getpass('Enter TOTP secret: '),
            }
            salt = os.urandom(self.SALT_LENGTH)
            fernet = self._get_encryption_key(salt)
            encrypted_data = fernet.encrypt(json.dumps(credentials).encode('utf-8'))
            with open(credentials_path, 'wb') as credentials_file:
                credentials_file.write(salt)
                credentials_file.write(encrypted_data)
        return credentials


async def call_with_retry(connection: Gio.DBusConnection, bus_name: str, object_path: str, interface_name: str, method_name: str, parameters: GLib.Variant | None) -> GLib.Variant:
    delay = 0.5
    attempts = 10
    while attempts > 0:
        try:
            return await connection.call(bus_name, object_path, interface_name, method_name, parameters, None, Gio.DBusCallFlags.NONE, -1)
        except GLib.Error as excp:
            err = str(excp)
            if err.find("Object does not exist at path") == -1:
                raise
            time.sleep(delay)
            delay *= 1.33
        attempts -= 1
    raise excp


@contextlib.asynccontextmanager
async def tunnel(connection: Gio.DBusConnection, config_path: str):
    response = await call_with_retry(connection, 'net.openvpn.v3.sessions', '/net/openvpn/v3/sessions', 'net.openvpn.v3.sessions', 'NewTunnel', GLib.Variant.new_tuple(GLib.Variant.new_object_path(config_path)))
    session_path = response.get_child_value(0).get_string()
    try:
        yield session_path
    finally:
        await call_with_retry(connection, 'net.openvpn.v3.sessions', session_path, 'net.openvpn.v3.sessions', 'Disconnect', None)
        logging.info(f'Disconnected.')


@contextlib.asynccontextmanager
async def status_change(connection: Gio.DBusConnection, session_path: str, callback):
    await call_with_retry(connection, 'net.openvpn.v3.sessions', session_path, 'net.openvpn.v3.sessions', 'LogForward', GLib.Variant.new_tuple(GLib.Variant.new_boolean(True)))
    subscription_id = connection.signal_subscribe('net.openvpn.v3.log', 'net.openvpn.v3.backends', 'StatusChange', session_path, None, Gio.DBusSignalFlags.NONE, callback)
    try:
        yield
    finally:
        connection.signal_unsubscribe(subscription_id)


async def set_inputs(connection: Gio.DBusConnection, session_path: str, credential_store: CredentialStore):
    response = await call_with_retry(connection, 'net.openvpn.v3.sessions', session_path, 'net.openvpn.v3.sessions', 'UserInputQueueGetTypeGroup', None)
    type_groups = response.get_child_value(0)
    for i in range(type_groups.n_children()):
        type_group = type_groups.get_child_value(i)
        type = type_group.get_child_value(0).get_uint32()
        group = type_group.get_child_value(1).get_uint32()
        response = await call_with_retry(connection, 'net.openvpn.v3.sessions', session_path, 'net.openvpn.v3.sessions', 'UserInputQueueCheck', GLib.Variant.new_tuple(GLib.Variant.new_uint32(type), GLib.Variant.new_uint32(group)))
        indices = response.get_child_value(0)
        for j in range(indices.n_children()):
            index = indices.get_child_value(j).get_uint32()
            response = await call_with_retry(connection, 'net.openvpn.v3.sessions', session_path, 'net.openvpn.v3.sessions', 'UserInputQueueFetch', GLib.Variant.new_tuple(GLib.Variant.new_uint32(type), GLib.Variant.new_uint32(group), GLib.Variant.new_uint32(index)))
            match response.get_child_value(3).get_string():
                case 'username':
                    input = credential_store.username
                case 'password':
                    input = credential_store.password
                case 'static_challenge':
                    process = await asyncio.create_subprocess_exec('oathtool', '--totp', '-d6', '-b', credential_store.secret, stdout=asyncio.subprocess.PIPE)
                    stdout, _ = await process.communicate()
                    input = stdout.decode('utf-8').strip()
                case _ as unknown_variable_name:
                    logging.warning(f'Unknown user input slot: {unknown_variable_name}')
                    continue
            response = await call_with_retry(connection, 'net.openvpn.v3.sessions', session_path, 'net.openvpn.v3.sessions', 'UserInputProvide', GLib.Variant.new_tuple(GLib.Variant.new_uint32(type), GLib.Variant.new_uint32(group), GLib.Variant.new_uint32(index), GLib.Variant.new_string(input)))


async def connect(connection: Gio.DBusConnection, session_path: str):
    await call_with_retry(connection, 'net.openvpn.v3.sessions', session_path, 'net.openvpn.v3.sessions', 'Connect', None)


class StatusMinor(enum.IntEnum):
    CFG_OK = 2
    CONN_CONNECTING = 6
    CONN_CONNECTED = 7
    CONN_DISCONNECTING = 8
    CONN_DISCONNECTED = 9
    CONN_AUTH_FAILED = 11
    CONN_RECONNECTING = 12
    CONN_DONE = 16


def status_change_handler(failed: asyncio.Event):
    def callback(_connection, _sender_name, _object_path, _interface_name, _signal_name, parameters: GLib.Variant):
        status_major = parameters.get_child_value(0).get_uint32()
        status_minor = parameters.get_child_value(1).get_uint32()
        message = parameters.get_child_value(2).get_string()
        log_prefix = 'Status Change: '
        if status_minor not in StatusMinor:
            # For status_major values consult https://codeberg.org/OpenVPN/openvpn3-linux/src/commit/fe2645567c9875509d8c3c3d88b22c4939779f8c/src/dbus/constants.hpp#L45
            # For status_minor values consult https://codeberg.org/OpenVPN/openvpn3-linux/src/commit/fe2645567c9875509d8c3c3d88b22c4939779f8c/src/dbus/constants.hpp#L90
            logging.warning(f'{log_prefix}{status_major}, {status_minor}, {message}.')
        else:
            logging.info(f'{log_prefix}{StatusMinor(status_minor).name}.')
        if status_minor in (StatusMinor.CONN_DISCONNECTING, StatusMinor.CONN_DISCONNECTED, StatusMinor.CONN_AUTH_FAILED, StatusMinor.CONN_DONE):
            failed.set()
    return callback


async def session(connection: Gio.DBusConnection, credential_store: CredentialStore, config_path: str):
    failed = asyncio.Event()
    async with tunnel(connection, config_path) as session_path:
        async with status_change(connection, session_path, status_change_handler(failed)):
            await set_inputs(connection, session_path, credential_store)
            await connect(connection, session_path)
            await failed.wait()


async def get_config_path(connection: Gio.DBusConnection, config_name: str):
    response = await call_with_retry(connection, 'net.openvpn.v3.configuration', '/net/openvpn/v3/configuration', 'net.openvpn.v3.configuration', 'LookupConfigName', GLib.Variant.new_tuple(GLib.Variant.new_string(config_name)))
    return response.get_child_value(0).get_objv()[0]


async def session_manager(connection: Gio.DBusConnection, credential_store: CredentialStore):
    config_path = await get_config_path(connection, credential_store.config)
    while True:
        try:
            await session(connection, credential_store, config_path)
        except Exception:
            logging.exception('Exception in running Session.')


async def interrupt():
    interrupted = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGINT, interrupted.set)
    await interrupted.wait()


@contextlib.asynccontextmanager
async def dbus_connection():
    connection = await Gio.bus_get(Gio.BusType.SYSTEM)
    try:
        yield connection
    finally:
        await connection.close()


def activate_handler(credential_store: CredentialStore):
    def callback(application: Gio.Application):
        async def run():
            try:
                async with dbus_connection() as connection:
                    task = asyncio.create_task(session_manager(connection, credential_store))
                    await interrupt()
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        logging.exception('Exception in running SessionManager.')
            finally:
                application.release()
        asyncio.create_task(run())
        application.hold()
    return callback


config = sys.argv[1]
if config != os.path.basename(config):
    sys.exit('Config name must not contain path components.')
credential_store = CredentialStore(config)
logging.basicConfig(format=f'%(asctime)s:{credential_store.config}:%(levelname)s:%(message)s', level=logging.INFO)
asyncio.set_event_loop_policy(GLibEventLoopPolicy())
app = Gio.Application.new(None, Gio.ApplicationFlags.FLAGS_NONE)
app.connect('activate', activate_handler(credential_store))
app.run()
