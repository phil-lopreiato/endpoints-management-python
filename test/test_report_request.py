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
import time
import unittest
from operator import attrgetter
from expects import be_none, equal, expect, raise_error

from google.cloud import servicecontrol as sc_messages
from google.logging.type import log_severity_pb2
from google.protobuf import struct_pb2, timestamp_pb2
from google.protobuf.json_format import ParseDict, MessageToDict

from endpoints_management.control import (caches, label_descriptor,
                                          metric_value,
                                          metric_descriptor, report_request,
                                          timestamp)


class TestReportingRules(unittest.TestCase):
    subject_cls = report_request.ReportingRules
    WANTED_LABELS = (label_descriptor.KnownLabels.REFERER,)
    WANTED_METRICS = (metric_descriptor.KnownMetrics.CONSUMER_REQUEST_COUNT,)

    def test_should_construct_with_no_args(self):
        rules = self.subject_cls()
        expect(rules).not_to(be_none)
        expect(rules.logs).to(equal(set()))
        expect(rules.metrics).to(equal(tuple()))
        expect(rules.labels).to(equal(tuple()))

    def test_should_construct_with_ok_expected_args(self):
        rules = self.subject_cls(logs=[u'wanted_log'],
                                 metrics=self.WANTED_METRICS,
                                 labels=self.WANTED_LABELS)
        expect(rules).not_to(be_none)
        expect(rules.logs).to(equal(set([u'wanted_log'])))
        expect(rules.metrics).to(equal(self.WANTED_METRICS))
        expect(rules.labels).to(equal(self.WANTED_LABELS))

    def test_should_construct_with_alt_constructor(self):
        rules = self.subject_cls.from_known_inputs()
        expect(rules).not_to(be_none)
        expect(rules.logs).to(equal(set()))
        expect(rules.metrics).to(equal(tuple()))
        expect(rules.labels).to(equal(tuple()))

    def test_should_construct_with_alt_constructor_with_ok_args(self):
        logs = [u'wanted_log', u'wanted_log']
        label_names = [x.label_name for x in self.WANTED_LABELS]
        metric_names = [x.metric_name for x in self.WANTED_METRICS]
        rules = self.subject_cls.from_known_inputs(
            logs=logs,
            label_names=label_names,
            metric_names=metric_names
        )
        expect(rules).not_to(be_none)
        expect(rules.logs).to(equal(set([u'wanted_log'])))
        expect(rules.metrics).to(equal(self.WANTED_METRICS))
        expect(rules.labels).to(equal(self.WANTED_LABELS))


_TEST_CONSUMER_ID = u'testConsumerID'
_TEST_OP1_NAME = u'testOp1'
_TEST_OP2_NAME = u'testOp2'
_WANTED_USER_AGENT = label_descriptor.USER_AGENT
_START_OF_EPOCH = datetime.datetime.utcfromtimestamp(0)
_START_OF_EPOCH_TIMESTAMP = timestamp.to_rfc3339(_START_OF_EPOCH)
_TEST_SERVICE_NAME = u'a_service_name'
_TEST_SIZE=1
_TEST_LATENCY=datetime.timedelta(seconds=7)
_EPOCH_TIMESTAMP_PB = timestamp_pb2.Timestamp().FromJsonString(_START_OF_EPOCH_TIMESTAMP)

_EXPECTED_OK_LOG_ENTRY = sc_messages.LogEntry(
    name = u'endpoints-log',
    severity = log_severity_pb2.LogSeverity.INFO,
    struct_payload=ParseDict(
        {
            u'http_response_code': 200,
            u'http_method': u'GET',
            u'request_latency_in_ms': 7000.0,
            u'timestamp': time.mktime(_START_OF_EPOCH.timetuple()),
            u'response_size': 1,
            u'request_size': 1,
            u'referer': u'a_referer',
        },
        struct_pb2.Struct()),
    timestamp=_EPOCH_TIMESTAMP_PB,
)
_EXPECTED_NOK_LOG_ENTRY = sc_messages.LogEntry(
    name = u'endpoints-log',
    severity = log_severity_pb2.LogSeverity.ERROR,
    struct_payload=ParseDict(
        {
            u'http_response_code': 404,
            u'http_method': u'GET',
            u'request_latency_in_ms': 7000.0,
            u'timestamp': time.mktime(_START_OF_EPOCH.timetuple()),
            u'response_size': 1,
            u'request_size': 1,
            u'referer': u'a_referer',
            u'error_cause': u'internal',
        },
        struct_pb2.Struct()),
    timestamp=_EPOCH_TIMESTAMP_PB,
)

_WANTED_USER_AGENT = label_descriptor.USER_AGENT
_WANTED_SERVICE_AGENT = label_descriptor.SERVICE_AGENT
_WANTED_PLATFORM = u'Unknown'

