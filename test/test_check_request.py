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

import http.client as httplib
import datetime
import unittest
from operator import attrgetter
from expects import be_none, equal, expect, raise_error

from google.cloud import servicecontrol as sc_messages
from google.protobuf import timestamp_pb2

from endpoints_management.control import caches, label_descriptor, timestamp
from endpoints_management.control import (check_request, metric_value)


class TestSign(unittest.TestCase):

    def setUp(self):
        op = sc_messages.Operation(
            consumer_id=_TEST_CONSUMER_ID,
            operation_name=_TEST_OP_NAME
        )
        self.test_check_request = sc_messages.CheckRequest(operation=op)
        self.test_op = op

    def test_should_fail_if_operation_is_not_set(self):
        testf = lambda: check_request.sign(sc_messages.CheckRequest())
        expect(testf).to(raise_error(ValueError))

    def test_should_fail_on_invalid_input(self):
        testf = lambda: check_request.sign(None)
        expect(testf).to(raise_error(ValueError))
        testf = lambda: check_request.sign(object())
        expect(testf).to(raise_error(ValueError))

    def test_should_fail_if_operation_has_no_operation_name(self):
        op = sc_messages.Operation(consumer_id=_TEST_CONSUMER_ID)
        testf = lambda: check_request.sign(
            sc_messages.CheckRequest(operation=op))
        expect(testf).to(raise_error(ValueError))

    def test_should_fail_if_operation_has_no_consumer_id(self):
        op = sc_messages.Operation(operation_name=_TEST_OP_NAME)
        testf = lambda: check_request.sign(
            sc_messages.CheckRequest(operation=op))
        expect(testf).to(raise_error(ValueError))

    def test_should_sign_a_valid_check_request(self):
        check_request.sign(self.test_check_request)

    def test_should_change_signature_when_labels_are_added(self):
        without_labels = check_request.sign(self.test_check_request)
        self.test_op.labels = {
            u'key1': u'value1',
            u'key2': u'value2'
        }
        self.test_check_request.operation = self.test_op
        with_labels = check_request.sign(self.test_check_request)
        expect(with_labels).not_to(equal(without_labels))

    def test_should_change_signature_when_metric_values_are_added(self):
        without_mvs = check_request.sign(self.test_check_request)
        self.test_op.metric_value_sets = [
            sc_messages.MetricValueSet(
                metric_name=u'a_float',
                metric_values=[
                    metric_value.create(
                        labels={
                            u'key1': u'value1',
                            u'key2': u'value2'},
                        double_value=1.1,
                    ),
                ]
            )
        ]
        self.test_check_request.operation = self.test_op
        with_mvs = check_request.sign(self.test_check_request)
        expect(with_mvs).not_to(equal(without_mvs))


class TestAggregatorCheck(unittest.TestCase):
    SERVICE_NAME = u'service.check'
    FAKE_OPERATION_ID = u'service.general.check'

    def setUp(self):
        self.timer = _DateTimeTimer()
        self.agg = check_request.Aggregator(
            self.SERVICE_NAME, caches.CheckOptions())

    def test_should_fail_if_req_is_bad(self):
        testf = lambda: self.agg.check(object())
        expect(testf).to(raise_error(ValueError))
        testf = lambda: self.agg.check(None)
        expect(testf).to(raise_error(ValueError))

    def test_should_fail_if_service_name_does_not_match(self):
        req = _make_test_request(self.SERVICE_NAME + u'-will-not-match')
        testf = lambda: self.agg.check(req)
        expect(testf).to(raise_error(ValueError))

    def test_should_fail_if_operation_is_missing(self):
        req = sc_messages.CheckRequest(
            service_name=self.SERVICE_NAME,
            operation=None)
        testf = lambda: self.agg.check(req)
        expect(testf).to(raise_error(ValueError))

    def test_should_return_none_initially_as_req_is_not_cached(self):
        req = _make_test_request(self.SERVICE_NAME)
        fake_response = sc_messages.CheckResponse(
            operation_id=self.FAKE_OPERATION_ID)
        agg = self.agg
        expect(agg.check(req)).to(be_none)


