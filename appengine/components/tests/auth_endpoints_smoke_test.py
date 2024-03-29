#!/usr/bin/env python
# Copyright 2014 The Swarming Authors. All rights reserved.
# Use of this source code is governed by the Apache v2.0 license that can be
# found in the LICENSE file.

"""Smoke test for Cloud Endpoints support in auth component.

It launches app via dev_appserver and queries a bunch of cloud endpoints
methods.
"""

import unittest
import os

import test_env
test_env.setup_test_env()

from support import local_app


# /components/tests/.
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
# /components/tests/endpoints_app/.
TEST_APP_DIR = os.path.join(THIS_DIR, 'endpoints_app')


class CloudEndpointsSmokeTest(unittest.TestCase):
  def setUp(self):
    super(CloudEndpointsSmokeTest, self).setUp()
    self.app = local_app.LocalApplication(TEST_APP_DIR, 9700)
    self.app.start()
    self.app.ensure_serving()

  def tearDown(self):
    try:
      self.app.stop()
      if self.has_failed():
        self.app.dump_log()
    finally:
      super(CloudEndpointsSmokeTest, self).tearDown()

  def has_failed(self):
    # pylint: disable=E1101
    return not self._resultForDoCleanups.wasSuccessful()

  def test_smoke(self):
    self.check_who_anonymous()
    self.check_who_authenticated()
    self.check_host_token()
    self.check_forbidden()

  def check_who_anonymous(self):
    response = self.app.client.json_request('/_ah/api/testing_service/v1/who')
    self.assertEqual(200, response.http_code)
    self.assertEqual('anonymous:anonymous', response.body.get('identity'))
    self.assertIn(response.body.get('ip'), ('127.0.0.1', '0:0:0:0:0:0:0:1'))

  def check_who_authenticated(self):
    # TODO(vadimsh): Testing this requires interacting with real OAuth2 service
    # to get OAuth2 token. It's doable, but the service account secrets had to
    # be hardcoded into the source code. I'm not sure it's a good idea.
    pass

  def check_forbidden(self):
    response = self.app.client.json_request(
        '/_ah/api/testing_service/v1/forbidden')
    self.assertEqual(403, response.http_code)
    expected = {
      u'error': {
        u'code': 403,
        u'errors': [
          {
            u'domain': u'global',
            u'message': u'Forbidden',
            u'reason': u'forbidden',
          }
        ],
        u'message': u'Forbidden',
      },
    }
    self.assertEqual(expected, response.body)

  def check_host_token(self):
    # Create token first.
    response = self.app.client.json_request(
        '/_ah/api/testing_service/v1/create_host_token', {'host': 'host-name'})
    self.assertEqual(200, response.http_code)
    token = response.body.get('host_token')
    self.assertTrue(token)

    # Verify it is usable.
    response = self.app.client.json_request(
        '/_ah/api/testing_service/v1/who', headers={'X-Host-Token-V1': token})
    self.assertEqual(200, response.http_code)
    self.assertEqual('host-name', response.body.get('host'))


if __name__ == '__main__':
  unittest.main()
