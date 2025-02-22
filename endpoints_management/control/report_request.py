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

"""report_request supports aggregation of ReportRequests.

It proves :class:`.Aggregator` that aggregates and batches together
ReportRequests.

"""


from __future__ import absolute_import

from builtins import range
from builtins import object
import collections
import functools
import hashlib
import logging
import time
from datetime import datetime, timedelta

from google.cloud import servicecontrol as sc_messages
from google.logging.type import log_severity_pb2 as log_severity
from google.protobuf import struct_pb2, timestamp_pb2
from google.protobuf.json_format import ParseDict

from enum import Enum
from . import caches, label_descriptor, operation
from . import metric_descriptor, signing, timestamp
from .. import USER_AGENT, SERVICE_AGENT

_logger = logging.getLogger(__name__)

NOT_SET = -1


def _validate_int_arg(name, value):
    if value == NOT_SET or (isinstance(value, int) and value >= 0):
        return
    raise ValueError(u'%s should be a non-negative int/long' % (name,))


def _validate_timedelta_arg(name, value):
    if value is None or isinstance(value, timedelta):
        return
    raise ValueError(u'%s should be a timedelta' % (name,))


class ReportingRules(collections.namedtuple(u'ReportingRules',
                                            [u'logs', u'metrics', u'labels'])):
    """Holds information that determines how to fill a `ReportRequest`.

    Attributes:
      logs (iterable[string]): the name of logs to be included in the `ReportRequest`
      metrics (iterable[:class:`endpoints_management.control.metric_descriptor.KnownMetrics`]):
        the metrics to be added to a `ReportRequest`
      labels (iterable[:class:`endpoints_management.control.metric_descriptor.KnownLabels`]):
        the labels to be added to a `ReportRequest`
    """
    # pylint: disable=too-few-public-methods

    def __new__(cls, logs=None, metrics=None, labels=None):
        """Invokes the base constructor with default values."""
        logs = set(logs) if logs else set()
        metrics = tuple(metrics) if metrics else tuple()
        labels = tuple(labels) if labels else tuple()
        return super(cls, ReportingRules).__new__(cls, logs, metrics, labels)

    @classmethod
    def from_known_inputs(cls, logs=None, metric_names=None, label_names=None):
        """An alternate constructor that assumes known metrics and labels.

        This differs from the default constructor in that the metrics and labels
        are iterables of names of 'known' metrics and labels respectively. The
        names are used to obtain the metrics and labels from
        :class:`endpoints_management.control.metric_descriptor.KnownMetrics` and
        :class:`endpoints_management.control.label_descriptor.KnownLabels` respectively.

        names that don't correspond to a known metric or label are ignored; as
        are metrics or labels that don't yet have a way of updating the
        `ReportRequest` operation.

        Args:
          logs (iterable[string]): the name of logs to be included in the
            `ReportRequest`
          metric_names (iterable[string]): the name of a known metric to be
            added to the `ReportRequest`
          label_names (iterable[string]): the name of a known label to be added
            to the `ReportRequest`

        """
        if not metric_names:
            metric_names = ()
        if not label_names:
            label_names = ()
        known_labels = []
        known_metrics = []
        # pylint: disable=no-member
        # pylint is not aware of the __members__ attributes
        for l in list(label_descriptor.KnownLabels.__members__.values()):
            if l.update_label_func and l.label_name in label_names:
                known_labels.append(l)
        for m in list(metric_descriptor.KnownMetrics.__members__.values()):
            if m.update_op_func and m.metric_name in metric_names:
                known_metrics.append(m)
        return cls(logs=logs, metrics=known_metrics, labels=known_labels)


class ReportedProtocols(Enum):
    """Enumerates the protocols that can be reported."""
    # pylint: disable=too-few-public-methods
    UNKNOWN = 0
    HTTP = 1
    HTTP2 = 2
    GRPC = 3


class ReportedPlatforms(Enum):
    """Enumerates the platforms that can be reported."""
    # pylint: disable=too-few-public-methods
    UNKNOWN = 0
    GAE_FLEX = 1
    GAE_STANDARD = 2
    GCE = 3
    GKE = 4
    DEVELOPMENT = 5

    def friendly_string(self):
        if self.name == u'UNKNOWN':
            return u'Unknown'
        elif self.name == u'GAE_FLEX':
            return u'GAE Flex'
        elif self.name == u'GAE_STANDARD':
            return u'GAE Standard'
        elif self.name == u'DEVELOPMENT':
            return u'GAE Dev Server'
        else:
            return self.name


