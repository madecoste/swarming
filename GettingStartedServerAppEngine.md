

# Introduction #

This requires paying account for [App Engine](https://cloud.google.com/products/) and to have [Cloud Storage](https://cloud.google.com/) to be enabled. [Compute Engine](https://cloud.google.com/products/compute-engine/) is an excellent candidate to be used for the Swarming bots. This setup involves central auth server that is optional, but nice to have. Without it user groups on isolate and swarming servers would need to be managed independently.


# Details to get a server up and running #

## 1. Reserve instance names ##

  * Visit https://appengine.google.com and register 3 instances. For documentation purposes, we'll name them `my-isolate-server`, `my-swarming-server` and `my-auth-server`.
  * Add admins as needed.


## 2. Deploy server code and set it as default ##

  * `gae update` uploads the code to AppEngine. `--switch` tells to switch default version to newly uploaded version immediately.

```
./appengine/auth_service/tools/gae upload -A my-auth-server --switch
./appengine/swarming/tools/gae upload -A my-swarming-server --switch
./appengine/isolate/tools/gae upload -A my-isolate-server --switch
```

At this point you can visit each of the service via a web browser but they are still not functional.

_Note:_ these are example names. You need to create your own instances at https://appengine.google.com.


## 3. Tweak performance settings ##

Via https://appengine.google.com, tweak the `Application Settings` to improve the performance. Recommendations:
  * Cookie Expiration: 2 Weeks.
  * Memcache Service Class: Dedicated with 1 to 5 Gb, depending on the load. Shared is fine with light load. To properly choose the value:
    * Set the cache to Dedicated 5Gb.
    * Wait a day of steady state usage.
    * Set the limit to be lower than the value read at "Total cache size" in "Memcache Viewer".
  * Log retention as desired depending on usage.

[app.yaml](https://cloud.google.com/appengine/docs/python/config/appconfig) already sets to use [F4 instances](https://cloud.google.com/appengine/docs/python/modules/#Python_Instance_scaling_and_class) by default.


## 4. Bootstrap 'administrators' group ##

Go to https://my-auth-server.appspot.com. If you are appengine admin of that instance, you'll be prompted to be added as a first administrator to 'administrators' group. Once accepted, wait ~30 sec the for change to take effect.

Now you should be able to see auth-server web UI and manage user groups and OAuth2 configuration from there (see below).

## 5. Link swarming and isolate servers to auth server ##

This would allow to manage user groups and OAuth2 configuration centrally from my-auth-server.

Go to https://my-auth-server.appspot.com/auth/services, in "Add service" section enter "my-swarming-server" and click "Generate Linking URL". Click on the link, it will redirect you to a page on https://my-swarming-server.appspot.com where you can confirm that you want to link it on my-auth-server.
You should be an appengine level admin of my-swarming-server to complete this process.

Do the same for my-isolate-server.

## 6. Configure OAuth2 client ##

Client toolset uses OAuth2 for authentication. We decided not to hardcode client\_id and client\_secret in the client source code but instead allow site admins to setup their own OAuth2 clients.

Follow this steps to configure OAuth2. Will be using my-swarming-server Cloud project, though any other project can be used.
Actions are performed in Developer Console for my-swarming-server project: https://console.developers.google.com/project/my-swarming-server:
  1. Fill in "Email Address" and "Product Name" on Consent Screen tab: https://console.developers.google.com/project/my-swarming-server/apiui/consent. The values will show up on Consent screen during OAuth2 login flow.
  1. Go to Credentials tab and click "Create new Client ID": https://console.developers.google.com/project/my-swarming-server/apiui/credential
  1. Pick Application type: "Installed application", Installed application type: "Other". Then click "Create Client ID".
  1. Copy\paste generated "Client ID" and "Client Secret" to "Primary client\_id" and "Client not-so-secret" fields on auth-server OAuth2 config page: https://my-auth-server.appspot.com/auth/oauth_config.
  1. Click "Submit". Wait 30 sec.
  1. To verify it worked, use auth.py tool from client toolset: auth.py login --service https://my-auth-server.appspot.com.


## 7. Whitelisting IPs for bots ##

This configuration is optimized for bots with static IPs. It's fine to use exclusively IP whitelist for authentication during development and testing phase, but eventually production bots should use some stronger form of authentication, e.g. OAuth2 AND IP whitelist.

_TODO: implement "stronger form of authentication" for bots_

Auth server holds a set of named IP whitelists that gets replicated to isolate and swarming services. There's a whitelist named "bots" that contains IP subnets the services trust unconditionally. If a request comes from such IP it will be authenticated as coming from 'bot:<ip address>' identity (unless some other authentication token is presented):

  * Go to https://my-auth-service.appspot.com/auth/ip_whitelists
  * Pick "Create new IP whitelist"
  * Name it "bots", description can be whatever you like.
  * Add IPs or IP subnets to whitelist.


## 8. Create ACLs ##

Swarming and Isolate instances use groups with some predefined names to control who can do what. By default in a fresh instance all groups are empty and no one can do anything :) Here's a minimal configuration suitable for initial testing and development:

  * **swarming-bots**:
    * bots:`*` (allow all whitelisted machines to act as a swarming bots).
  * **swarming-users**:
    * Emails of people who should be able to trigger swarming tasks. It's fine to use `*` pattern too, e.g. `*`@chromium.org.
  * **swarming-privileged-users**:
    * swarming-users (allow all users to see all tasks, for simplicity during testing).
  * **isolate-access**:
    * swarming-bots (allow all bots to read and write from isolate storage).
    * swarming-users (allow all users to read and write from isolate storage).

> See also SwarmingAccessGroups.

## 9. Cloud Storage configuration for isolate-server ##

The isolate server uses [Google Cloud Storage](https://cloud.google.com/storage/) as its backend.

_TODO: detail this section_.
  * Configure our Cloud Storage project via https://cloud.google.com/console#/project and generate a private key. Normally the admin URL will look like https://console.developers.google.com/project/my-isolate-server/permissions.
  * Visit https://my-isolate-server.appspot.com/restricted/gs_config to configure the Cloud Storage bucket, private key and client id.


# Adding Bots #

Now that you have a server up and running, you'll need GettingStartedBots before triggering a task.