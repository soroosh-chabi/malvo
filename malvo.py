#!/usr/bin/env python3
import asyncio
import base64
import contextlib
import enum
import json
import logging
import os
import signal
import sys
import termios

from gi.events import GLibEventLoopPolicy
from gi.repository import GLib, Gio
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from xdg.BaseDirectory import save_data_path


class CredentialStore:
    SALT_LENGTH = 16

    def __init__(self, config: str, password: str):
        self._config = config
        self._password = password

    def get_credential(self, name: str) -> str | None:
        credentials = self._read_credentials()
        return credentials.get(name)

    def set_credential(self, name: str, value: str):
        credentials = self._read_credentials()
        credentials[name] = value
        self._write_credentials(credentials)

    def verify_password(self):
        try:
            self._decrypt_credentials()
        except FileNotFoundError:
            pass

    def _write_credentials(self, credentials: dict[str, str]):
        salt = os.urandom(self.SALT_LENGTH)
        fernet = self._get_encryption_key(salt)
        encrypted_data = fernet.encrypt(json.dumps(credentials).encode('utf-8'))
        credentials_path = os.path.join(save_data_path('malvo'), self._config)
        with open(credentials_path, 'wb') as credentials_file:
            credentials_file.write(salt)
            credentials_file.write(encrypted_data)

    def _read_credentials(self):
        try:
            decrypted_data = self._decrypt_credentials()
        except FileNotFoundError:
            return {}
        return json.loads(decrypted_data.decode('utf-8'))

    def _decrypt_credentials(self) -> bytes:
        credentials_path = os.path.join(save_data_path('malvo'), self._config)
        with open(credentials_path, 'rb') as credentials_file:
            salt = credentials_file.read(self.SALT_LENGTH)
            encrypted_data = credentials_file.read()
        fernet = self._get_encryption_key(salt)
        return fernet.decrypt(encrypted_data)

    def _get_encryption_key(self, salt):
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=1_200_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._password.encode()))
        return Fernet(key)


class InputAttentionGroup(enum.IntEnum):
    USER_PASSWORD = 1
    CHALLENGE_STATIC = 4


async def read_line(prompt: str) -> str:
    print(prompt, end='', flush=True)
    ready = asyncio.Event()
    loop = asyncio.get_running_loop()
    fd = sys.stdin.fileno()
    loop.add_reader(fd, ready.set)
    try:
        await ready.wait()
    except asyncio.CancelledError:
        print()
        raise
    finally:
        loop.remove_reader(fd)
    return input()

async def read_secret(prompt: str) -> str:
    fd = sys.stdin.fileno()
    if sys.stdin.isatty():
        old = termios.tcgetattr(fd)
        new = old.copy()
        new[3] = (new[3] & ~termios.ECHO) | termios.ECHONL
        termios.tcsetattr(fd, termios.TCSANOW, new)
        try:
            return await read_line(prompt)
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old)
    return await read_line(prompt)


class CredentialManager:
    def __init__(self, config: str, credential_store: CredentialStore):
        self.config = config
        self._credential_store = credential_store

    async def _get_credential_store(self):
        return self._credential_store

    async def get_credential(self, attention_group: InputAttentionGroup, name: str, description: str, hidden_input: bool) -> str:
        match attention_group:
            case InputAttentionGroup.USER_PASSWORD:
                if credential := (await self._get_credential_store()).get_credential(name):
                    return credential
                return await self._ask_for_credential(attention_group, name, description, hidden_input)
            case InputAttentionGroup.CHALLENGE_STATIC:
                return await self._ask_for_credential(attention_group, name, description, hidden_input)

    async def _ask_for_credential(self, attention_group: InputAttentionGroup, name: str, description: str, hidden_input: bool) -> str:
        if not description.endswith(': '):
            description += ': '
        if hidden_input:
            credential = await read_secret(description)
        else:
            credential = await read_line(description)
        if attention_group == InputAttentionGroup.USER_PASSWORD:
            (await self._get_credential_store()).set_credential(name, credential)
        return credential


async def call_with_retry(connection: Gio.DBusConnection, bus_name: str, object_path: str, interface_name: str, method_name: str, parameters: GLib.Variant | None) -> GLib.Variant:
    delay = 0.5
    attempts = 10
    while attempts > 0:
        try:
            return await connection.call(bus_name, object_path, interface_name, method_name, parameters, None, Gio.DBusCallFlags.NONE, -1)
        except GLib.Error as excp:
            if "Object does not exist at path" not in str(excp):
                raise
        await asyncio.sleep(delay)
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


async def set_inputs(connection: Gio.DBusConnection, session_path: str, credential_manager: CredentialManager):
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
            input = await credential_manager.get_credential(InputAttentionGroup(group), response.get_child_value(3).get_string(), response.get_child_value(4).get_string(), response.get_child_value(5).get_boolean())
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


