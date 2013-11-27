# Copyright 2013 The Swarming Authors. All rights reserved.
# Use of this source code is governed by the Apache v2.0 license that can be
# found in the LICENSE file.

import os

import jinja2


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

JINJA = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(ROOT_DIR, 'templates')),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


def get(*args, **kwargs):
  return JINJA.get_template(*args, **kwargs)