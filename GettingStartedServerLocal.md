# Running locally #

A Swarming setup normally requires an isolate server and a swarming server. Then you can start a local bot to run trivial tests.

**Caveat:** The local App Engine SDK server is particularly slow, do **not** expect it to give acceptable performance. The Swarming code is optimized to be used in production. The main use case for using the local server is for UI development of the Swarming server itself.


## Getting the App Engine SDK ##

[Download the SDK](https://developers.google.com/appengine/downloads#Google_App_Engine_SDK_for_Python) and decompress it if you don't have it already.


## Swarming server ##

The Swarming server is the task controller. That's where the Swarming bots connect to and it is the host to use to trigger tasks.

Use `--open` **only** if you plan to connect a bot or trigger from another host. Otherwise leave it out.

```
./appengine/swarming/tools/gae devserver --open
```

Open http://localhost:8080 to ensure it works.

Ctrl-C out to terminate.


## Isolate server ##

Currently, the Isolate Server **only** works on AppEngine, see GettingStartedServerAppEngine.


## Bots ##

Connect at least one bot to your server. You can run a bot directly on the same host than the server for testing purposes.

```
curl http://localhost:8080/get_slave_code -o swarming_bot.zip
python swarming_bot.zip
```

Ctrl-C out to terminate.


## Triggering your first job ##

This tests that your setup works end-to-end. Replace with your isolate server instance.

```
./client/example/3_swarming_run_auto_upload.py -I https://my-isolate-server.appspot.com -S http://localhost:8080
```


# Try it on App Engine #

Now that your ran successfully a end-to-end setup, it's time to try it on a distributed architecture; GettingStartedServerAppEngine.