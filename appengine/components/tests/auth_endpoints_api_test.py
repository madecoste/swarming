#!/usr/bin/env python
# Copyright 2015 The Swarming Authors. All rights reserved.
# Use of this source code is governed by the Apache v2.0 license that can be
# found in the LICENSE file.

import json
import logging
import sys
import unittest

import test_env
test_env.setup_test_env()

import endpoints
from protorpc.messages import ValidationError
from protorpc.remote import protojson

import webapp2
import webtest

from support import test_case
from components import utils

from components.auth import api
from components.auth import handler
from components.auth import host_token
from components.auth import model
from components.auth import version

from components.auth.ui import endpoints_api
from components.auth.ui import rest_api
from components.auth.ui import ui


def msg_dict(request):
  return json.loads(protojson.encode_message(request))


class MembershipTest(test_case.EndpointsTestCase):

  api_service_cls = endpoints_api.AuthService

  def setUp(self):
    super(MembershipTest, self).setUp()
    handler.configure([])
    api.reset_local_state()
    self.mock(api, 'is_admin', lambda: True)
    model.AuthGroup(key=model.group_key('testgroup'), members=[]).put()
    def is_group_member_mock(group, identity):
      group = model.group_key(group).get()
      return group is not None and identity in group.members
    self.mock(api, 'is_group_member', is_group_member_mock)

  def add_group(self, group, identities):
    model.AuthGroup(key=model.group_key(group), members=[
        model.Identity.from_bytes(identity) for identity in identities]).put()

  def test_is_member_ok(self):
    """Assert that is_member correctly indicates membership in normal cases."""
    self.add_group('testgroup', ['user:mithras@hotmail.com'])

    # baphomet is not a member
    request = endpoints_api.MembershipRequest(
        group='testgroup',
        identity='user:baphomet@aol.com')
    response = self.call_api('membership', msg_dict(request), 200)
    self.assertEqual({u'is_member': False}, response.json)

    # mithras is a member
    request = endpoints_api.MembershipRequest(
        group='testgroup',
        identity='user:mithras@hotmail.com')
    response = self.call_api('membership', msg_dict(request), 200)
    self.assertEqual({u'is_member': True}, response.json)

  def test_is_member_false_for_spurious_group(self):
    """Assert that is_member returns false for nonexistent group names."""
    request = endpoints_api.MembershipRequest(
        group='wolves', identity='user:amaterasu@the.sun')
    response = self.call_api('membership', msg_dict(request), 200)
    self.assertEqual({u'is_member': False}, response.json)

  def test_is_member_adds_prefix(self):
    self.add_group('golden_egg', ['user:praj@pa.ti'])
    request = endpoints_api.MembershipRequest(
        group='golden_egg', identity='praj@pa.ti')
    response = self.call_api('membership', msg_dict(request), 200)
    self.assertEqual({u'is_member': True}, response.json)

  def test_is_member_fails_with_degenerate_request(self):
    requests = [
        endpoints_api.MembershipRequest(group='testgroup'),
        endpoints_api.MembershipRequest(identity='loki@ragna.rok')]
    for request in requests:
      with self.assertRaises(ValidationError):
        _ = self.call_api('membership', msg_dict(request), 200)

  def test_is_member_fails_with_invalid_identity(self):
    request = endpoints_api.MembershipRequest(
        group='testgroup', identity='invalid:identity')
    with self.call_should_fail('400'):
      _ = self.call_api('membership', msg_dict(request), 200)


if __name__ == '__main__':
  if '-v' in sys.argv:
    unittest.TestCase.maxDiff = None
  logging.basicConfig(
      level=logging.DEBUG if '-v' in sys.argv else logging.ERROR)
  unittest.main()
