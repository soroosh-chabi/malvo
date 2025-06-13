# What is this?

This is a command line OpenVPN3 Linux front-end for starting VPN sessions and reconnecting in case of disconnections without any user intervention. It also directly logs the changes to session's status to the terminal. In order to do this, it needs to be given a "credentials file" as its only argument that contains information about the credentials needed for establishing connections. The credentials file is encrypted using a 4-digit PIN. If it is not found, you will be asked for the credentials that will be written to this file for later reuse.

This front-end supports OpenVPN configurations where authentication happens using username and password and a TOTP used as a static challenge. For TOTP generation, the following paramters are assumed:
- time-step duration of 30 seconds
- SHA1 hash function
- 6 digits
- start time of UNIX epoch (1970-01-01 00:00:00 UTC)

# What are the dependencies?

You need to have OpenVPN3 Linux installed on your system. Check the [official guide](https://community.openvpn.net/openvpn/wiki/OpenVPN3Linux) for details. This tool uses [oathtool](https://www.nongnu.org/oath-toolkit/) for TOTP generation. On debian, you can get that through the `oathtool` package. Python is needed to run the tool. I've tested it on Python 3.11. The requests Python package needs to be installed.

# How is it run?

Simply run
```
python client.py <path_to_credentials>
```
substituting the path to your credentials file. To stop the connection, use Ctrl+C (interrupt).