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
import unittest
from expects import be_none, expect, equal, raise_error

from google.cloud import servicecontrol as sc_messages
from google.protobuf import timestamp_pb2
from endpoints_management.control import (metric_value, operation, timestamp)
from endpoints_management.control import MetricKind

_A_FLOAT_VALUE = 1.1
_REALLY_EARLY = timestamp_pb2.Timestamp().FromJsonString(timestamp.to_rfc3339(datetime.datetime(1970, 1, 1, 0, 0, 0)))
_EARLY = timestamp_pb2.Timestamp().FromJsonString(timestamp.to_rfc3339(datetime.datetime(1980, 1, 1, 10, 0, 0)))
_LATER = timestamp_pb2.Timestamp().FromJsonString(timestamp.to_rfc3339(datetime.datetime(1980, 2, 2, 10, 0, 0)))
_LATER_STILL = timestamp_pb2.Timestamp().FromJsonString(timestamp.to_rfc3339(datetime.datetime(1981, 2, 2, 10, 0, 0)))

_TEST_LABELS = {
    u'key1': u'value1',
    u'key2': u'value2',
}

# in tests, the description field is not currently used, but should be filled
_TESTS = [
    {
        u'description': u'update the start time to that of the earliest',
        u'kinds': None,
        u'initial': sc_messages.Operation(
            start_time=_EARLY,
            end_time=_LATER
        ),
        u'ops': [
            sc_messages.Operation(
                start_time=_REALLY_EARLY,
                end_time=_LATER
            ),
            sc_messages.Operation(
                start_time=_LATER,
                end_time=_LATER
            ),
        ],
        u'want': sc_messages.Operation(start_time=_REALLY_EARLY, end_time=_LATER)
    },
    {
        u'description': u'update the end time to that of the latest',
        u'kinds': None,
        u'initial': sc_messages.Operation(
            start_time=_EARLY,
            end_time=_LATER
        ),
        u'ops': [
            sc_messages.Operation(
                start_time=_EARLY,
                end_time=_LATER
            ),
            sc_messages.Operation(
                start_time=_EARLY,
                end_time=_LATER_STILL
            ),
        ],
        u'want': sc_messages.Operation(start_time=_EARLY, end_time=_LATER_STILL)
    },
    {
        u'description': u'combine the log entries',
        u'kinds': None,
        u'initial': sc_messages.Operation(
            start_time=_EARLY,
            end_time=_LATER,
            log_entries=[sc_messages.LogEntry(text_payload=u'initial')]
        ),
        u'ops': [
            sc_messages.Operation(
                start_time=_EARLY,
                end_time=_LATER,
                log_entries=[sc_messages.LogEntry(text_payload=u'agg1')]
            ),
            sc_messages.Operation(
                start_time=_EARLY,
                end_time=_LATER,
                log_entries=[sc_messages.LogEntry(text_payload=u'agg2')]
            ),
        ],
        u'want': sc_messages.Operation(
            start_time=_EARLY,
            end_time=_LATER,
            log_entries=[
                sc_messages.LogEntry(text_payload=u'initial'),
                sc_messages.LogEntry(text_payload=u'agg1'),
                sc_messages.LogEntry(text_payload=u'agg2')
            ]
        )
    },
    {
        u'description': u'combines the metric value using the default kind',
        u'kinds': None,
        u'initial': sc_messages.Operation(
            start_time=_EARLY,
            end_time=_LATER,
            metric_value_sets = [
                sc_messages.MetricValueSet(
                    metric_name=u'some_floats',
                    metric_values=[
                        metric_value.create(
                            labels=_TEST_LABELS,
                            double_value=_A_FLOAT_VALUE,
                            end_time=_EARLY
                        ),
                    ]
                ),
                sc_messages.MetricValueSet(
                    metric_name=u'other_floats',
                    metric_values=[
                        metric_value.create(
                            labels=_TEST_LABELS,
                            double_value=_A_FLOAT_VALUE,
                            end_time=_EARLY
                        ),
                    ]
                )
            ]
        ),
        u'ops': [
            sc_messages.Operation(
                start_time=_EARLY,
                end_time=_LATER,
                metric_value_sets= [
                    sc_messages.MetricValueSet(
                        metric_name=u'some_floats',
                        metric_values=[
                            metric_value.create(
                                labels=_TEST_LABELS,
                                double_value=_A_FLOAT_VALUE,
                                end_time=_LATER
                            ),
                        ]
                    ),
                ]
            ),
            sc_messages.Operation(
                start_time=_EARLY,
                end_time=_LATER,
                metric_value_sets= [
                    sc_messages.MetricValueSet(
                        metric_name=u'other_floats',
                        metric_values=[
                            metric_value.create(
                                labels=_TEST_LABELS,
                                double_value=_A_FLOAT_VALUE,
                                end_time=_LATER_STILL
                            ),
                        ]
                    )
                ]

            ),
        ],
        u'want': sc_messages.Operation(
            start_time=_EARLY,
            end_time=_LATER,
            metric_value_sets= [
                sc_messages.MetricValueSet(
                    metric_name=u'other_floats',
                    metric_values=[
                        metric_value.create(
                            labels=_TEST_LABELS,
                            double_value=_A_FLOAT_VALUE * 2,
                            end_time=_LATER_STILL
                        ),
                    ]
                ),
                sc_messages.MetricValueSet(
                    metric_name=u'some_floats',
                    metric_values=[
                        metric_value.create(
                            labels=_TEST_LABELS,
                            double_value=_A_FLOAT_VALUE * 2,
                            end_time=_LATER
                        ),
                    ]
                )
            ]
        )
    },
    {
        u'description': u'combines a metric value using a kind that is not DELTA',
        u'kinds': {u'some_floats': MetricKind.GAUGE },
        u'initial': sc_messages.Operation(
            start_time=_EARLY,
            end_time=_LATER,
            metric_value_sets=[
                sc_messages.MetricValueSet(
                    metric_name=u'some_floats',
                    metric_values=[
                        metric_value.create(
                            labels=_TEST_LABELS,
                            double_value=_A_FLOAT_VALUE,
                            end_time=_EARLY,
                        ),
                    ]
                ),
                sc_messages.MetricValueSet(
                    metric_name=u'other_floats',
                    metric_values=[
                        metric_value.create(
                            labels=_TEST_LABELS,
                            double_value=_A_FLOAT_VALUE,
                            end_time=_EARLY
                        ),
                    ]
                )
            ]
        ),
        u'ops': [
            sc_messages.Operation(
                start_time=_EARLY,
                end_time=_LATER,
                metric_value_sets= [
                    sc_messages.MetricValueSet(
                        metric_name=u'some_floats',
                        metric_values=[
                            metric_value.create(
                                labels=_TEST_LABELS,
                                double_value=_A_FLOAT_VALUE,
                                end_time=_LATER
                            ),
                        ]
                    ),
                ]
            ),
            sc_messages.Operation(
                start_time=_EARLY,
                end_time=_LATER,
                metric_value_sets=[
                    sc_messages.MetricValueSet(
                        metric_name=u'other_floats',
                        metric_values=[
                            metric_value.create(
                                labels=_TEST_LABELS,
                                double_value=_A_FLOAT_VALUE,
                                end_time=_LATER_STILL
                            ),
                        ]
                    )
                ]

            ),
        ],
        u'want': sc_messages.Operation(
            start_time=_EARLY,
            end_time=_LATER,
            metric_value_sets=[
                sc_messages.MetricValueSet(
                    metric_name=u'other_floats',
                    metric_values=[
                        metric_value.create(
                            labels=_TEST_LABELS,
                            double_value=_A_FLOAT_VALUE * 2,
                            end_time=_LATER_STILL
                        ),
                    ]
                ),
                sc_messages.MetricValueSet(
                    metric_name=u'some_floats',
                    metric_values=[
                        metric_value.create(
                            labels=_TEST_LABELS,
                            double_value=_A_FLOAT_VALUE,
                            end_time=_LATER
                        ),
                    ]
                )
            ]
        )
    }
]

