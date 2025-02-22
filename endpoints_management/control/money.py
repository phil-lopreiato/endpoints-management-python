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

"""money provides funcs for working with `Money` instances.

:func:`check_valid` determines if a `Money` instance is valid
:func:`add` adds two `Money` instances together

"""

from __future__ import absolute_import

import logging
import sys

from google.type import money_pb2

_logger = logging.getLogger(__name__)

_INT64_MAX = sys.maxsize
_INT64_MIN = -sys.maxsize - 1
_BILLION = 1000000000
MAX_NANOS = _BILLION - 1
_MSG_3_LETTERS_LONG = u'The currency code is not 3 letters long'
_MSG_UNITS_NANOS_MISMATCH = u'The signs of the units and nanos do not match'
_MSG_NANOS_OOB = u'The nanos field must be between -999999999 and 999999999'


def check_valid(money):
    """Determine if an instance of `Money` is valid.

    Args:
      money (:class:`endpoints_management.gen.servicecontrol_v1_messages.Money`): the
        instance to test

    Raises:
      ValueError: if the money instance is invalid
    """
    if not isinstance(money, money_pb2.Money):
        raise ValueError(u'Inputs should be of type %s' % (money_pb2.Money,))
    currency = money.currency_code
    if not currency or len(currency) != 3:
        raise ValueError(_MSG_3_LETTERS_LONG)
    units = money.units
    nanos = money.nanos
    if ((units > 0) and (nanos < 0)) or ((units < 0) and (nanos > 0)):
        raise ValueError(_MSG_UNITS_NANOS_MISMATCH)
    if abs(nanos) > MAX_NANOS:
        raise ValueError(_MSG_NANOS_OOB)


def add(a, b, allow_overflow=False):
    """Adds two instances of `Money`.

    Args:
      a (:class:`endpoints_management.gen.servicecontrol_v1_messages.Money`): one money
        value
      b (:class:`endpoints_management.gen.servicecontrol_v1_messages.Money`): another
        money value
      allow_overflow: determines if the addition is allowed to overflow

    Return:
      `Money`: an instance of Money

    Raises:
      ValueError: if the inputs do not have the same currency code
      OverflowError: if the sum overflows and allow_overflow is not `True`
    """
    for m in (a, b):
        if not isinstance(m, money_pb2.Money):
            raise ValueError(u'Inputs should be of type %s' % (money_pb2.Money,))
    if a.currency_code != b.currency_code:
        raise ValueError(u'Money values need the same currency to be summed')
    nano_carry, nanos_sum = _sum_nanos(a, b)
    units_sum_no_carry = a.units + b.units
    units_sum = units_sum_no_carry + nano_carry

    # Adjust when units_sum and nanos_sum have different signs
    if units_sum > 0 and nanos_sum < 0:
        units_sum -= 1
        nanos_sum += _BILLION
    elif units_sum < 0 and nanos_sum > 0:
        units_sum += 1
        nanos_sum -= _BILLION

    # Return the result, detecting overflow if it occurs
    sign_a = _sign_of(a)
    sign_b = _sign_of(b)
    if sign_a > 0 and sign_b > 0 and units_sum >= _INT64_MAX:
        if not allow_overflow:
            raise OverflowError(u'Money addition positive overflow')
        else:
            return money_pb2.Money(units=_INT64_MAX,
                                     nanos=MAX_NANOS,
                                     currency_code=a.currency_code)
    elif (sign_a < 0 and sign_b < 0 and
          (units_sum_no_carry <= -_INT64_MAX or units_sum <= -_INT64_MAX)):
        if not allow_overflow:
            raise OverflowError(u'Money addition negative overflow')
        else:
            return money_pb2.Money(units=_INT64_MIN,
                                     nanos=-MAX_NANOS,
                                     currency_code=a.currency_code)
    else:
        return money_pb2.Money(units=units_sum,
                                 nanos=nanos_sum,
                                 currency_code=a.currency_code)


def _sum_nanos(a, b):
    the_sum = a.nanos + b.nanos
    carry = 0
    if the_sum > _BILLION:
        carry = 1
        the_sum -= _BILLION
    elif the_sum <= -_BILLION:
        carry = -1
        the_sum += _BILLION
    return carry, the_sum


def _sign_of(money):
    """Determines the amount sign of a money instance

    Args:
      money (:class:`endpoints_management.gen.servicecontrol_v1_messages.Money`): the
        instance to test

    Return:
      int: 1, 0 or -1

    """
    units = money.units
    nanos = money.nanos
    if units:
        if units > 0:
            return 1
        elif units < 0:
            return -1
    if nanos:
        if nanos > 0:
            return 1
        elif nanos < 0:
            return -1
    return 0
