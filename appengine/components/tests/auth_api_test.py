#!/usr/bin/env python
# Copyright 2014 The Swarming Authors. All rights reserved.
# Use of this source code is governed by the Apache v2.0 license that can be
# found in the LICENSE file.

# Disable 'Access to a protected member', Unused argument', 'Unused variable'.
# pylint: disable=W0212,W0612,W0613


import Queue
import sys
import threading
import unittest

import test_env
test_env.setup_test_env()

from google.appengine.ext import ndb

from support import test_case

from components.auth import api
from components.auth import ipaddr
from components.auth import model


class AuthDBTest(test_case.TestCase):
  """Tests for AuthDB class."""

  def setUp(self):
    super(AuthDBTest, self).setUp()
    self.mock(api.logging, 'warning', lambda *_args: None)
    self.mock(api.logging, 'error', lambda *_args: None)

  def test_is_group_member(self):
    # Test identity.
    joe = model.Identity(model.IDENTITY_USER, 'joe@example.com')

    # Group that includes joe via glob.
    with_glob = model.AuthGroup(id='WithGlob')
    with_glob.globs.append(
        model.IdentityGlob(model.IDENTITY_USER, '*@example.com'))

    # Group that includes joe via explicit listing.
    with_listing = model.AuthGroup(id='WithListing')
    with_listing.members.append(joe)

    # Group that includes joe via nested group.
    with_nesting = model.AuthGroup(id='WithNesting')
    with_nesting.nested.append('WithListing')

    # Creates AuthDB with given list of groups and then runs the check.
    is_member = (lambda groups, identity, group:
        api.AuthDB(groups=groups).is_group_member(group, identity))

    # Wildcard group includes everyone (even anonymous).
    self.assertTrue(is_member([], joe, '*'))
    self.assertTrue(is_member([], model.Anonymous, '*'))

    # An unknown group includes nobody.
    self.assertFalse(is_member([], joe, 'Missing'))
    self.assertFalse(is_member([], model.Anonymous, 'Missing'))

    # Globs are respected.
    self.assertTrue(is_member([with_glob], joe, 'WithGlob'))
    self.assertFalse(is_member([with_glob], model.Anonymous, 'WithGlob'))

    # Members lists are respected.
    self.assertTrue(is_member([with_listing], joe, 'WithListing'))
    self.assertFalse(is_member([with_listing], model.Anonymous, 'WithListing'))

    # Nested groups are respected.
    self.assertTrue(is_member([with_nesting, with_listing], joe, 'WithNesting'))
    self.assertFalse(
        is_member([with_nesting, with_listing], model.Anonymous, 'WithNesting'))

  def test_list_group(self):
    list_group = (lambda groups, group, recursive:
        api.AuthDB(groups=groups).list_group(group, recursive))

    grp_1 = model.AuthGroup(id='1')
    grp_1.members.extend([
      model.Identity(model.IDENTITY_USER, 'a@example.com'),
      model.Identity(model.IDENTITY_USER, 'b@example.com'),
    ])

    grp_2 = model.AuthGroup(id='2')
    grp_2.nested.append('1')
    grp_2.members.extend([
      # Specify 'b' again, even though it's in a nested group.
      model.Identity(model.IDENTITY_USER, 'b@example.com'),
      model.Identity(model.IDENTITY_USER, 'c@example.com'),
    ])

    # Unknown group.
    self.assertEqual(set(), list_group([grp_1, grp_2], 'blah', False))
    self.assertEqual(set(), list_group([grp_1, grp_2], 'blah', True))

    # Non recursive.
    expected = set([
      model.Identity(model.IDENTITY_USER, 'b@example.com'),
      model.Identity(model.IDENTITY_USER, 'c@example.com'),
    ])
    self.assertEqual(expected, list_group([grp_1, grp_2], '2', False))

    # Recursive.
    expected = set([
      model.Identity(model.IDENTITY_USER, 'a@example.com'),
      model.Identity(model.IDENTITY_USER, 'b@example.com'),
      model.Identity(model.IDENTITY_USER, 'c@example.com'),
    ])
    self.assertEqual(expected, list_group([grp_1, grp_2], '2', True))

  def test_nested_groups_cycle(self):
    # Groups that nest each other.
    group1 = model.AuthGroup(id='Group1')
    group1.nested.append('Group2')
    group2 = model.AuthGroup(id='Group2')
    group2.nested.append('Group1')

    # Collect error messages.
    errors = []
    self.mock(api.logging, 'error', lambda *args: errors.append(args))

    # This should not hang, but produce error message.
    auth_db = api.AuthDB(groups=[group1, group2])
    self.assertFalse(
        auth_db.is_group_member('Group1', model.Anonymous))
    self.assertEqual(1, len(errors))

  def test_is_allowed_oauth_client_id(self):
    global_config = model.AuthGlobalConfig(
        oauth_client_id='1',
        oauth_additional_client_ids=['2', '3'])
    auth_db = api.AuthDB(global_config=global_config)
    self.assertFalse(auth_db.is_allowed_oauth_client_id(None))
    self.assertTrue(auth_db.is_allowed_oauth_client_id('1'))
    self.assertTrue(auth_db.is_allowed_oauth_client_id('2'))
    self.assertTrue(auth_db.is_allowed_oauth_client_id('3'))
    self.assertFalse(auth_db.is_allowed_oauth_client_id('4'))

  def test_fetch_auth_db_lazy_bootstrap(self):
    # Don't exist before the call.
    self.assertFalse(model.root_key().get())

    # Run bootstrap.
    api._lazy_bootstrap_ran = False
    api.fetch_auth_db()

    # Exist now.
    self.assertTrue(model.root_key().get())

  def test_fetch_auth_db(self):
    # Create AuthGlobalConfig.
    global_config = model.AuthGlobalConfig(key=model.root_key())
    global_config.oauth_client_id = '1'
    global_config.oauth_client_secret = 'secret'
    global_config.oauth_additional_client_ids = ['2', '3']
    global_config.put()

    # Create a bunch of (empty) groups.
    groups = [
      model.AuthGroup(key=model.group_key('Group A')),
      model.AuthGroup(key=model.group_key('Group B')),
    ]
    for group in groups:
      group.put()

    # And a bunch of secrets (local and global).
    local_secrets = [
        model.AuthSecret.bootstrap('local%d' % i, 'local') for i in (0, 1, 2)
    ]
    global_secrets = [
        model.AuthSecret.bootstrap('global%d' % i, 'global') for i in (0, 1, 2)
    ]

    # And IP whitelist.
    ip_whitelist_assignments = model.AuthIPWhitelistAssignments(
        key=model.ip_whitelist_assignments_key(),
        assignments=[
          model.AuthIPWhitelistAssignments.Assignment(
            identity=model.Anonymous,
            ip_whitelist='some ip whitelist',
          ),
        ])
    ip_whitelist_assignments.put()
    some_ip_whitelist = model.AuthIPWhitelist(
        key=model.ip_whitelist_key('some ip whitelist'),
        subnets=['127.0.0.1/32'])
    bots_ip_whitelist = model.AuthIPWhitelist(
        key=model.ip_whitelist_key('bots'),
        subnets=['127.0.0.1/32'])
    some_ip_whitelist.put()
    bots_ip_whitelist.put()

    # This all stuff should be fetched into AuthDB.
    auth_db = api.fetch_auth_db()
    self.assertEqual(global_config, auth_db.global_config)
    self.assertEqual(
        set(g.key.id() for g in groups),
        set(auth_db.groups))
    self.assertEqual(
        set(s.key.id() for s in local_secrets),
        set(auth_db.secrets['local']))
    self.assertEqual(
        set(s.key.id() for s in global_secrets),
        set(auth_db.secrets['global']))
    self.assertEqual(
        ip_whitelist_assignments,
        auth_db.ip_whitelist_assignments)
    self.assertEqual(
        {'bots': bots_ip_whitelist, 'some ip whitelist': some_ip_whitelist},
        auth_db.ip_whitelists)

  def test_get_secret(self):
    # Make AuthDB with two secrets.
    local_secret = model.AuthSecret.bootstrap('local_secret', 'local')
    global_secret = model.AuthSecret.bootstrap('global_secret', 'global')
    auth_db = api.AuthDB(secrets=[local_secret, global_secret])

    # Ensure they are accessible via get_secret.
    self.assertEqual(
        local_secret.values,
        auth_db.get_secret(api.SecretKey('local_secret', 'local')))
    self.assertEqual(
        global_secret.values,
        auth_db.get_secret(api.SecretKey('global_secret', 'global')))

  def test_get_secret_bootstrap(self):
    # Mock AuthSecret.bootstrap to capture calls to it.
    original = api.model.AuthSecret.bootstrap
    calls = []
    @classmethod
    def mocked_bootstrap(cls, name, scope):
      calls.append((name, scope))
      result = original(name, scope)
      result.values = ['123']
      return result
    self.mock(api.model.AuthSecret, 'bootstrap', mocked_bootstrap)

    auth_db = api.AuthDB()
    got = auth_db.get_secret(api.SecretKey('local_secret', 'local'))
    self.assertEqual(['123'], got)
    self.assertEqual([('local_secret', 'local')], calls)

  def test_get_secret_bad_scope(self):
    with self.assertRaises(ValueError):
      api.AuthDB().get_secret(api.SecretKey('some', 'bad-scope'))

  @staticmethod
  def make_auth_db_with_ip_whitelist():
    """AuthDB with a@example.com assigned IP whitelist '127.0.0.1/32'."""
    return api.AuthDB(
      ip_whitelists=[
        model.AuthIPWhitelist(
          key=model.ip_whitelist_key('some ip whitelist'),
          subnets=['127.0.0.1/32'],
        ),
        model.AuthIPWhitelist(
          key=model.ip_whitelist_key('bots'),
          subnets=['192.168.1.1/32', '::1/32'],
        ),
      ],
      ip_whitelist_assignments=model.AuthIPWhitelistAssignments(
        assignments=[
          model.AuthIPWhitelistAssignments.Assignment(
            identity=model.Identity(model.IDENTITY_USER, 'a@example.com'),
            ip_whitelist='some ip whitelist',)
        ],
      ),
    )

  def test_verify_ip_whitelisted_ok(self):
    # Should not raise: IP is whitelisted.
    ident = model.Identity(model.IDENTITY_USER, 'a@example.com')
    result = self.make_auth_db_with_ip_whitelist().verify_ip_whitelisted(
        ident, ipaddr.ip_from_string('127.0.0.1'))
    self.assertEqual(ident, result)

  def test_verify_ip_whitelisted_not_whitelisted(self):
    with self.assertRaises(api.AuthorizationError):
      self.make_auth_db_with_ip_whitelist().verify_ip_whitelisted(
          model.Identity(model.IDENTITY_USER, 'a@example.com'),
          ipaddr.ip_from_string('192.168.0.100'))

  def test_verify_ip_whitelisted_bot(self):
    # Should convert Anonymous as bot, 192.168.1.1 is in 'bots' whitelist.
    result = self.make_auth_db_with_ip_whitelist().verify_ip_whitelisted(
        model.Anonymous, ipaddr.ip_from_string('192.168.1.1'))
    self.assertEqual(model.Identity(model.IDENTITY_BOT, '192.168.1.1'), result)

  def test_verify_ip_whitelisted_bot_ipv6_loopback(self):
    # Should convert Anonymous as bot, 192.168.1.1 is in 'bots' whitelist.
    result = self.make_auth_db_with_ip_whitelist().verify_ip_whitelisted(
        model.Anonymous, ipaddr.ip_from_string('::1'))
    self.assertEqual(
        model.Identity(model.IDENTITY_BOT, '0-0-0-0-0-0-0-1'), result)

  def test_verify_ip_whitelisted_not_assigned(self):
    # Should not raise: whitelist is not required for another_user@example.com.
    ident = model.Identity(model.IDENTITY_USER, 'another_user@example.com')
    result = self.make_auth_db_with_ip_whitelist().verify_ip_whitelisted(
        ident, ipaddr.ip_from_string('192.168.0.100'))
    self.assertEqual(ident, result)

  def test_verify_ip_whitelisted_missing_whitelist(self):
    auth_db = api.AuthDB(
      ip_whitelist_assignments=model.AuthIPWhitelistAssignments(
        assignments=[
          model.AuthIPWhitelistAssignments.Assignment(
            identity=model.Identity(model.IDENTITY_USER, 'a@example.com'),
            ip_whitelist='missing ip whitelist',)
        ],
      ),
    )
    with self.assertRaises(api.AuthorizationError):
      auth_db.verify_ip_whitelisted(
          model.Identity(model.IDENTITY_USER, 'a@example.com'),
          ipaddr.ip_from_string('127.0.0.1'))


