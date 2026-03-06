# What is this?

This is a command line OpenVPN3 Linux front-end for starting VPN sessions and reconnecting in case of disconnections without any user intervention. It also directly logs the changes to session's status to the terminal. In order to do this, it needs to be given a "credentials file" as its only argument that contains information about the credentials needed for establishing connections. The credentials file is encrypted using a password. If it is not found, you will be asked for the credentials that will be written to this file for later reuse.

This front-end supports OpenVPN configurations where authentication happens using username and password and a TOTP used as a static challenge. For TOTP generation, the following paramters are assumed:
- time-step duration of 30 seconds
- SHA1 hash function
- 6 digits
- start time of UNIX epoch (1970-01-01 00:00:00 UTC)

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
malvo <path_to_credentials>
```

substituting the path to your credentials file. To stop the connection, use Ctrl+C (interrupt).