class TestAggregatorThatCannotCache(unittest.TestCase):
    SERVICE_NAME = u'service.no_cache'
    FAKE_OPERATION_ID = u'service.no_cache.op_id'

    def setUp(self):
        # -ve num_entries means no cache is present
        self.agg = check_request.Aggregator(
            self.SERVICE_NAME,
            caches.CheckOptions(num_entries=-1))

    def test_should_not_cache_responses(self):
        req = _make_test_request(self.SERVICE_NAME)
        fake_response = sc_messages.CheckResponse(
            operation_id=self.FAKE_OPERATION_ID)
        agg = self.agg
        expect(agg.check(req)).to(be_none)
        agg.add_response(req, fake_response)
        expect(agg.check(req)).to(be_none)
        agg.clear()
        expect(agg.check(req)).to(be_none)

    def test_should_have_empty_flush_response(self):
        expect(len(self.agg.flush())).to(equal(0))

    def test_should_have_none_as_flush_interval(self):
        expect(self.agg.flush_interval).to(be_none)



class TestCachingAggregator(unittest.TestCase):
    SERVICE_NAME = u'service.with_cache'
    FAKE_OPERATION_ID = u'service.with_cache.op_id'

    def setUp(self):
        self.timer = _DateTimeTimer()
        self.expiration = datetime.timedelta(seconds=2)
        options = caches.CheckOptions(
            flush_interval=datetime.timedelta(seconds=1),
            expiration=self.expiration)
        self.agg = check_request.Aggregator(
            self.SERVICE_NAME, options, timer=self.timer)

    def test_should_have_expiration_as_flush_interval(self):
        expect(self.agg.flush_interval).to(equal(self.expiration))

    def test_should_cache_responses(self):
        req = _make_test_request(self.SERVICE_NAME)
        fake_response = sc_messages.CheckResponse(
            operation_id=self.FAKE_OPERATION_ID)
        agg = self.agg
        expect(agg.check(req)).to(be_none)
        agg.add_response(req, fake_response)
        expect(agg.check(req)).to(equal(fake_response))

    def test_should_not_cache_requests_with_important_operations(self):
        req = _make_test_request(
            self.SERVICE_NAME,
            importance=sc_messages.Operation.Importance.HIGH)
        fake_response = sc_messages.CheckResponse(
            operation_id=self.FAKE_OPERATION_ID)
        agg = self.agg
        expect(agg.check(req)).to(be_none)
        agg.add_response(req, fake_response)
        expect(agg.check(req)).to(be_none)

    def test_signals_a_resend_on_1st_call_after_flush_interval(self):
        req = _make_test_request(self.SERVICE_NAME)
        fake_response = sc_messages.CheckResponse(
            operation_id=self.FAKE_OPERATION_ID)
        agg = self.agg
        expect(agg.check(req)).to(be_none)
        agg.add_response(req, fake_response)
        expect(agg.check(req)).to(equal(fake_response))

        # Now flush interval is reached, but not the response expiry
        self.timer.tick() # now past the flush_interval
        expect(agg.check(req)).to(be_none)  # none signals the resend

        # Until expiry, the response will continue to be returned
        expect(agg.check(req)).to(equal(fake_response))
        expect(agg.check(req)).to(equal(fake_response))

        # Once expired the cached response is no longer returned
        # expire
        self.timer.tick()
        self.timer.tick() # now expired
        expect(agg.check(req)).to(be_none)
        expect(agg.check(req)).to(be_none)  # 2nd check is None as well

    def test_signals_resend_on_1st_call_after_flush_interval_with_errors(self):
        req = _make_test_request(self.SERVICE_NAME)
        failure_code = sc_messages.CheckError.Code.NOT_FOUND
        fake_response = sc_messages.CheckResponse(
            operation_id=self.FAKE_OPERATION_ID, check_errors=[
                sc_messages.CheckError(code=failure_code)
            ])
        agg = self.agg
        expect(agg.check(req)).to(be_none)
        agg.add_response(req, fake_response)
        expect(agg.check(req)).to(equal(fake_response))

        # Now flush interval is reached, but not the response expiry
        self.timer.tick() # now past the flush_interval
        expect(agg.check(req)).to(be_none)  # first response is null

        # until expiry, the response will continue to be returned
        expect(agg.check(req)).to(equal(fake_response))
        expect(agg.check(req)).to(equal(fake_response))

        # expire
        self.timer.tick()
        self.timer.tick() # now expired
        expect(agg.check(req)).to(be_none)
        expect(agg.check(req)).to(be_none) # 2nd check is None as well

    def test_should_extend_expiration_on_receipt_of_a_response(self):
        req = _make_test_request(self.SERVICE_NAME)
        fake_response = sc_messages.CheckResponse(
            operation_id=self.FAKE_OPERATION_ID
        )
        agg = self.agg
        expect(agg.check(req)).to(be_none)
        agg.add_response(req, fake_response)
        expect(agg.check(req)).to(equal(fake_response))

        # Now flush interval is reached, but not the response expiry
        self.timer.tick() # now past the flush_interval
        expect(agg.check(req)).to(be_none)  # first response is null

        # until expiry, the response will continue to be returned
        expect(agg.check(req)).to(equal(fake_response))
        expect(agg.check(req)).to(equal(fake_response))

        # add a response as the request expires
        self.timer.tick()
        agg.add_response(req, fake_response)
        # it would have expired, but because the response was added it does not
        expect(agg.check(req)).to(equal(fake_response))
        expect(agg.check(req)).to(equal(fake_response))
        self.timer.tick() # now past the flush interval again
        expect(agg.check(req)).to(be_none)
        expect(agg.check(req)).to(equal(fake_response))

    def test_does_not_flush_request_that_has_not_been_updated(self):
        req = _make_test_request(self.SERVICE_NAME)
        fake_response = sc_messages.CheckResponse(
            operation_id=self.FAKE_OPERATION_ID
        )
        agg = self.agg
        expect(agg.check(req)).to(be_none)
        agg.add_response(req, fake_response)
        self.timer.tick() # now past the flush_interval
        expect(len(agg.flush())).to(equal(0)) # nothing expired
        self.timer.tick() # now past expiry
        self.timer.tick() # now past expiry
        expect(agg.check(req)).to(be_none)  # confirm nothing in cache
        expect(agg.check(req)).to(be_none)  # confirm nothing in cache
        expect(len(agg.flush())).to(equal(0)) # no cached check request

    def test_does_flush_requests_that_have_been_updated(self):
        req = _make_test_request(self.SERVICE_NAME)
        fake_response = sc_messages.CheckResponse(
            operation_id=self.FAKE_OPERATION_ID
        )
        agg = self.agg
        expect(agg.check(req)).to(be_none)
        agg.add_response(req, fake_response)

        expect(agg.check(req)).to(equal(fake_response))
        self.timer.tick() # now past the flush_interval
        expect(len(agg.flush())).to(equal(0)) # nothing expired
        self.timer.tick() # now past expiry
        self.timer.tick() # now past expiry
        expect(len(agg.flush())).to(equal(1)) # got the cached check request

    def test_should_clear_requests(self):
        req = _make_test_request(self.SERVICE_NAME)
        fake_response = sc_messages.CheckResponse(
            operation_id=self.FAKE_OPERATION_ID
        )
        agg = self.agg
        expect(agg.check(req)).to(be_none)
        agg.add_response(req, fake_response)
        expect(agg.check(req)).to(equal(fake_response))
        agg.clear()
        expect(agg.check(req)).to(be_none)
        expect(len(agg.flush())).to(equal(0))


