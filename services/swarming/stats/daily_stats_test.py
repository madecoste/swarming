#!/usr/bin/env python
# Copyright 2013 The Swarming Authors. All rights reserved.
# Use of this source code is governed by the Apache v2.0 license that can be
# found in the LICENSE file.

"""Tests for DailyStats class."""


import datetime
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import test_env

test_env.setup_test_env()

from google.appengine.ext import ndb
from google.appengine.ext import testbed

from stats import daily_stats
from stats import runner_stats

# The amount of time (in minutes) that every runner took to get assigned.
WAIT_TIME = 2

# The amount of time (in minutes) that every runner took to run.
RUNNING_TIME = 3


def _AddRunner(end_time, success, timeout):
  assigned_time = end_time - datetime.timedelta(minutes=RUNNING_TIME)
  created_time = assigned_time - datetime.timedelta(minutes=WAIT_TIME)

  runner = runner_stats.RunnerStats(
      test_case_name='name', dimensions='xp', num_instances=0,
      instance_index=0, created_time=created_time, assigned_time=assigned_time,
      end_time=end_time, success=success, timed_out=timeout,
      automatic_retry_count=0)
  runner.put()

  return runner


class DailyStatsTest(unittest.TestCase):
  def setUp(self):
    # Setup the app engine test bed.
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_all_stubs()

  def tearDown(self):
    self.testbed.deactivate()

  def testGenerateDailyStatsTwice(self):
    current_day = datetime.datetime.utcnow().date()

    self.assertTrue(daily_stats.GenerateDailyStats(current_day))
    self.assertFalse(daily_stats.GenerateDailyStats(current_day))

  def testGenerateDailyStatsWithBasicInfo(self):
    current_day = datetime.datetime.utcnow().date()

    # Add 1 sucess, 2 regular failures, and 1 failure due to a timeout.
    _AddRunner(datetime.datetime.combine(current_day, datetime.time()),
               success=True, timeout=False)
    _AddRunner(datetime.datetime.combine(current_day, datetime.time()),
               success=False, timeout=False)
    _AddRunner(datetime.datetime.combine(current_day, datetime.time()),
               success=False, timeout=False)
    _AddRunner(datetime.datetime.combine(current_day, datetime.time()),
               success=False, timeout=True)

    # Add a runner from yesterday and tomorrow and ensure they are ignored.
    _AddRunner(datetime.datetime.combine(
        current_day + datetime.timedelta(days=1), datetime.time()),
               success=True, timeout=False)
    _AddRunner(datetime.datetime.combine(
        current_day - datetime.timedelta(days=1), datetime.time()),
               success=True, timeout=False)

    self.assertTrue(daily_stats.GenerateDailyStats(current_day))
    self.assertEqual(1, daily_stats.DailyStats.query().count())

    daily_stat = daily_stats.DailyStats.query().get()
    self.assertEqual(4, daily_stat.shards_finished)
    self.assertEqual(2, daily_stat.shards_failed)
    self.assertEqual(1, daily_stat.shards_timed_out)
    self.assertEqual(WAIT_TIME * 4, daily_stat.total_wait_time)
    self.assertEqual(RUNNING_TIME * 4, daily_stat.total_running_time)

  def testGenerateDailyStatsWithAbortedRunner(self):
    current_day = datetime.datetime.utcnow().date()

    runner = _AddRunner(datetime.datetime.combine(current_day, datetime.time()),
                        success=False, timeout=False)

    # If a runner is never run and is aborted because we never see a machine
    # that can run it, it will lack an assigned time.
    runner.assigned_time = None
    runner.put()

    self.assertTrue(daily_stats.GenerateDailyStats(current_day))

    daily_stat = daily_stats.DailyStats.query().get()
    self.assertEqual(0, daily_stat.shards_finished)

  def testGetDailyStats(self):
    current_day = datetime.datetime.utcnow().date()
    days_to_add = 7
    for i in range(days_to_add):
      day = current_day - datetime.timedelta(days=i)
      daily_stat = daily_stats.DailyStats(date=day)
      daily_stat.put()

    # Check just getting one day.
    stats = daily_stats.GetDailyStats(current_day)
    self.assertEqual(1, len(stats))
    self.assertEqual(current_day, stats[0].date)

    # Check getting all days.
    stats = daily_stats.GetDailyStats(
        current_day - datetime.timedelta(days=days_to_add))
    self.assertEqual(days_to_add, len(stats))
    self.assertEqual(current_day - datetime.timedelta(days=days_to_add - 1),
                     stats[0].date)
    self.assertEqual(current_day, stats[-1].date)

  def testDeleteOldDailyStats(self):
    current_day = datetime.datetime.utcnow().date()

    # Add a daily stats model that shouldn't get deleted.
    daily_stat = daily_stats.DailyStats(date=current_day)
    daily_stat.put()

    ndb.Future.wait_all(daily_stats.DeleteOldDailyStats())
    self.assertEqual(1, daily_stats.DailyStats.query().count())

    # Add a daily stats model that should get deleted.
    daily_stat = daily_stats.DailyStats(
        date=(current_day -
              datetime.timedelta(days=daily_stats.DAILY_STATS_LIFE_IN_DAYS +
                                 1)))
    daily_stat.put()
    self.assertEqual(2, daily_stats.DailyStats.query().count())

    # Ensure the correct model is deleted.
    ndb.Future.wait_all(daily_stats.DeleteOldDailyStats())
    self.assertEqual(1, daily_stats.DailyStats.query().count())

    remaining_model = daily_stats.DailyStats.query().get()
    self.assertEqual(current_day, remaining_model.date)


if __name__ == '__main__':
  unittest.main()