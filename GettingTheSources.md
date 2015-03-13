# Introduction #

A Swarming setup is made up of 4 components to work, with the 3 servers in the default repository and the client in its own repository:

  * [services/swarming](https://code.google.com/p/swarming/source/browse?#git%2Fservices%2Fswarming) contains the C&C center. It is meant to be run on [AppEngine](https://developers.google.com/appengine/).
    * [services/swarming/swarm\_bot](https://code.google.com/p/swarming/source/browse?#git%2Fservices%2Fswarming%2Fswarming_bot) contains the bot code. The user doesn't not have to touch it, since the bot code is downloaded directly from the server.
  * [services/auth\_service](https://code.google.com/p/swarming/source/browse?#git%2Fappengine%2Fauth_service) contains the Authentication service. It is the central point for Access Control Lists.
  * [services/isolate](https://code.google.com/p/swarming/source/browse?#git%2Fservices%2Fisolate) contains the Content-Addressed-Cache server. It is meant to be run on [AppEngine](https://developers.google.com/appengine/).
  * [client](https://code.google.com/p/swarming/source/browse?repo=client) contains the client code. This includes tracing tools, isolation code and swarm related client side code.


# Checking out #

Check out the whole suite via git submodules with:

```
git clone https://code.google.com/p/swarming --recursive
```


# Contributors #

If you want to push, you will be asked for your _code.google.com_ credential all the time. You can store this information on disk, assuming you are using either full disk encryption or efscrypt:

```
echo "machine code.google.com login <email address> password <code.google.com password>" >> ~/.netrc
```

Want to contribute? See [Contributing](Contributing.md).


# Try it out! #

Once you got the sources, you can try it out on AppEngine: GettingStartedServerAppEngine.