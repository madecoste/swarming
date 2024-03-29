#!/usr/bin/env python
# Copyright 2015 The Swarming Authors. All rights reserved.
# Use of this source code is governed by the Apache v2.0 license that can be
# found in the LICENSE file.

import logging
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import test_env

test_env.setup_test_env()

from google.appengine.ext import ndb

from server import task_pack
from support import test_case

# pylint: disable=W0212


class TaskPackApiTest(test_case.TestCase):
  def test_all_apis_are_tested(self):
    # Ensures there's a test for each public API.
    module = task_pack
    expected = frozenset(
        i for i in dir(module)
        if i[0] != '_' and hasattr(getattr(module, i), 'func_name'))
    missing = expected - frozenset(
        i[5:] for i in dir(self) if i.startswith('test_'))
    self.assertFalse(missing)

  def test_pack_request_key(self):
    # Old style keys.
    self.assertEqual(
        '10',
       task_pack.pack_request_key(
           ndb.Key('TaskRequestShard', 'f71849', 'TaskRequest', 256)))
    # New style key.
    self.assertEqual(
        '11',
       task_pack.pack_request_key(ndb.Key('TaskRequest', 0x7fffffffffffffee)))

  def test_unpack_request_key(self):
    # Old style keys.
    self.assertEqual(
        ndb.Key('TaskRequestShard', 'f71849', 'TaskRequest', 256),
        task_pack.unpack_request_key('10'))
    # New style key.
    self.assertEqual(
        ndb.Key('TaskRequest', 0x7fffffffffffffee),
        task_pack.unpack_request_key('11'))
    with self.assertRaises(ValueError):
      task_pack.unpack_request_key('2')

  def test_request_key_to_result_summary_key(self):
    # New style key.
    request_key = task_pack.unpack_request_key('11')
    result_key = task_pack.request_key_to_result_summary_key(
        request_key)
    expected = ndb.Key(
        'TaskRequest', 0x7fffffffffffffee, 'TaskResultSummary', 1)
    self.assertEqual(expected, result_key)
    # Old style key.
    request_key = task_pack.unpack_request_key('10')
    result_key = task_pack.request_key_to_result_summary_key(
        request_key)
    expected = ndb.Key(
        'TaskRequestShard', 'f71849', 'TaskRequest', 256,
        'TaskResultSummary', 1)
    self.assertEqual(expected, result_key)

  def test_result_summary_key_to_request_key(self):
    request_key = task_pack.unpack_request_key('11')
    result_summary_key = task_pack.request_key_to_result_summary_key(
        request_key)
    actual = task_pack.result_summary_key_to_request_key(result_summary_key)
    self.assertEqual(request_key, actual)

  def test_result_summary_key_to_run_result_key(self):
    request_key = task_pack.unpack_request_key('11')
    result_summary_key = task_pack.request_key_to_result_summary_key(
        request_key)
    run_result_key = task_pack.result_summary_key_to_run_result_key(
        result_summary_key, 1)
    expected = ndb.Key(
        'TaskRequest', 0x7fffffffffffffee, 'TaskResultSummary', 1,
        'TaskRunResult', 1)
    self.assertEqual(expected, run_result_key)
    run_result_key = task_pack.result_summary_key_to_run_result_key(
        result_summary_key, 2)
    expected = ndb.Key(
        'TaskRequest', 0x7fffffffffffffee, 'TaskResultSummary', 1,
        'TaskRunResult', 2)
    self.assertEqual(expected, run_result_key)

    with self.assertRaises(ValueError):
      task_pack.result_summary_key_to_run_result_key(result_summary_key, 0)
    with self.assertRaises(NotImplementedError):
      task_pack.result_summary_key_to_run_result_key(result_summary_key, 3)

  def test_run_result_key_to_result_summary_key(self):
    request_key = task_pack.unpack_request_key('11')
    result_summary_key = task_pack.request_key_to_result_summary_key(
        request_key)
    run_result_key = task_pack.result_summary_key_to_run_result_key(
        result_summary_key, 1)
    self.assertEqual(
        result_summary_key,
        task_pack.run_result_key_to_result_summary_key(run_result_key))

  def test_pack_result_summary_key(self):
    request_key = task_pack.unpack_request_key('11')
    result_summary_key = task_pack.request_key_to_result_summary_key(
        request_key)
    run_result_key = task_pack.result_summary_key_to_run_result_key(
        result_summary_key, 1)

    actual = task_pack.pack_result_summary_key(result_summary_key)
    self.assertEqual('110', actual)

    with self.assertRaises(AssertionError):
      task_pack.pack_result_summary_key(run_result_key)

  def test_pack_run_result_key(self):
    request_key = task_pack.unpack_request_key('11')
    result_summary_key = task_pack.request_key_to_result_summary_key(
        request_key)
    run_result_key = task_pack.result_summary_key_to_run_result_key(
        result_summary_key, 1)
    self.assertEqual('111', task_pack.pack_run_result_key(run_result_key))

    with self.assertRaises(AssertionError):
      task_pack.pack_run_result_key(result_summary_key)

  def test_unpack_result_summary_key(self):
    # New style key.
    actual = task_pack.unpack_result_summary_key('bb80210')
    expected = ndb.Key(
        'TaskRequest', 0x7fffffffff447fde, 'TaskResultSummary', 1)
    self.assertEqual(expected, actual)
    # Old style key.
    actual = task_pack.unpack_result_summary_key('bb80200')
    expected = ndb.Key(
        'TaskRequestShard', '6f4236', 'TaskRequest', 196608512,
        'TaskResultSummary', 1)
    self.assertEqual(expected, actual)

    with self.assertRaises(ValueError):
      task_pack.unpack_result_summary_key('0')
    with self.assertRaises(ValueError):
      task_pack.unpack_result_summary_key('g')
    with self.assertRaises(ValueError):
      task_pack.unpack_result_summary_key('bb80201')

  def test_unpack_run_result_key(self):
    # New style key.
    for i in ('1', '2'):
      actual = task_pack.unpack_run_result_key('bb8021' + i)
      expected = ndb.Key(
          'TaskRequest', 0x7fffffffff447fde,
          'TaskResultSummary', 1, 'TaskRunResult', int(i))
      self.assertEqual(expected, actual)
    # Old style key.
    for i in ('1', '2'):
      actual = task_pack.unpack_run_result_key('bb8020' + i)
      expected = ndb.Key(
          'TaskRequestShard', '6f4236', 'TaskRequest', 196608512,
          'TaskResultSummary', 1, 'TaskRunResult', int(i))
      self.assertEqual(expected, actual)

    with self.assertRaises(ValueError):
      task_pack.unpack_run_result_key('1')
    with self.assertRaises(ValueError):
      task_pack.unpack_run_result_key('g')
    with self.assertRaises(ValueError):
      task_pack.unpack_run_result_key('bb80200')
    with self.assertRaises(NotImplementedError):
      task_pack.unpack_run_result_key('bb80203')


if __name__ == '__main__':
  if '-v' in sys.argv:
    unittest.TestCase.maxDiff = None
  logging.basicConfig(
      level=logging.DEBUG if '-v' in sys.argv else logging.ERROR)
  unittest.main()
