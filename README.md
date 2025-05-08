# What is this?

This is a command line OpenVPN3 Linux front-end for starting VPN sessions and reconnecting in case of disconnections without any user intervention. It also directly logs the changes to session's status to the terminal. In order to do this, it needs to be given a "credentials file" as its only argument that contains information about the credentials needed for establishing connections, which means the file can be extremely sensitive and might need to be kept safe.

This front-end supports OpenVPN configurations where authentication happens using username and password and a TOTP used as a static challenge. For TOTP generation, the following paramters are assumed:
- time-step duration of 30 seconds
- SHA1 hash function
- 6 digits
- start time of UNIX epoch (1970-01-01 00:00:00 UTC)

For the purpose of passing the necessary credentials to this program, you can either put them directly in the "credentials file" (which is not very safe) or retrieve them from [Bitwarden](https://bitwarden.com/) Password Manager. Note that retrieving credentials from Bitwarden takes precedence.

# What are the dependencies?

You need to have OpenVPN3 Linux installed on your system. Check the [official guide](https://community.openvpn.net/openvpn/wiki/OpenVPN3Linux) for details. This tool uses [oathtool](https://www.nongnu.org/oath-toolkit/) for TOTP generation. On debian, you can get that through the `oathtool` package. Python is needed to run the tool. I've tested it on Python 3.11. The requests Python package needs to be installed.

If you are keeping your credentials in Bitwarden Password Manager, you would also need to have the [Bitwarden CLI](https://bitwarden.com/help/cli/) [serving on localhost:8087](https://bitwarden.com/help/cli/#serve). This program will synchronize and unlock the vault and retrieve the needed information but will not lock the vault afterwards. The credentials are only retrieved once at the beginning and are not updated again. A unit file is provided for the user instance of systemd to automatically start Bitwarden on login. You need to copy or symlink `bitwarden.service` in your `$HOME/.config/systemd/user` (or wherever you put your user units) then run:
```
systemctl --user daemon-reload
systemctl --user --now enable bitwarden.service
```


# What does a credentials file look like?

There is an example [credentials](credentials) file provided. The `username` and `password` keys are fairly self-explanatory. This tool assumes that you have already [imported](https://community.openvpn.net/openvpn/wiki/OpenVPN3Linux#Importingaconfigurationfileforre-useandstartingaVPNsession) your configuration into the OpenVPN3 Linux back-end and are providing the name of that configuration (the same as the argument given to the `--config` option of tools such as `openvpn3 session-start`) in the `config` key of the credentials file. For the `secret` key, you need to provide the secret key that should be used to generate your TOTP's.

The `username-item` and `secret-item` keys allow you to specify the names of items stored in Bitwarden Password Manager that contain respectively the username-password pair and the TOTP secret for the configuration.

# How is it run?

Simply run
```
python client.py <path_to_credentials>
```
substituting the path to your credentials file. To stop the connection, use Ctrl+C (interrupt).