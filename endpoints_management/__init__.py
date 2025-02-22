# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import

import logging

from . import auth, config, control

__version__ = '2.0.0.dev1'

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)

USER_AGENT = u'ESP'
SERVICE_AGENT = u'EF_PYTHON/' + __version__

__all__ = ['auth', 'config', 'control']
