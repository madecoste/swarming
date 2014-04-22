# Copyright 2014 The Swarming Authors. All rights reserved.
# Use of this source code is governed by the Apache v2.0 license that can be
# found in the LICENSE file.

"""Tasks definition.

Each user request creates a new TaskRequest. The TaskRequest instance saves the
metadata of the request, e.g. who requested it, when why, etc. It links to the
actual data of the request in a TaskProperties. The TaskProperties represents
everything needed to run the task.

This means if two users request an identical task, it can be deduped
accordingly and efficiently by the scheduler.

Note that the mere existence of a TaskRequest in the db doesn't mean it will be
scheduled, see task_scheduler.py for the actual scheduling. Registering tasks
and scheduling are kept separated to keep the immutable and mutable models in
separate files.


Overview of transactions:
- TaskRequest() are created inside a transaction.


Graph of the schema:
    +------Root------+
    |TaskRequestShard|
    +----------------+
            ^
            |
  +---------------------+
  |TaskRequest          |
  |    +--------------+ |
  |    |TaskProperties| |
  |    +--------------+ |
  +---------------------+
        ^
        |
  <See task_shard_to_run.py and task_result.py>

TaskProperties is embedded in TaskRequest. TaskProperties is still declared as a
separate entity to clearly declare the boundary for task request deduplication.
"""


import datetime
import hashlib
import json
import random

from google.appengine.ext import ndb

from components import datastore_utils
from components import utils
from server import task_common


# One day in seconds. Add 10s to account for small jitter.
_ONE_DAY_SECS = 24*60*60 + 10


# Minimum value for timeouts.
_MIN_TIMEOUT_SECS = 30


# Parameters for new_request().
# The content of the 'data' parameter. This relates to the context of the
# request, e.g. who wants to run a task.
_DATA_KEYS = frozenset(
    ['name', 'priority', 'properties', 'scheduling_expiration_secs', 'user'])
# The content of 'properties' inside the 'data' parameter. This relates to the
# task itself, e.g. what to run.
_PROPERTIES_KEYS = frozenset(
    ['commands', 'data', 'dimensions', 'env', 'execution_timeout_secs',
     'io_timeout_secs', 'number_shards'])


### Properties validators must come before the models.


def _validate_is_json_internal(prop, value, required):
  """Validates and enforce the data is in expected json encoded format."""
  decoded = json.loads(value)
  if not decoded and required:
    # pylint: disable=W0212
    raise ValueError('%s is required' % prop._name)
  # Reencodes as strict internal encoding.
  return utils.encode_to_json(decoded), decoded


def _validate_command(prop, value):
  """Validates TaskProperties.command_json."""
  encoded, decoded = _validate_is_json_internal(prop, value, True)
  if (not isinstance(decoded, list) or
      not all(isinstance(i, list) for i in decoded)):
    # pylint: disable=W0212
    raise ValueError(
        '%s must be a list of commands, each a list of arguments' % prop._name)
  return encoded


def _validate_data(prop, value):
  """Validates TaskProperties.data_json."""
  decoded = json.loads(value)
  if (not isinstance(decoded, list) or
      not all(isinstance(i, list) and len(i) == 2 for i in decoded)):
    # pylint: disable=W0212
    raise ValueError('%s must be a list of (url, file)' % prop._name)
  # Reencodes as strict internal encoding.
  return utils.encode_to_json(sorted(decoded))


def _validate_dict_of_strings(prop, value):
  """Validates TaskProperties.dimension_json and TaskProperties.env_json."""
  encoded, decoded = _validate_is_json_internal(prop, value, False)
  if (not isinstance(decoded, dict) or
      not all(
        isinstance(k, unicode) and isinstance(v, unicode)
        for k, v in decoded.iteritems())):
    # pylint: disable=W0212
    raise ValueError('%s must be a dict of strings' % prop._name)
  return encoded


def _validate_number_shards(prop, value):
  if (0 >= value or task_common.MAXIMUM_SHARDS < value):
    # pylint: disable=W0212
    raise ValueError(
        '%s (%d) must be between 1 and %s (inclusive)' %
        (prop._name, value, task_common.MAXIMUM_SHARDS))
  return value


def _validate_timeout(prop, value):
  """Validates timeouts in seconds in TaskProperties."""
  if _MIN_TIMEOUT_SECS > value or _ONE_DAY_SECS < value:
    # pylint: disable=W0212
    raise ValueError(
        '%s (%ds) must be between %ds and one day' %
            (prop._name, value, _MIN_TIMEOUT_SECS))


def _validate_priority(_prop, value):
  """Validates TaskRequest.priority."""
  task_common.validate_priority(value)
  return value