class TestAuthDBCache(test_case.TestCase):
  """Tests for process-global and request-local AuthDB cache."""

  def setUp(self):
    super(TestAuthDBCache, self).setUp()
    api.reset_local_state()

  def set_time(self, ts):
    """Mocks time.time() to return |ts|."""
    self.mock(api.time, 'time', lambda: ts)

  def set_fetched_auth_db(self, auth_db):
    """Mocks fetch_auth_db to return |auth_db|."""
    def mock_fetch_auth_db(known_version=None):
      if (known_version is not None and
          auth_db.entity_group_version == known_version):
        return None
      return auth_db
    self.mock(api, 'fetch_auth_db', mock_fetch_auth_db)

  def test_get_request_cache_different_threads(self):
    """Ensure get_request_cache() respects multiple threads."""
    # Runs in its own thread.
    def thread_proc():
      # get_request_cache() returns something meaningful.
      request_cache = api.get_request_cache()
      self.assertTrue(request_cache)
      # Returns same object in a context of a same request thread.
      self.assertTrue(api.get_request_cache() is request_cache)
      return request_cache

    # Launch two threads running 'thread_proc', wait for them to stop, collect
    # whatever they return.
    results_queue = Queue.Queue()
    threads = [
      threading.Thread(target=lambda: results_queue.put(thread_proc()))
      for _ in xrange(2)
    ]
    for t in threads:
      t.start()
    results = [results_queue.get() for _ in xrange(len(threads))]

    # Different threads use different RequestCache objects.
    self.assertTrue(results[0] is not results[1])

  def test_get_request_cache_different_requests(self):
    """Ensure get_request_cache() returns new object for a new request."""
    # Grab request cache for 'current' request.
    request_cache = api.get_request_cache()

    # Track calls to 'close'.
    close_calls = []
    self.mock(request_cache, 'close', lambda: close_calls.append(1))

    # Restart testbed, effectively emulating a new request on a same thread.
    self.testbed.deactivate()
    self.testbed.activate()

    # Should return a new instance of request cache now.
    self.assertTrue(api.get_request_cache() is not request_cache)
    # Old one should have been closed.
    self.assertEqual(1, len(close_calls))

  def test_get_process_auth_db_expiration(self):
    """Ensure get_process_auth_db() respects expiration."""
    # Prepare several instances of AuthDB to be used in mocks.
    auth_db_v0 = api.AuthDB(entity_group_version=0)
    auth_db_v1 = api.AuthDB(entity_group_version=1)

    # Fetch initial copy of AuthDB.
    self.set_time(0)
    self.set_fetched_auth_db(auth_db_v0)
    self.assertEqual(auth_db_v0, api.get_process_auth_db())

    # It doesn't expire for some time.
    self.set_time(api.get_process_cache_expiration_sec() - 1)
    self.set_fetched_auth_db(auth_db_v1)
    self.assertEqual(auth_db_v0, api.get_process_auth_db())

    # But eventually it does.
    self.set_time(api.get_process_cache_expiration_sec() + 1)
    self.set_fetched_auth_db(auth_db_v1)
    self.assertEqual(auth_db_v1, api.get_process_auth_db())

  def test_get_process_auth_db_known_version(self):
    """Ensure get_process_auth_db() respects entity group version."""
    # Prepare several instances of AuthDB to be used in mocks.
    auth_db_v0 = api.AuthDB(entity_group_version=0)
    auth_db_v0_again = api.AuthDB(entity_group_version=0)

    # Fetch initial copy of AuthDB.
    self.set_time(0)
    self.set_fetched_auth_db(auth_db_v0)
    self.assertEqual(auth_db_v0, api.get_process_auth_db())

    # Make cache expire, but setup fetch_auth_db to return a new instance of
    # AuthDB, but with same entity group version. Old known instance of AuthDB
    # should be reused.
    self.set_time(api.get_process_cache_expiration_sec() + 1)
    self.set_fetched_auth_db(auth_db_v0_again)
    self.assertTrue(api.get_process_auth_db() is auth_db_v0)

  def test_get_process_auth_db_multithreading(self):
    """Ensure get_process_auth_db() plays nice with multiple threads."""

    def run_in_thread(func):
      """Runs |func| in a parallel thread, returns future (as Queue)."""
      result = Queue.Queue()
      thread = threading.Thread(target=lambda: result.put(func()))
      thread.start()
      return result

    # Prepare several instances of AuthDB to be used in mocks.
    auth_db_v0 = api.AuthDB(entity_group_version=0)
    auth_db_v1 = api.AuthDB(entity_group_version=1)

    # Run initial fetch, should cache |auth_db_v0| in process cache.
    self.set_time(0)
    self.set_fetched_auth_db(auth_db_v0)
    self.assertEqual(auth_db_v0, api.get_process_auth_db())

    # Make process cache expire.
    self.set_time(api.get_process_cache_expiration_sec() + 1)

    # Start fetching AuthDB from another thread, at some point it will call
    # 'fetch_auth_db', and we pause the thread then and resume main thread.
    fetching_now = threading.Event()
    auth_db_queue = Queue.Queue()
    def mock_fetch_auth_db(**_kwargs):
      fetching_now.set()
      return auth_db_queue.get()
    self.mock(api, 'fetch_auth_db', mock_fetch_auth_db)
    future = run_in_thread(api.get_process_auth_db)

    # Wait for internal thread to call |fetch_auth_db|.
    fetching_now.wait()

    # Ok, now main thread is unblocked, while internal thread is blocking on a
    # artificially slow 'fetch_auth_db' call. Main thread can now try to get
    # AuthDB via get_process_auth_db(). It should get older stale copy right
    # away.
    self.assertEqual(auth_db_v0, api.get_process_auth_db())

    # Finish background 'fetch_auth_db' call by returning 'auth_db_v1'.
    # That's what internal thread should get as result of 'get_process_auth_db'.
    auth_db_queue.put(auth_db_v1)
    self.assertEqual(auth_db_v1, future.get())

    # Now main thread should get it as well.
    self.assertEqual(auth_db_v1, api.get_process_auth_db())

  def test_get_process_auth_db_exceptions(self):
    """Ensure get_process_auth_db() handles DB exceptions well."""
    # Prepare several instances of AuthDB to be used in mocks.
    auth_db_v0 = api.AuthDB(entity_group_version=0)
    auth_db_v1 = api.AuthDB(entity_group_version=1)

    # Fetch initial copy of AuthDB.
    self.set_time(0)
    self.set_fetched_auth_db(auth_db_v0)
    self.assertEqual(auth_db_v0, api.get_process_auth_db())

    # Make process cache expire.
    self.set_time(api.get_process_cache_expiration_sec() + 1)

    # Emulate an exception in fetch_auth_db.
    def mock_fetch_auth_db(*_kwargs):
      raise Exception('Boom!')
    self.mock(api, 'fetch_auth_db', mock_fetch_auth_db)

    # Capture calls to logging.exception.
    logger_calls = []
    self.mock(api.logging, 'exception', lambda *_args: logger_calls.append(1))

    # Should return older copy of auth_db_v0 and log the exception.
    self.assertEqual(auth_db_v0, api.get_process_auth_db())
    self.assertEqual(1, len(logger_calls))

    # Make fetch_auth_db to work again. Verify get_process_auth_db() works too.
    self.set_fetched_auth_db(auth_db_v1)
    self.assertEqual(auth_db_v1, api.get_process_auth_db())

  def test_get_request_auth_db(self):
    """Ensure get_request_auth_db() caches AuthDB in request cache."""
    # 'get_request_auth_db()' returns whatever get_process_auth_db() returns
    # when called for a first time.
    self.mock(api, 'get_process_auth_db', lambda: 'fake')
    self.assertEqual('fake', api.get_request_auth_db())

    # But then it caches it locally and reuses local copy, instead of calling
    # 'get_process_auth_db()' all the time.
    self.mock(api, 'get_process_auth_db', lambda: 'another-fake')
    self.assertEqual('fake', api.get_request_auth_db())

  def test_warmup(self):
    """Ensure api.warmup() fetches AuthDB into process-global cache."""
    self.assertFalse(api._auth_db)
    api.warmup()
    self.assertTrue(api._auth_db)


