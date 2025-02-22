# Copyright 2016 Google Inc. All Rights Reserved.
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

import datetime
import hashlib

import unittest
from expects import equal, expect, raise_error

from google.cloud import servicecontrol as sc_messages
from google.protobuf import timestamp_pb2
from google.type import money_pb2
from endpoints_management.control import (distribution, timestamp,
                                          metric_value)
from endpoints_management.control import MetricKind


class TestUpdateHash(unittest.TestCase):
    NOTHING_ADDED = hashlib.md5().digest()

    def make_hash(self, mv):
        md5 = hashlib.md5()
        metric_value.update_hash(md5, mv)
        return md5.digest()

    def test_should_add_nothing_without_labels_or_currency(self):
        expect(self.make_hash(sc_messages.MetricValue())).to(
            equal(self.NOTHING_ADDED))

    def test_should_add_matching_hashes_for_matching_labels(self):
        a_dict = {u'test': u'dict'}
        mv1 = metric_value.create(labels=a_dict)
        mv2 = metric_value.create(labels=a_dict)
        want = self.make_hash(mv1)
        got = self.make_hash(mv2)
        expect(got).to(equal(want))

    """
    def test_should_update_hash_for_when_currency_is_added(self):
        a_dict = {u'test': u'dict'}
        mv1 = metric_value.create(labels=a_dict)
        mv2 = metric_value.create(labels=a_dict)
        mv2.money_value= money_pb2.Money(currency_code=u'JPY')
        want = self.make_hash(mv1)
        got = self.make_hash(mv2)
        expect(got).to_not(equal(want))
    """


class TestSign(TestUpdateHash):

    def make_hash(self, mv):
        return metric_value.sign(mv)


class TestMerge(unittest.TestCase):
    A_FLOAT_VALUE = 1.0
    EARLY = timestamp_pb2.Timestamp().FromJsonString(timestamp.to_rfc3339(datetime.datetime(1970, 1, 1, 10, 0, 0)))
    LATER = timestamp_pb2.Timestamp().FromJsonString(timestamp.to_rfc3339(datetime.datetime(1990, 1, 1, 10, 0, 0)))
    TEST_LABELS = {
        u'key1': u'value1',
        u'key2': u'value2',
    }

    def setUp(self):
        self.test_value = metric_value.create(
            labels=self.TEST_LABELS,
            double_value=self.A_FLOAT_VALUE)
        self.early_ending = metric_value.create(
            labels=self.TEST_LABELS,
            double_value=self.A_FLOAT_VALUE,
            end_time=self.EARLY)
        self.late_ending = metric_value.create(
            labels=self.TEST_LABELS,
            double_value=self.A_FLOAT_VALUE,
            end_time=self.LATER)
        """
        self.test_value_with_money = metric_value.create(
            labels=self.TEST_LABELS,
            money_value=money_pb2.Money(
                currency_code=u'JPY', units=100, nanos=0))
        """

    def test_should_fail_for_metric_values_with_different_types(self):
        changed = metric_value.create(labels=self.TEST_LABELS, int64_value=1)
        for kind in (MetricKind.GAUGE, MetricKind.CUMULATIVE, MetricKind.DELTA):
            testf = lambda: metric_value.merge(kind, self.test_value, changed)
            expect(testf).to(raise_error(ValueError))

    def test_should_fail_for_uninitialized_metric_values(self):
        no_init = metric_value.create()
        for kind in (MetricKind.GAUGE, MetricKind.CUMULATIVE, MetricKind.DELTA):
            testf = lambda: metric_value.merge(kind, no_init, no_init)
            expect(testf).to(raise_error(ValueError))

    def test_should_fail_for_delta_metrics_with_unmergable_types(self):
        no_init = metric_value.create()
        unmergeables = [
            metric_value.create(string_value=u'a test string'),
            metric_value.create(bool_value=False),
        ]
        for mv in unmergeables:
            testf = lambda: metric_value.merge(MetricKind.DELTA, mv, mv)
            expect(testf).to(raise_error(ValueError))

    """
    def test_should_succeed_for_delta_metrics_with_the_money_type(self):
        v = self.test_value_with_money
        want = 2 * v.money_value.units
        got = metric_value.merge(MetricKind.DELTA, v, v)
        expect(got.money_value.units).to(equal(want))
    """

    def test_should_succeed_for_delta_metrics_with_the_double_type(self):
        v = self.test_value
        want = 2 * v.double_value
        got = metric_value.merge(MetricKind.DELTA, v, v)
        expect(got.double_value).to(equal(want))

    def test_should_succeed_for_delta_metrics_with_the_int64_type(self):
        test_int = 4
        v = metric_value.create(labels=self.TEST_LABELS, int64_value=test_int)
        want = 2 * test_int
        got = metric_value.merge(MetricKind.DELTA, v, v)
        expect(got.int64_value).to(equal(want))

    def test_should_succeed_for_delta_metrics_with_the_distribution_type(self):
        test_distribution = distribution.create_explicit([0.1, 0.3, 0.5])
        distribution.add_sample(0.4, test_distribution)
        v = metric_value.create(labels=self.TEST_LABELS,
                                distribution_value=test_distribution)
        want = 2 * test_distribution.count
        got = metric_value.merge(MetricKind.DELTA, v, v)
        expect(got.distribution_value.count).to(equal(want))

    def test_should_return_metric_value_with_latest_end_time_for_non_deltas(self):
        for kind in (MetricKind.GAUGE, MetricKind.CUMULATIVE):
            got = metric_value.merge(kind, self.early_ending, self.late_ending)
            expect(got).to(equal(self.late_ending))
            got = metric_value.merge(kind, self.late_ending, self.early_ending)
            expect(got).to(equal(self.late_ending))

    def test_should_use_the_latest_end_time_delta_merges(self):
        got = metric_value.merge(MetricKind.DELTA,
                                 self.early_ending,
                                 self.late_ending)
        expect(got.end_time).to(equal(self.late_ending.end_time))
        got = metric_value.merge(MetricKind.DELTA,
                                 self.late_ending,
                                 self.early_ending)
        expect(got.end_time).to(equal(self.late_ending.end_time))

    def test_should_use_the_earliest_start_time_in_delta_merges(self):
        early_starting = metric_value.create(
            labels=self.TEST_LABELS,
            double_value=self.A_FLOAT_VALUE,
            start_time=self.EARLY)
        late_starting = metric_value.create(
            labels=self.TEST_LABELS,
            double_value=self.A_FLOAT_VALUE,
            start_time=self.LATER)
        got = metric_value.merge(MetricKind.DELTA, early_starting,
                                 late_starting)
        expect(got.start_time).to(equal(early_starting.start_time))
        got = metric_value.merge(MetricKind.DELTA, late_starting,
                                 early_starting)
        expect(got.start_time).to(equal(early_starting.start_time))