def _validate_expiration(prop, value):
  now = task_common.utcnow()
  offset = int(round((value - now).total_seconds()))
  if _MIN_TIMEOUT_SECS > offset or _ONE_DAY_SECS < offset:
    # pylint: disable=W0212
    raise ValueError(
        '%s (%s, %ds from now) must effectively be between %ds and one day '
        'from now (%s)' %
        (prop._name, value, offset, _MIN_TIMEOUT_SECS, now))


### Models.


class TaskProperties(ndb.Model):
  """Defines all the properties of a task to be run on the Swarming
  infrastructure.

  This entity is not saved in the DB as a standalone entity, instead it is
  embedded in a TaskRequest.

  TODO(maruel): Determine which of the below that are necessary.
  Things not caried over from TestCase:
  - TestObject.decorate_output
  - TestCase.cleanup, we always use the same value?
  - TestCase.encoding, enforce utf-8
  - TestCase.restart_on_failure, probably needed
  - TestCase.verbose, use env var instead.
  - TestCase.working_dir, not sure. this is cheezy.
  - TestObject.hard_time_out, per command execution timeout, only global.
  - TestObject.io_time_out, I/O timeout, per command execution timeout, only
    global.

  This model is immutable.
  """
  # Hashing algorithm used to hash TaskProperties to create its key.
  HASHING_ALGO = hashlib.sha1

  # Commands to run. It is a list of lists. Each command is run one after the
  # other. Encoded json.
  commands_json = ndb.StringProperty(indexed=False, validator=_validate_command)

  # List of (URLs, local file) for the bot to download. Encoded as json. Must be
  # sorted by URLs. Optional.
  data_json = ndb.StringProperty(indexed=False, validator=_validate_data)

  # Filter to use to determine the required properties on the bot to run on. For
  # example, Windows or hostname. Encoded as json. Optional but highly
  # recommended.
  dimensions_json = ndb.StringProperty(
      indexed=False, validator=_validate_dict_of_strings)

  # Environment variables. Encoded as json. Optional.
  env_json = ndb.StringProperty(
      indexed=False, validator=_validate_dict_of_strings)

  # Number of instances to split this task into.
  number_shards = ndb.IntegerProperty(
      indexed=False, validator=_validate_number_shards)

  # Maximum duration the bot can take to run a shard of this task.
  execution_timeout_secs = ndb.IntegerProperty(
      indexed=True, validator=_validate_timeout)

  # Bot controlled timeout for new bytes from the subprocess. If a subprocess
  # doesn't output new data to stdout for .io_timeout_secs, consider the command
  # timed out. Optional.
  io_timeout_secs = ndb.IntegerProperty(
      indexed=True, validator=_validate_timeout)

  def commands(self):
    return json.loads(self.commands_json)

  def data(self):
    return json.loads(self.data_json)

  def dimensions(self):
    return json.loads(self.dimensions_json)

  def env(self):
    return json.loads(self.env_json)

  def to_dict(self):
    return {
      'commands': self.commands(),
      'data': self.data(),
      'dimensions': self.dimensions(),
      'env': self.env(),
      'execution_timeout_secs': self.execution_timeout_secs,
      'io_timeout_secs': self.io_timeout_secs,
      'number_shards': self.number_shards,
    }


class TaskRequest(ndb.Model):
  """Contains a user request.

  The key is a increasing integer based on time since task_common.UNIX_EPOCH
  plus some randomness on 8 low order bits then lower 8 bits set to 0. See
  _new_request_key() for the complete gory details.

  This model is immutable.
  """
  created_ts = ndb.DateTimeProperty()

  # The name for this test request.
  name = ndb.StringProperty()

  # User who requested this task.
  user = ndb.StringProperty()

  # TaskProperties value as generated by TaskProperties.HASHING_ALGO. It
  # uniquely identify the TaskProperties instance for an eventual deduplication
  # by the task scheduler.
  properties_hash = datastore_utils.BytesComputedProperty(
      lambda self: self._calculate_hash())  # pylint: disable=W0212

  # The actual properties are embedded in this model.
  properties = ndb.LocalStructuredProperty(TaskProperties, compressed=True)

  # Priority of the task to be run. A lower number is higher priority, thus will
  # preempt requests with lower priority (higher numbers).
  priority = ndb.IntegerProperty(indexed=False, validator=_validate_priority)

  # If the task request is not scheduled by this moment, it will be aborted by a
  # cron job. It is saved instead of scheduling_expiration_secs so finding
  # expired jobs is a simple query.
  expiration_ts = ndb.DateTimeProperty(
      indexed=True, validator=_validate_expiration)

  @property
  def scheduling_expiration_secs(self):
    """Reconstructs this value from expiration_ts and created_ts."""
    return (self.expiration_ts - self.created_ts).total_seconds()

  def to_dict(self):
    """Converts properties_hash to hex so it is json serializable."""
    out = super(TaskRequest, self).to_dict()
    out['properties_hash'] = out['properties_hash'].encode('hex')
    out['properties'] = self.properties.to_dict()
    return out

  def _calculate_hash(self):
    """Calculates the hash for the embedded TaskProperties.

    Used to calculate the value of self.properties_hash.
    """
    return self.properties.HASHING_ALGO(
        utils.encode_to_json(self.properties)).digest()