class ErrorCause(Enum):
    """Enumerates the causes of errors."""
    # pylint: disable=too-few-public-methods
    internal = 0  # default, error in scc library code
    application = 1  # external application error
    auth = 2  # authentication error
    service_control = 3  # error in service control check


# alias the severity enum
_SEVERITY = log_severity.LogSeverity


def _struct_payload_from(a_dict):
    struct_pb = struct_pb2.Struct()
    return ParseDict(a_dict, struct_pb)


_KNOWN_LABELS = label_descriptor.KnownLabels


class Info(
        collections.namedtuple(
            u'Info', (
                u'api_name',
                u'api_method',
                u'api_version',
                u'auth_issuer',
                u'auth_audience',
                u'backend_time',
                u'consumer_project_number',
                u'error_cause',
                u'location',
                u'log_message',
                u'method',
                u'overhead_time',
                u'platform',
                u'producer_project_id',
                u'protocol',
                u'request_size',
                u'request_time',
                u'response_code',
                u'response_size',
                u'url',
            ) + operation.Info._fields),
        operation.Info):
    """Holds the information necessary to fill in a ReportRequest.

    In the attribute descriptions below, N/A means 'not available'

    Attributes:
       api_name (string): the api name and version
       api_method (string): the full api method name
       api_version (string): the api version
       auth_issuer (string): the auth issuer
       auth_audience (string): the auth audience
       backend_time(datetime.timedelta): the backend request time, None for N/A
       consumer_project_number(int): the project number of the consumer, as
           returned by the check request
       error_cause(:class:`ErrorCause`): the cause of error if one has occurred
       location (string): the location of the service
       log_message (string): a message to log as an info log
       method (string): the HTTP method used to make the request
       overhead_time(datetime.timedelta): the overhead time, None for N/A
       platform (:class:`ReportedPlatform`): the platform in use
       producer_project_id (string): the producer project id
       protocol (:class:`ReportedProtocol`): the protocol used
       request_size(int): the request size in bytes, -1 means N/A
       request_time(datetime.timedelta): the request time
       response_size(int): the request size in bytes, -1 means N/A
       response_code(int): the code of the http response
       url (string): the request url

    """
    # pylint: disable=too-many-arguments,too-many-locals

    COPYABLE_LOG_FIELDS = [
        u'api_name',
        u'api_method',
        u'api_key',
        u'producer_project_id',
        u'referer',
        u'location',
        u'log_message',
        u'url',
    ]

    def __new__(cls,
                api_name=u'',
                api_method=u'',
                api_version=u'',
                auth_issuer=u'',
                auth_audience=u'',
                backend_time=None,
                consumer_project_number=NOT_SET,
                error_cause=ErrorCause.internal,
                location=u'',
                log_message=u'',
                method=u'',
                overhead_time=None,
                platform=ReportedPlatforms.UNKNOWN,
                producer_project_id=u'',
                protocol=ReportedProtocols.UNKNOWN,
                request_size=NOT_SET,
                request_time=None,
                response_size=NOT_SET,
                response_code=200,
                url=u'',
                **kw):
        """Invokes the base constructor with default values."""
        op_info = operation.Info(**kw)
        _validate_timedelta_arg(u'backend_time', backend_time)
        _validate_timedelta_arg(u'overhead_time', overhead_time)
        _validate_timedelta_arg(u'request_time', request_time)
        _validate_int_arg(u'request_size', request_size)
        _validate_int_arg(u'response_size', response_size)
        if not isinstance(protocol, ReportedProtocols):
            raise ValueError(u'protocol should be a %s' % (ReportedProtocols,))
        if not isinstance(platform, ReportedPlatforms):
            raise ValueError(u'platform should be a %s' % (ReportedPlatforms,))
        if not isinstance(error_cause, ErrorCause):
            raise ValueError(u'error_cause should be a %s' % (ErrorCause,))
        return super(cls, Info).__new__(
            cls,
            api_name,
            api_method,
            api_version,
            auth_issuer,
            auth_audience,
            backend_time,
            consumer_project_number,
            error_cause,
            location,
            log_message,
            method,
            overhead_time,
            platform,
            producer_project_id,
            protocol,
            request_size,
            request_time,
            response_code,
            response_size,
            url,
            **op_info._asdict())

    def _as_log_entry(self, name, now):
        """Makes a `LogEntry` from this instance for the given log_name.

        Args:
          rules (:class:`ReportingRules`): determines what labels, metrics and
            logs to include in the report request.
          now (:class:`datetime.DateTime`): the current time

        Return:
          a ``LogEntry`` generated from this instance with the given name
          and timestamp

        Raises:
          ValueError: if the fields in this instance are insufficient to
            to create a valid ``ServicecontrolServicesReportRequest``

        """
        # initialize the struct with fields that are always present
        d = {
            u'http_response_code': self.response_code,
            u'timestamp': time.mktime(now.timetuple())
        }

        # compute the severity
        severity = _SEVERITY.INFO
        if self.response_code >= 400:
            severity = _SEVERITY.ERROR
            d[u'error_cause'] = self.error_cause.name

        # add 'optional' fields to the struct
        if self.request_size > 0:
            d[u'request_size'] = self.request_size
        if self.response_size > 0:
            d[u'response_size'] = self.response_size
        if self.method:
            d[u'http_method'] = self.method
        if self.request_time:
            d[u'request_latency_in_ms'] = self.request_time.total_seconds() * 1000

        # add 'copyable' fields to the struct
        for key in self.COPYABLE_LOG_FIELDS:
            value = getattr(self, key, None)
            if value:
                d[key] = value

        return sc_messages.LogEntry(
            name=name,
            timestamp=timestamp_pb2.Timestamp().FromJsonString(timestamp.to_rfc3339(now)),
            severity=severity,
            struct_payload=_struct_payload_from(d))

    def as_report_request(self, rules, timer=datetime.utcnow):
        """Makes a `ServicecontrolServicesReportRequest` from this instance

        Args:
          rules (:class:`ReportingRules`): determines what labels, metrics and
            logs to include in the report request.
          timer: a function that determines the current time

        Return:
          a ``ServicecontrolServicesReportRequest`` generated from this instance
          governed by the provided ``rules``

        Raises:
          ValueError: if the fields in this instance cannot be used to create
            a valid ``ServicecontrolServicesReportRequest``

        """
        if not self.service_name:
            raise ValueError(u'the service name must be set')
        op = super(Info, self).as_operation(timer=timer)

        # Populate metrics and labels if they can be associated with a
        # method/operation
        if op.operation_id and op.operation_name:
            labels = {}
            for known_label in rules.labels:
                known_label.do_labels_update(self, labels)

            # Forcibly add system label reporting here, as the base service
            # config does not specify it as a label.
            labels[_KNOWN_LABELS.SCC_PLATFORM.label_name] = (
                self.platform.friendly_string())
            labels[_KNOWN_LABELS.SCC_SERVICE_AGENT.label_name] = (
                SERVICE_AGENT)
            labels[_KNOWN_LABELS.SCC_USER_AGENT.label_name] = USER_AGENT

            if labels:
                op.labels = labels
            for known_metric in rules.metrics:
                known_metric.do_operation_update(self, op)

        # Populate the log entries
        now = timer()
        op.log_entries = [self._as_log_entry(l, now) for l in rules.logs]

        return sc_messages.ReportRequest(
            service_name=self.service_name,
            operations=[op])