class TestOperationAggregation(unittest.TestCase):

    def test_should_aggregate_as_expected(self):
        for t in _TESTS:
            desc = t[u'description']
            initial = t[u'initial']
            want = t[u'want']
            agg = operation.Aggregator(initial, kinds=t[u'kinds'])
            for o in t[u'ops']:
                agg.add(o)
                got = agg.as_operation()
            try:
                expect(got).to(equal(want))
            except AssertionError as e:
                raise AssertionError(u'Failed to {0}\n{1}'.format(desc, e))


_INFO_TESTS = [
    (operation.Info(
        referer=u'a_referer',
        service_name=u'a_service_name'),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         start_time=_REALLY_EARLY,
         end_time=_REALLY_EARLY)),
    (operation.Info(
        operation_id=u'an_op_id',
        referer=u'a_referer',
        service_name=u'a_service_name'),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         operation_id=u'an_op_id',
         start_time=_REALLY_EARLY,
         end_time=_REALLY_EARLY)),
    (operation.Info(
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        referer=u'a_referer',
        service_name=u'a_service_name'),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_REALLY_EARLY,
         end_time=_REALLY_EARLY)),
    (operation.Info(
        android_cert_fingerprint=u'an_android_cert_fingerprint',
        android_package_name=u'an_android_package_name',
        api_key=u'an_api_key',
        api_key_valid=True,
        ios_bundle_id=u'an_ios_bundle_id',
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        referer=u'a_referer',
        service_name=u'a_service_name'),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         consumer_id=u'api_key:an_api_key',
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_REALLY_EARLY,
         end_time=_REALLY_EARLY)),
    (operation.Info(
        api_key=u'an_api_key',
        api_key_valid=False,
        consumer_project_id=u'project_id',
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        referer=u'a_referer',
        service_name=u'a_service_name'),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         consumer_id=u'project:project_id',
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_REALLY_EARLY,
         end_time=_REALLY_EARLY)),
]

class TestInfo(unittest.TestCase):

    def test_should_construct_with_no_args(self):
        expect(operation.Info()).not_to(be_none)

    def test_should_convert_to_operation_ok(self):
        timer = _DateTimeTimer()
        for info, want in _INFO_TESTS:
            expect(info.as_operation(timer=timer)).to(equal(want))


class _DateTimeTimer(object):
    def __init__(self, auto=False):
        self.auto = auto
        self.time = datetime.datetime.utcfromtimestamp(0)

    def __call__(self):
        if self.auto:
            self.tick()
        return self.time

    def tick(self):
        self.time += datetime.timedelta(seconds=1)
