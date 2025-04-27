# What is this?

This is a command line OpenVPN3 Linux front-end for starting VPN sessions and reconnecting in case of disconnections without any user intervention. It also directly logs the changes to session's status to the terminal. In order to do this, it needs to be given a "credentials file" as its only argument that contains all the necessary credentials for establishing connections, which means the file is extremely sensitive and needs to be kept safe.

This front-end supports OpenVPN configurations where authentication happens through username and password and a TOTP used as a static challenge. For TOTP generation, the following paramters are assumed:
- time-step duration of 30 seconds
- SHA1 hash function
- 6 digits
- start time of UNIX epoch (1970-01-01 00:00:00 UTC)

# What are the dependencies?

You need to have OpenVPN3 Linux installed on your system. Check the [official guide](https://community.openvpn.net/openvpn/wiki/OpenVPN3Linux) for details. This tool uses [oathtool](https://www.nongnu.org/oath-toolkit/) for TOTP generation. On debian, you can get that through the `oathtool` package. Finally you would need Python to run the tool. I've tested it on Python 3.11.

# What does a credentials file look like?

There is an example [credentials](credentials) file provided with fairly self-explanatory fields. This tool assumes that you have already [imported](https://community.openvpn.net/openvpn/wiki/OpenVPN3Linux#Importingaconfigurationfileforre-useandstartingaVPNsession) your configuration into the OpenVPN3 Linux back-end and are providing the name of that configuration (the same as the argument given to the `--config` option of tools such as `openvpn3 session-start`) in the `config` key of the credentials file. For the `secret` key, you need to provide the secret key that should be used to generate your TOTP's.

# How is it run?

Simply run
```
python client.py <path_to_credentials>
```
substituting the path to your credentials file. To stop the connection, use Ctrl+C (interrupt).