_NO_RESULTS = tuple()


class Aggregator(object):
    """Aggregates Service Control Report requests.

    :func:`report` determines if a `ReportRequest` should be sent to the
    service immediately

    """

    CACHED_OK = object()
    """A sentinel returned by :func:`report` when a request is cached OK."""

    MAX_OPERATION_COUNT = 1000
    """The maximum number of operations to send in a report request."""

    def __init__(self, service_name, options, kinds=None,
                 timer=datetime.utcnow):
        """
        Constructor

        Args:
          service_name (string): name of the service being aggregagated
          options (:class:`endpoints_management.caches.ReportOptions`): configures the behavior
            of this aggregator
          kinds (dict[string, [:class:`.MetricKind`]]): describes the
            type of metrics used during aggregation
          timer (function([[datetime]]): a function that returns the current
            as a time as a datetime instance

        """
        self._cache = caches.create(options, timer=timer)
        self._options = options
        self._kinds = kinds
        self._service_name = service_name

    @property
    def flush_interval(self):
        """The interval between calls to flush.

        Returns:
           timedelta: the period between calls to flush if, or ``None`` if no
           cache is set

        """
        return None if self._cache is None else self._options.flush_interval

    @property
    def service_name(self):
        """The service to which all requests being aggregated should belong."""
        return self._service_name

    def flush(self):
        """Flushes this instance's cache.

        The driver of this instance should call this method every
        `flush_interval`.

        Returns:
          list[``ServicecontrolServicesReportRequest``]: corresponding to the
            pending cached operations

        """
        if self._cache is None:
            return _NO_RESULTS
        with self._cache as c:
            flushed_ops = [x.as_operation() for x in c.out_deque]
            c.out_deque.clear()
            reqs = []
            max_ops = self.MAX_OPERATION_COUNT
            for x in range(0, len(flushed_ops), max_ops):
                report_request = sc_messages.ReportRequest(
                    service_name=self.service_name,
                    operations=flushed_ops[x:x + max_ops])
                reqs.append(report_request)

            return reqs

    def clear(self):
        """Clears the cache."""
        if self._cache is None:
            return _NO_RESULTS
        if self._cache is not None:
            with self._cache as k:
                res = [x.as_operation() for x in list(k.values())]
                k.clear()
                k.out_deque.clear()
                return res

    def report(self, req):
        """Adds a report request to the cache.

        Returns ``None`` if it could not be aggregated, and callers need to
        send the request to the server, otherwise it returns ``CACHED_OK``.

        Args:
           req (:class:`sc_messages.ReportRequest`): the request
             to be aggregated

        Result:
           ``None`` if the request as not cached, otherwise ``CACHED_OK``

        """
        if self._cache is None:
            return None  # no cache, send request now
        if not isinstance(req, sc_messages.ReportRequest):
            raise ValueError(u'Invalid request')
        if req.service_name != self.service_name:
            _logger.error(u'bad report(): service_name %s does not match ours %s',
                          req.service_name, self.service_name)
            raise ValueError(u'Service name mismatch')
        report_req = req
        if not report_req:
            _logger.error(u'bad report(): no report_request in %s', req)
            raise ValueError(u'Expected report_request not set')
        if _has_high_important_operation(report_req) or self._cache is None:
            return None
        ops_by_signature = _key_by_signature(report_req.operations,
                                             _sign_operation)

        # Concurrency:
        #
        # This holds a lock on the cache while updating it.  No i/o operations
        # are performed, so any waiting threads see minimal delays
        with self._cache as cache:
            for key, op in list(ops_by_signature.items()):
                agg = cache.get(key)
                if agg is None:
                    cache[key] = operation.Aggregator(op, self._kinds)
                else:
                    agg.add(op)

        return self.CACHED_OK


def _has_high_important_operation(req):
    def is_important(op):
        return (op.importance !=
                sc_messages.Operation.Importance.LOW)

    return functools.reduce(lambda x, y: x and is_important(y),
                            req.operations, True)


def _key_by_signature(operations, signature_func):
    """Creates a dictionary of operations keyed by signature

    Args:
      operations (iterable[Operations]): the input operations

    Returns:
       dict[string, [Operations]]: the operations keyed by signature
    """
    return dict((signature_func(op), op) for op in operations)


def _sign_operation(op):
    """Obtains a signature for an operation in a ReportRequest.

    Args:
       op (:class:`endpoints_management.gen.servicecontrol_v1_messages.Operation`): an
         operation used in a `ReportRequest`

    Returns:
       string: a unique signature for that operation
    """
    md5 = hashlib.md5()
    md5.update(op.consumer_id.encode('utf-8'))
    md5.update(b'\x00')
    md5.update(op.operation_name.encode('utf-8'))
    if op.labels:
        sorted_labels = {k: op.labels[k] for k in sorted(op.labels)}
        signing.add_dict_to_hash(md5, sorted_labels)
    return md5.digest()