def _new_request_key():
  """Returns a valid ndb.Key for this entity.

  Key id is a 64 bit integer:
  - 1 bit highest order bit to detect overflow.
  - 47 bits is time since epoch at 1ms resolution is
    2**47 / 365 / 24 / 60 / 60 / 1000 = 4462 years.
  - 8 bits of randomness reduces to 2**-7 the probability of collision on exact
    same timestamp at 1ms resolution, so a maximum theoretical rate of 256000
    requests per second but an effective rate likely in the range of ~2560
    requests per second without too much transaction conflicts.
  - The last 8 bits are used for sharding on TaskShardToRun and are kept to 0
    here for key compatibility.
  """
  now = task_common.milliseconds_since_epoch(None)
  assert 1 <= now < 2**47, now
  suffix = random.getrandbits(8)
  assert 0 <= suffix <= 0xFF
  value = (now << 16) | (suffix << 8)
  return id_to_request_key(value)


def _put_request(request):
  """Puts the new TaskRequest in the DB.

  Returns:
    ndb.Key of the new entity. Returns None if failed, which should be surfaced
    to the user.
  """
  assert not request.key
  request.key = _new_request_key()
  return datastore_utils.insert(request, _new_request_key)


### Public API.


def id_to_request_key(task_id):
  """Returns the ndb.Key for a TaskRequest id."""
  if task_id & 0xFF:
    raise ValueError('Unexpected low order byte is set')
  parent = datastore_utils.hashed_shard_key(
      str(task_id), task_common.SHARDING_LEVEL, 'TaskRequestShard')
  return ndb.Key(TaskRequest, task_id, parent=parent)


def new_request(data):
  """Constructs a TaskRequest out of a yet-to-be-specified API.

  Argument:
  - data: dict with:
    - name
    - user
    - properties
      - commands
      - data
      - dimensions
      - env
      - execution_timeout_secs
      - io_timeout_secs
      - number_shards
    - priority
    - scheduling_expiration_secs

  Returns:
    The newly created TaskRequest.
  """
  # Save ourself headaches with typos and refuses unexpected values.
  set_data = frozenset(data)
  if set_data != _DATA_KEYS:
    raise ValueError(
        'Unexpected parameters for new_request(): %s\nExpected: %s' % (
            ', '.join(sorted(_DATA_KEYS.symmetric_difference(set_data))),
            ', '.join(sorted(_DATA_KEYS))))
  data_properties = data['properties']
  set_data_properties = frozenset(data_properties)
  if set_data_properties != _PROPERTIES_KEYS:
    raise ValueError(
        'Unexpected properties for new_request(): %s\nExpected: %s' % (
            ', '.join(sorted(
                _PROPERTIES_KEYS.symmetric_difference(set_data_properties))),
            ', '.join(sorted(_PROPERTIES_KEYS))))

  # The following is very important to be deterministic. Keys must be sorted,
  # encoding must be deterministic.
  commands_json = utils.encode_to_json(data_properties['commands'])
  data_json = utils.encode_to_json(sorted(data_properties['data']))
  dimensions_json = utils.encode_to_json(data_properties['dimensions'])
  env_json = utils.encode_to_json(data_properties['env'])
  properties = TaskProperties(
      commands_json=commands_json,
      data_json=data_json,
      dimensions_json=dimensions_json,
      env_json=env_json,
      number_shards=data_properties['number_shards'],
      execution_timeout_secs=data_properties['execution_timeout_secs'],
      io_timeout_secs=data_properties['io_timeout_secs'])

  now = task_common.utcnow()
  expiration_ts = now + datetime.timedelta(
      seconds=data['scheduling_expiration_secs'])
  request = TaskRequest(
      created_ts=now,
      name=data['name'],
      user=data['user'],
      properties=properties,
      priority=data['priority'],
      expiration_ts=expiration_ts)
  if _put_request(request):
    return request
  return None