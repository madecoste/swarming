

# Introduction #

Starting a bot is basically running a python script on boot.


# Details #

You also can connect as many bots as you want to a server! In particular, the bots can be running Windows, OSX, Ubuntu, Raspbian, on a Crouton chroot on ChromeOS (even on ARM), etc.


## Right-sizing bots ##

Visit SwarmingBotSizing for details about how to chose the right amount of CPU/RAM/Disk space depending on the use case.


## Bootstrapping automatically ##

The server has a self-bootstrapping script that is hosted by default at the /bootstrap URL. It is also advertised on the swarming server itself. Bootstrapping a bot boils down to running the python script directly:

```
python -c "import urllib; exec urllib.urlopen('https://my-swarming-server.appspot.com/bootstrap').read()"
```

_TODO: it only works for IP whitelisted bots currently_

## Bootstrapping Manually ##

You can also simply download the swarming bot code directly from the server and start it manually:

```
mkdir bot; cd bot
curl -sSLOJ https://my-swarming-server.appspot.com/get_slave_code
python swarming_bot.zip
```

_TODO: it only works for IP whitelisted bots currently_

## Configuration ##

The bot will determine its dimensions automatically. The server code provides common dimensions (os, cpu, gpu, etc) and additional dimensions can be provided via [bot\_config.py](https://code.google.com/p/swarming/source/browse/appengine/swarming/swarming_bot/bot_config.py).


## Automatically starting on reboot ##

`os_utilities.py` provides tooling to have the bot setup themselves to automatically start on reboot to reduce manual setup. This shall be triggered by a custom [bot\_config.py](https://code.google.com/p/swarming/source/browse/appengine/swarming/swarming_bot/bot_config.py).


## Whitelisting bots on the server ##

Each bot must be "whitelisted" to allow them to access the server and fetch tasks to run. If not done, polling for jobs will result in a "403 Forbidden" response from Swarming.


## Cron job on linux ##

If you setup your bot to run as a cron job, be sure that environment variables are correctly set as expected. See http://www.logikdev.com/2010/02/02/locale-settings-for-your-cron-job/ for more details.


## Debugging ##

If you need to debug your tasks directly, you can run them in the same environment as Swarming runs them with `swarming.py reproduce`.


# Try it out #

```
git clone https://code.google.com/p/swarming.client
python swarming.client/example/3_swarming_run_auto_upload.py --help
python swarming.client/example/3_swarming_run_auto_upload.py -I https://my-isolate-server.appspot.com -S https://my-swarming-server.appspot.com
```