_EXPECTED_OK_METRIC = metric_descriptor.KnownMetrics.CONSUMER_REQUEST_COUNT
_EXPECTED_NOK_METRIC = metric_descriptor.KnownMetrics.CONSUMER_ERROR_COUNT
_ADD_LOG_TESTS = [
    (report_request.Info(
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        method=u'GET',
        referer=u'a_referer',
        backend_time=_TEST_LATENCY,
        overhead_time=_TEST_LATENCY,
        request_time=_TEST_LATENCY,
        request_size=_TEST_SIZE,
        response_size=_TEST_SIZE,
        service_name=_TEST_SERVICE_NAME),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         log_entries=[_EXPECTED_OK_LOG_ENTRY],
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_EPOCH_TIMESTAMP_PB,
         end_time=_EPOCH_TIMESTAMP_PB)
    ),
    (report_request.Info(
        response_code=404,
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        method=u'GET',
        referer=u'a_referer',
        backend_time=_TEST_LATENCY,
        overhead_time=_TEST_LATENCY,
        request_time=_TEST_LATENCY,
        request_size=_TEST_SIZE,
        response_size=_TEST_SIZE,
        service_name=_TEST_SERVICE_NAME),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         log_entries=[_EXPECTED_NOK_LOG_ENTRY],
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_EPOCH_TIMESTAMP_PB,
         end_time=_EPOCH_TIMESTAMP_PB)
    )
]

_TEST_API_KEY = u'test_key'
_ADD_METRICS_TESTS = [
    (report_request.Info(
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        method=u'GET',
        referer=u'a_referer',
        backend_time=_TEST_LATENCY,
        overhead_time=_TEST_LATENCY,
        request_time=_TEST_LATENCY,
        request_size=_TEST_SIZE,
        response_size=_TEST_SIZE,
        service_name=_TEST_SERVICE_NAME,
        api_key=_TEST_API_KEY,
        api_key_valid=True),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         log_entries=[],
         labels={
             u'servicecontrol.googleapis.com/service_agent':
                 _WANTED_SERVICE_AGENT,
             u'servicecontrol.googleapis.com/user_agent':
                 _WANTED_USER_AGENT,
             u'servicecontrol.googleapis.com/platform':
                 _WANTED_PLATFORM,
         },
         metric_value_sets= [
             sc_messages.MetricValueSet(
                 metric_name=_EXPECTED_OK_METRIC.metric_name,
                 metric_values=[
                     metric_value.create(int64_value=1),
                 ]
             ),
         ],
         consumer_id=u'api_key:' + _TEST_API_KEY,
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_EPOCH_TIMESTAMP_PB,
         end_time=_EPOCH_TIMESTAMP_PB)
    ),
    (report_request.Info(
        response_code=404,
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        method=u'GET',
        referer=u'a_referer',
        backend_time=_TEST_LATENCY,
        overhead_time=_TEST_LATENCY,
        request_time=_TEST_LATENCY,
        request_size=_TEST_SIZE,
        response_size=_TEST_SIZE,
        service_name=_TEST_SERVICE_NAME,
        api_key=_TEST_API_KEY,
        api_key_valid=True),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         log_entries=[],
         labels={
             u'servicecontrol.googleapis.com/service_agent':
                 _WANTED_SERVICE_AGENT,
             u'servicecontrol.googleapis.com/user_agent':
                 _WANTED_USER_AGENT,
             u'servicecontrol.googleapis.com/platform':
                 _WANTED_PLATFORM,
         },
         metric_value_sets= [
             sc_messages.MetricValueSet(
                 metric_name=_EXPECTED_OK_METRIC.metric_name,
                 metric_values=[
                     metric_value.create(int64_value=1),
                 ]
             ),
             sc_messages.MetricValueSet(
                 metric_name=_EXPECTED_NOK_METRIC.metric_name,
                 metric_values=[
                     metric_value.create(int64_value=1),
                 ]
             ),
         ],
         consumer_id=u'api_key:' + _TEST_API_KEY,
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_EPOCH_TIMESTAMP_PB,
         end_time=_EPOCH_TIMESTAMP_PB)
    ),
]

_EXPECTED_OK_LABEL = label_descriptor.KnownLabels.REFERER
_ADD_LABELS_TESTS = [
    (report_request.Info(
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        method=u'GET',
        referer=u'a_referer',
        service_name=_TEST_SERVICE_NAME),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         labels={
             _EXPECTED_OK_LABEL.label_name: u'a_referer',
             u'servicecontrol.googleapis.com/service_agent':
                 _WANTED_SERVICE_AGENT,
             u'servicecontrol.googleapis.com/user_agent':
                 _WANTED_USER_AGENT,
             u'servicecontrol.googleapis.com/platform':
                 _WANTED_PLATFORM,

         },
         log_entries=[],
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_EPOCH_TIMESTAMP_PB,
         end_time=_EPOCH_TIMESTAMP_PB)
    ),
]