class StatusChangeHandler:
    def __init__(self, connection: Gio.DBusConnection):
        self._connection = connection
        self.failed = asyncio.Event()
        self._current_session = None

    async def set_current_session(self, session_path: str):
        self._current_session = session_path
        await call_with_retry(self._connection, 'net.openvpn.v3.sessions', self._current_session, 'net.openvpn.v3.sessions', 'LogForward', GLib.Variant.new_tuple(GLib.Variant.new_boolean(True)))        

    def _callback(self, _connection, _sender_name, object_path: str, _interface_name, _signal_name, parameters: GLib.Variant):
        if object_path != self._current_session:
            return
        status_minor = parameters.get_child_value(1).get_uint32()
        log_prefix = 'Status Update: '
        if status_minor not in StatusMinor:
            # For status_major values consult https://codeberg.org/OpenVPN/openvpn3-linux/src/commit/fe2645567c9875509d8c3c3d88b22c4939779f8c/src/dbus/constants.hpp#L45
            # For status_minor values consult https://codeberg.org/OpenVPN/openvpn3-linux/src/commit/fe2645567c9875509d8c3c3d88b22c4939779f8c/src/dbus/constants.hpp#L90
            status_major = parameters.get_child_value(0).get_uint32()
            message = parameters.get_child_value(2).get_string()
            logging.warning(f'{log_prefix}{status_major}, {status_minor}, {message}.')
        else:
            logging.info(f'{log_prefix}{StatusMinor(status_minor).name}.')
        if status_minor in (StatusMinor.CONN_DISCONNECTING, StatusMinor.CONN_DISCONNECTED, StatusMinor.CONN_AUTH_FAILED, StatusMinor.CONN_DONE):
            self.failed.set()

    def __enter__(self):
        self._subscription_id = self._connection.signal_subscribe('net.openvpn.v3.log', 'net.openvpn.v3.backends', 'StatusChange', None, None, Gio.DBusSignalFlags.NONE, self._callback)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._connection.signal_unsubscribe(self._subscription_id)
        return False


async def session(connection: Gio.DBusConnection, credential_manager: CredentialManager, config_path: str, status_change_handler: StatusChangeHandler):
    async with tunnel(connection, config_path) as session_path:
        await status_change_handler.set_current_session(session_path)
        await set_inputs(connection, session_path, credential_manager)
        await connect(connection, session_path)
        await status_change_handler.failed.wait()


async def get_config_path(connection: Gio.DBusConnection, config_name: str):
    response = await call_with_retry(connection, 'net.openvpn.v3.configuration', '/net/openvpn/v3/configuration', 'net.openvpn.v3.configuration', 'LookupConfigName', GLib.Variant.new_tuple(GLib.Variant.new_string(config_name)))
    return response.get_child_value(0).get_objv()[0]


async def session_manager(connection: Gio.DBusConnection, credential_manager: CredentialManager):
    config_path = await get_config_path(connection, credential_manager.config)
    with StatusChangeHandler(connection) as status_change_handler:
        while True:
            try:
                await session(connection, credential_manager, config_path, status_change_handler)
            except Exception:
                logging.exception('Exception in running Session.')
                await asyncio.sleep(1)


async def run_interruptible(coro):
    task = asyncio.create_task(coro)
    interrupted = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, interrupted.set)
    try:
        await asyncio.wait([task, asyncio.create_task(interrupted.wait())], return_when=asyncio.FIRST_COMPLETED)
        if task.cancel():
            try:
                await task
            except asyncio.CancelledError:
                pass
        else:
            await task
    finally:
        loop.remove_signal_handler(signal.SIGINT)


@contextlib.asynccontextmanager
async def dbus_connection():
    connection = await Gio.bus_get(Gio.BusType.SYSTEM)
    try:
        yield connection
    finally:
        await connection.close()


async def init_credential_manager(config: str) -> CredentialManager:
    while True:
        password = await read_secret('Enter credentials file password: ')
        credential_store = CredentialStore(config, password)
        try:
            credential_store.verify_password()
            break
        except InvalidToken:
            print('Credentials file password is incorrect.')
    return CredentialManager(config, credential_store)


async def main():
    config = sys.argv[1]
    if config != os.path.basename(config):
        print('Config name must not contain path components.')
        return
    logging.basicConfig(format=f'%(asctime)s:{config}:%(levelname)s:%(message)s', level=logging.INFO)
    credential_manager = await init_credential_manager(config)
    async with dbus_connection() as connection:
        await session_manager(connection, credential_manager)


def activate(application: Gio.Application):
    async def run():
        try:
            await run_interruptible(main())
        finally:
            application.release()
    asyncio.create_task(run())
    application.hold()


asyncio.set_event_loop_policy(GLibEventLoopPolicy())
app = Gio.Application.new(None, Gio.ApplicationFlags.FLAGS_NONE)
app.connect('activate', activate)
app.run()
