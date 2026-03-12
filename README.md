# What is this?

This is a command line OpenVPN3 Linux front-end for starting VPN sessions and reconnecting in case of disconnections without any user intervention. It directly logs the changes to session's status to the terminal. It also stores the username and password credentials used with the OpenVPN3 config in a password protected file for easier access in later sessions. In order to do this, it needs to be given the *name* of the config as its only argument. The credentials file is stored in your XDG data directory (e.g. `~/.local/share/malvo/`) with the same name as the config.

# Building the package

Install the build dependencies (on Debian or Ubuntu):

```
sudo apt install dpkg-dev debhelper dh-exec
```

From the source tree, build the binary package with:

```
dpkg-buildpackage -T binary
```

The resulting `.deb` will be created in the parent directory.

# Runtime dependencies

The package depends on OpenVPN3 Linux ([official guide](https://community.openvpn.net/openvpn/wiki/OpenVPN3Linux)). You can install the latest version from OpenVPN's APT repositories; otherwise the one from Debian's archive will be used.

# How is it run?

Run

```
malvo <config>
```

substituting the name of your credentials file (e.g. `work`; the file will be created or read from `~/.local/share/malvo/`). To stop the connection, use Ctrl+C (interrupt).