KEYGETTER = attrgetter(u'key')


class TestInfo(unittest.TestCase):

    def test_should_construct_with_no_args(self):
        expect(report_request.Info()).not_to(be_none)

    def test_should_raise_if_constructed_with_a_bad_protocol(self):
        testf = lambda: report_request.Info(protocol=object())
        # not a report_request.ReportedProtocols
        expect(testf).to(raise_error(ValueError))

    def test_should_raise_if_constructed_with_a_bad_platform(self):
        testf = lambda: report_request.Info(platform=object())
        expect(testf).to(raise_error(ValueError))

    def test_should_raise_if_constructed_with_a_bad_request_size(self):
        testf = lambda: report_request.Info(request_size=object())
        expect(testf).to(raise_error(ValueError))
        testf = lambda: report_request.Info(request_size=-2)
        expect(testf).to(raise_error(ValueError))

    def test_should_raise_if_constructed_with_a_bad_response_size(self):
        testf = lambda: report_request.Info(response_size=object())
        expect(testf).to(raise_error(ValueError))
        testf = lambda: report_request.Info(response_size=-2)
        expect(testf).to(raise_error(ValueError))

    def test_should_raise_if_constructed_with_a_bad_backend_time(self):
        testf = lambda: report_request.Info(backend_time=object())
        expect(testf).to(raise_error(ValueError))

    def test_should_raise_if_constructed_with_a_bad_overhead_time(self):
        testf = lambda: report_request.Info(overhead_time=object())
        expect(testf).to(raise_error(ValueError))

    def test_should_raise_if_constructed_with_a_bad_request_time(self):
        testf = lambda: report_request.Info(request_time=object())
        expect(testf).to(raise_error(ValueError))

    def test_should_raise_if_constructed_with_a_bad_error_cause(self):
        testf = lambda: report_request.Info(error_cause=object())
        expect(testf).to(raise_error(ValueError))

    def test_should_fail_as_report_request_on_incomplete_info(self):
        timer = _DateTimeTimer()
        incomplete = report_request.Info()  # has no service_name
        rules = report_request.ReportingRules()
        testf = lambda: incomplete.as_report_request(rules, timer=timer)
        expect(testf).to(raise_error(ValueError))

    def test_should_add_expected_logs_as_report_request(self):
        timer = _DateTimeTimer()
        rules = report_request.ReportingRules(logs=[u'endpoints-log'])
        for info, want in _ADD_LOG_TESTS:
            got = info.as_report_request(rules, timer=timer)
            expect(got.service_name).to(equal(_TEST_SERVICE_NAME))
            # compare the log entry in detail to avoid instability when
            # comparing the operations directly
            wantLogEntry = want.log_entries[0]
            gotLogEntry = got.operations[0].log_entries[0]
            expect(gotLogEntry.name).to(equal(wantLogEntry.name))
            expect(gotLogEntry.timestamp).to(equal(wantLogEntry.timestamp))
            expect(gotLogEntry.severity).to(equal(wantLogEntry.severity))

            gotStruct = sc_messages.LogEntry.to_dict(gotLogEntry).get("struct_payload")
            wantStruct = sc_messages.LogEntry.to_dict(wantLogEntry).get("struct_payload")
            expect(gotStruct).to(equal(wantStruct))

    def test_should_add_expected_metric_as_report_request(self):
        timer = _DateTimeTimer()
        rules = report_request.ReportingRules(metrics=[
            _EXPECTED_OK_METRIC, _EXPECTED_NOK_METRIC
        ])
        for info, want in _ADD_METRICS_TESTS:
            got = info.as_report_request(rules, timer=timer)
            expect(got.service_name).to(equal(_TEST_SERVICE_NAME))
            expect(got.operations[0]).to(equal(want))

    def test_should_add_expected_label_as_report_request(self):
        timer = _DateTimeTimer()
        rules = report_request.ReportingRules(labels=[
            _EXPECTED_OK_LABEL
        ])
        for info, want in _ADD_LABELS_TESTS:
            got = info.as_report_request(rules, timer=timer)
            expect(got.service_name).to(equal(_TEST_SERVICE_NAME))
            expect(got.operations[0]).to(equal(want))


class TestAggregatorReport(unittest.TestCase):
    SERVICE_NAME = u'service.report'

    def setUp(self):
        self.timer = _DateTimeTimer()
        self.agg = report_request.Aggregator(
            self.SERVICE_NAME, caches.ReportOptions())

    def test_should_fail_if_req_is_bad(self):
        testf = lambda: self.agg.report(object())
        expect(testf).to(raise_error(ValueError))
        testf = lambda: self.agg.report(None)
        expect(testf).to(raise_error(ValueError))

    def test_should_fail_if_service_name_does_not_match(self):
        req = _make_test_request(self.SERVICE_NAME + u'-will-not-match')
        testf = lambda: self.agg.report(req)
        expect(testf).to(raise_error(ValueError))