_TEST_CONSUMER_ID = u'testConsumerID'
_TEST_OP_NAME = u'testOperationName'


def _make_test_request(service_name, importance=None):
    if importance is None:
        importance = sc_messages.Operation.Importance.LOW
    op = sc_messages.Operation(
        consumer_id=_TEST_CONSUMER_ID,
        operation_name=_TEST_OP_NAME,
        importance=importance
    )
    check_request = sc_messages.CheckRequest(service_name=service_name, operation=op)
    return check_request


_WANTED_USER_AGENT = label_descriptor.USER_AGENT
_WANTED_SERVICE_AGENT = label_descriptor.SERVICE_AGENT
_START_OF_EPOCH = timestamp_pb2.Timestamp().FromJsonString(timestamp.to_rfc3339(datetime.datetime(1970, 1, 1, 0, 0, 0)))
_TEST_SERVICE_NAME = u'a_service_name'
_INFO_TESTS = [
    (check_request.Info(
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        referer=u'a_referer',
        service_name=_TEST_SERVICE_NAME),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         labels = {
             u'servicecontrol.googleapis.com/user_agent': _WANTED_USER_AGENT,
             u'servicecontrol.googleapis.com/referer': u'a_referer',
             u'servicecontrol.googleapis.com/service_agent':
                 _WANTED_SERVICE_AGENT,
         },
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_START_OF_EPOCH,
         end_time=_START_OF_EPOCH)),
    (check_request.Info(
        android_cert_fingerprint=u'an_android_cert_fingerprint',
        android_package_name=u'an_android_package_name',
        api_key=u'an_api_key',
        api_key_valid=True,
        ios_bundle_id=u'an_ios_bundle_id',
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        referer=u'a_referer',
        service_name=_TEST_SERVICE_NAME),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         consumer_id=u'api_key:an_api_key',
         labels = {
             u'servicecontrol.googleapis.com/android_cert_fingerprint': u'an_android_cert_fingerprint',
             u'servicecontrol.googleapis.com/android_package_name': u'an_android_package_name',
             u'servicecontrol.googleapis.com/ios_bundle_id': u'an_ios_bundle_id',
             u'servicecontrol.googleapis.com/user_agent': _WANTED_USER_AGENT,
             u'servicecontrol.googleapis.com/referer': u'a_referer',
             u'servicecontrol.googleapis.com/service_agent':
                 _WANTED_SERVICE_AGENT,
        },
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_START_OF_EPOCH,
         end_time=_START_OF_EPOCH)),
    (check_request.Info(
        api_key=u'an_api_key',
        api_key_valid=False,
        client_ip=u'127.0.0.1',
        consumer_project_id=u'project_id',
        operation_id=u'an_op_id',
        operation_name=u'an_op_name',
        referer=u'a_referer',
        service_name=_TEST_SERVICE_NAME),
     sc_messages.Operation(
         importance=sc_messages.Operation.Importance.LOW,
         consumer_id=u'project:project_id',
         labels = {
             u'servicecontrol.googleapis.com/caller_ip': u'127.0.0.1',
             u'servicecontrol.googleapis.com/user_agent': _WANTED_USER_AGENT,
             u'servicecontrol.googleapis.com/referer': u'a_referer',
             u'servicecontrol.googleapis.com/service_agent':
                 _WANTED_SERVICE_AGENT,
         },
         operation_id=u'an_op_id',
         operation_name=u'an_op_name',
         start_time=_START_OF_EPOCH,
         end_time=_START_OF_EPOCH)),
]
_INCOMPLETE_INFO_TESTS = [
    check_request.Info(
        operation_name=u'an_op_name',
        service_name=_TEST_SERVICE_NAME),
    check_request.Info(
        operation_id=u'an_op_id',
        service_name=_TEST_SERVICE_NAME),
    check_request.Info(
        operation_id=u'an_op_id',
        operation_name=u'an_op_name')
]