class ApiTest(test_case.TestCase):
  """Test for publicly exported API."""

  def mock_ndb_now(self, now):
    """Makes properties with |auto_now| and |auto_now_add| use mocked time."""
    self.mock(model.ndb.DateTimeProperty, '_now', lambda _: now)
    self.mock(model.ndb.DateProperty, '_now', lambda _: now.date())

  def test_get_current_identity_unitialized(self):
    """If set_current_identity wasn't called raises an exception."""
    with self.assertRaises(api.UninitializedError):
      api.get_current_identity()

  def test_get_current_identity(self):
    """Ensure get_current_identity returns whatever was put in request cache."""
    api.get_request_cache().set_current_identity(model.Anonymous)
    self.assertEqual(model.Anonymous, api.get_current_identity())

  def test_require_decorator_ok(self):
    """@require calls the callback and then decorated function."""
    callback_calls = []
    def require_callback():
      callback_calls.append(1)
      return True

    @api.require(require_callback)
    def allowed(*args, **kwargs):
      return (args, kwargs)

    self.assertEqual(((1, 2), {'a': 3}), allowed(1, 2, a=3))
    self.assertEqual(1, len(callback_calls))

  def test_require_decorator_fail(self):
    """@require raises exception and doesn't call decorated function."""
    forbidden_calls = []

    @api.require(lambda: False)
    def forbidden():
      forbidden_calls.append(1)

    with self.assertRaises(api.AuthorizationError):
      forbidden()
    self.assertFalse(forbidden_calls)

  def test_require_decorator_nesting_ok(self):
    """Permission checks are called in order."""
    calls = []
    def check(name):
      calls.append(name)
      return True

    @api.require(lambda: check('A'))
    @api.require(lambda: check('B'))
    def allowed(arg):
      return arg

    self.assertEqual('value', allowed('value'))
    self.assertEqual(['A', 'B'], calls)

  def test_require_decorator_nesting_first_deny(self):
    """First deny raises AuthorizationError."""
    calls = []
    def check(name, result):
      calls.append(name)
      return result

    forbidden_calls = []

    @api.require(lambda: check('A', False))
    @api.require(lambda: check('B', True))
    def forbidden(arg):
      forbidden_calls.append(1)

    with self.assertRaises(api.AuthorizationError):
      forbidden('value')
    self.assertFalse(forbidden_calls)
    self.assertEqual(['A'], calls)

  def test_require_decorator_nesting_non_first_deny(self):
    """Non-first deny also raises AuthorizationError."""
    calls = []
    def check(name, result):
      calls.append(name)
      return result

    forbidden_calls = []

    @api.require(lambda: check('A', True))
    @api.require(lambda: check('B', False))
    def forbidden(arg):
      forbidden_calls.append(1)

    with self.assertRaises(api.AuthorizationError):
      forbidden('value')
    self.assertFalse(forbidden_calls)
    self.assertEqual(['A', 'B'], calls)

  def test_require_decorator_on_method(self):
    calls = []
    def checker():
      calls.append(1)
      return True

    class Class(object):
      @api.require(checker)
      def method(self, *args, **kwargs):
        return (self, args, kwargs)

    obj = Class()
    self.assertEqual((obj, ('value',), {'a': 2}), obj.method('value', a=2))
    self.assertEqual(1, len(calls))

  def test_require_decorator_on_static_method(self):
    calls = []
    def checker():
      calls.append(1)
      return True

    class Class(object):
      @staticmethod
      @api.require(checker)
      def static_method(*args, **kwargs):
        return (args, kwargs)

    obj = Class()
    self.assertEqual((('value',), {'a': 2}), Class.static_method('value', a=2))
    self.assertEqual(1, len(calls))

  def test_require_decorator_on_class_method(self):
    calls = []
    def checker():
      calls.append(1)
      return True

    class Class(object):
      @classmethod
      @api.require(checker)
      def class_method(cls, *args, **kwargs):
        return (cls, args, kwargs)

    obj = Class()
    self.assertEqual(
        (Class, ('value',), {'a': 2}), Class.class_method('value', a=2))
    self.assertEqual(1, len(calls))

  def test_require_decorator_ndb_nesting_require_first(self):
    calls = []
    def checker():
      calls.append(1)
      return True

    @api.require(checker)
    @ndb.non_transactional
    def func(*args, **kwargs):
      return (args, kwargs)
    self.assertEqual((('value',), {'a': 2}), func('value', a=2))
    self.assertEqual(1, len(calls))

  def test_require_decorator_ndb_nesting_require_last(self):
    calls = []
    def checker():
      calls.append(1)
      return True

    @ndb.non_transactional
    @api.require(checker)
    def func(*args, **kwargs):
      return (args, kwargs)
    self.assertEqual((('value',), {'a': 2}), func('value', a=2))
    self.assertEqual(1, len(calls))

  def test_public_then_require_fails(self):
    with self.assertRaises(TypeError):
      @api.public
      @api.require(lambda: True)
      def func():
        pass

  def test_require_then_public_fails(self):
    with self.assertRaises(TypeError):
      @api.require(lambda: True)
      @api.public
      def func():
        pass

  def test_is_decorated(self):
    self.assertTrue(api.is_decorated(api.public(lambda: None)))
    self.assertTrue(
        api.is_decorated(api.require(lambda: True)(lambda: None)))