class TestAggregatorTheCannotCache(unittest.TestCase):
    SERVICE_NAME = u'service.no_cache'

    def setUp(self):
        # -ve num_entries means no cache is present
        self.agg = report_request.Aggregator(
            self.SERVICE_NAME,
            caches.ReportOptions(num_entries=-1))

    def test_should_not_cache_responses(self):
        req = _make_test_request(self.SERVICE_NAME)
        expect(self.agg.report(req)).to(be_none)

    def test_should_have_empty_flush_response(self):
        expect(len(self.agg.flush())).to(equal(0))

    def test_should_have_none_as_flush_interval(self):
        expect(self.agg.flush_interval).to(be_none)


class TestCachingAggregator(unittest.TestCase):
    SERVICE_NAME = u'service.with_cache'

    def setUp(self):
        self.timer = _DateTimeTimer()
        self.flush_interval = datetime.timedelta(seconds=1)
        options = caches.ReportOptions(flush_interval=self.flush_interval)
        self.agg = report_request.Aggregator(
            self.SERVICE_NAME, options, timer=self.timer)

    def test_should_have_option_flush_interval_as_the_flush_interval(self):
        expect(self.agg.flush_interval).to(equal(self.flush_interval))

    def test_should_not_cache_requests_with_important_operations(self):
        req = _make_test_request(
            self.SERVICE_NAME,
            importance=sc_messages.Operation.Importance.HIGH)
        agg = self.agg
        expect(agg.report(req)).to(be_none)

    def test_should_cache_requests_and_return_cached_ok(self):
        req = _make_test_request(self.SERVICE_NAME, n=2, start=0)
        agg = self.agg
        expect(agg.report(req)).to(equal(report_request.Aggregator.CACHED_OK))

    def test_should_cache_requests_and_batch_them_on_flush(self):
        req1 = _make_test_request(self.SERVICE_NAME, n=2, start=0)
        req2 = _make_test_request(self.SERVICE_NAME, n=2, start=2)

        agg = self.agg
        expect(agg.report(req1)).to(equal(report_request.Aggregator.CACHED_OK))
        expect(agg.report(req2)).to(equal(report_request.Aggregator.CACHED_OK))
        # no immediate requests for flush
        flushed_reqs = agg.flush()
        expect(len(flushed_reqs)).to(equal(0))

        self.timer.tick() # time passes ...
        self.timer.tick() # ... and is now past the flush_interval
        flushed_reqs = agg.flush()
        expect(len(flushed_reqs)).to(equal(1))
        flushed_ops = flushed_reqs[0].operations
        expect(len(flushed_ops)).to(equal(4)) # number of ops in the req{1,2}

    def test_should_aggregate_operations_in_requests(self):
        n = 261 # arbitrary
        agg = self.agg
        for _ in range(n):
            # many requests, but only two ops
            req = _make_test_request(self.SERVICE_NAME, n=2, start=0)
            expect(agg.report(req)).to(
                equal(report_request.Aggregator.CACHED_OK))

        # time passes ...
        self.timer.tick()
        self.timer.tick() # ... and is now past the flush_interval
        flushed_reqs = agg.flush()
        expect(len(flushed_reqs)).to(equal(1))
        flushed_ops = flushed_reqs[0].operations
        expect(len(flushed_ops)).to(equal(2)) # many requests, but only two ops

    def test_may_clear_aggregated_operations(self):
        n = 261 # arbitrary
        agg = self.agg
        for i in range(n):
            # many requests, but only two ops
            req = _make_test_request(self.SERVICE_NAME, n=2, start=0)
            expect(agg.report(req)).to(
                equal(report_request.Aggregator.CACHED_OK))

        # time passes ...
        agg.clear()  # the aggregator is cleared
        self.timer.tick()
        self.timer.tick() # ... and is now past the flush_interval
        flushed_reqs = agg.flush()
        expect(len(flushed_reqs)).to(equal(0))  # but there is nothing


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


def _make_op_names(n, start=0):
    return (u'testOp%d' % (x,) for x in range(start, start + n))


def _make_test_request(service_name, importance=None, n=3, start=0):
    if importance is None:
        importance = sc_messages.Operation.Importance.LOW
    op_names = _make_op_names(n, start=start)
    ops = [sc_messages.Operation(consumer_id=_TEST_CONSUMER_ID,
                              operation_name=op_name,
                              importance=importance) for op_name in op_names]
    if ops:
        ops[0].labels = {u'key1': u'always add a label to the first op'}
    return sc_messages.ReportRequest(service_name=service_name, operations=ops)