KEYGETTER = attrgetter(u'key')


class TestInfo(unittest.TestCase):

    def test_should_construct_with_no_args(self):
        expect(check_request.Info()).not_to(be_none)

    def test_should_convert_using_as_check_request(self):
        timer = _DateTimeTimer()
        for info, want in _INFO_TESTS:
            got = info.as_check_request(timer=timer)
            expect(got.operation).to(equal(want))
            expect(got.service_name).to(equal(_TEST_SERVICE_NAME))

    def test_should_fail_as_check_request_on_incomplete_info(self):
        timer = _DateTimeTimer()
        for info in _INCOMPLETE_INFO_TESTS:
            testf = lambda: info.as_check_request(timer=timer)
            expect(testf).to(raise_error(ValueError))


class TestConvertResponse(unittest.TestCase):
    PROJECT_ID = u'test_convert_response'

    def test_should_be_ok_with_no_errors(self):
        code, message, _ = check_request.convert_response(
            sc_messages.CheckResponse(), self.PROJECT_ID)
        expect(code).to(equal(httplib.OK))
        expect(message).to(equal(u''))

    def test_should_include_project_id_in_error_text_when_needed(self):
        resp = sc_messages.CheckResponse(
            check_errors=[
                sc_messages.CheckError(
                    code=sc_messages.CheckError.Code.PROJECT_DELETED)
            ]
        )
        code, got, _ = check_request.convert_response(resp, self.PROJECT_ID)
        want = u'Project %s has been deleted' % (self.PROJECT_ID,)
        expect(code).to(equal(httplib.FORBIDDEN))
        expect(got).to(equal(want))

    def test_should_include_detail_in_error_text_when_needed(self):
        detail = u'details, details, details'
        resp = sc_messages.CheckResponse(
            check_errors=[
                sc_messages.CheckError(
                    code=sc_messages.CheckError.Code.IP_ADDRESS_BLOCKED,
                    detail=detail)
            ]
        )
        code, got, _ = check_request.convert_response(resp, self.PROJECT_ID)
        expect(code).to(equal(httplib.FORBIDDEN))
        expect(got).to(equal(detail))


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