class OAuthAccountsTest(test_case.TestCase):
  """Test for extract_oauth_caller_identity function."""

  def mock_all(self, user_email, client_id, allowed_client_ids=()):
    class FakeUser(object):
      email = lambda _: user_email
    class FakeAuthDB(object):
      is_allowed_oauth_client_id = lambda _, cid: cid in allowed_client_ids
    self.mock(api.oauth, 'get_current_user', lambda _: FakeUser())
    self.mock(api.oauth, 'get_client_id', lambda _: client_id)
    self.mock(api, 'get_request_auth_db', FakeAuthDB)

  @staticmethod
  def user(email):
    return model.Identity(model.IDENTITY_USER, email)

  def test_is_allowed_oauth_client_id_ok(self):
    self.mock_all('email@email.com', 'some-client-id', ['some-client-id'])
    self.assertEqual(
        self.user('email@email.com'), api.extract_oauth_caller_identity())

  def test_is_allowed_oauth_client_id_not_ok(self):
    self.mock_all('email@email.com', 'some-client-id', ['another-client-id'])
    with self.assertRaises(api.AuthorizationError):
      api.extract_oauth_caller_identity()

  def test_is_allowed_oauth_client_id_not_ok_empty(self):
    self.mock_all('email@email.com', 'some-client-id')
    with self.assertRaises(api.AuthorizationError):
      api.extract_oauth_caller_identity()

  def test_gae_service_account(self):
    self.mock_all('app-id@appspot.gserviceaccount.com', 'anonymous')
    self.assertEqual(
        self.user('app-id@appspot.gserviceaccount.com'),
        api.extract_oauth_caller_identity())

  def test_gce_service_account(self):
    self.mock_all(
        '123456789123@project.gserviceaccount.com',
        '123456789123.project.googleusercontent.com')
    self.assertEqual(
        self.user('123456789123@project.gserviceaccount.com'),
        api.extract_oauth_caller_identity())

  def test_private_key_service_account(self):
    self.mock_all(
        '111111111111-abcdefghq20gfl1@developer.gserviceaccount.com',
        '111111111111-abcdefghq20gfl1.apps.googleusercontent.com')
    self.assertEqual(
        self.user('111111111111-abcdefghq20gfl1@developer.gserviceaccount.com'),
        api.extract_oauth_caller_identity())


if __name__ == '__main__':
  if '-v' in sys.argv:
    unittest.TestCase.maxDiff = None
  unittest.main()
