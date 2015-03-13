# Prerequisites #

  1. Get all the sources at GettingTheSources.
  1. Grab [depot\_tools](https://sites.google.com/a/chromium.org/dev/developers/how-tos/install-depot-tools) to get `git cl`.


# Submitting a patch for review to be integrated upstream #

  1. Go into the right git submodule, for example: `cd client`
  1. Create a branch tracking origin/master: `git checkout -b my_hack origin/master`
  1. Hack. Hack. Hack.
  1. Write tests.
  1. `git commit -a -m "I rock the world"`
  1. Sign the [Google CLA](https://developers.google.com/open-source/cla/individual).
  1. Submit your change for review with:
```
git cl upload --send-mail
```

We don't support merge request at the moment.

# Stable branch #

  * The `stable` branch in `client` repository is a pointer to the master branch to the known good commit. It normally is set to `master` directly shortly after commits to `master`.
  * `client` is also versioned via swarming/.gitmodules. It is normally rolled to `master` too but may disagree with `stable`.