# -*- coding: utf-8 -
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#
# Copyright 2011 Cloudant, Inc.

import six
import sys
import time
import socket
import struct
import logging
try:
    import cPickle as pickle
except ImportError:
    import pickle

import bucky.client as client


if six.PY3:
    xrange = range


log = logging.getLogger(__name__)


def _get_host_trim():
    global __host_trim__
    if __host_trim__ is not None:
        return __host_trim__
    host_trim = cfg.name_host_trim
    __host_trim__ = []
    for s in host_trim:
        s = list(reversed([p.strip() for p in s.split(".")]))
        __host_trim__.append(s)
    return __host_trim__


def hostname(host):
    host_trim = _get_host_trim()
    parts = host.split(".")
    parts = list(reversed([p.strip() for p in parts]))
    for s in host_trim:
        same = True
        for i, p in enumerate(s):
            if p != parts[i]:
                same = False
                break
        if same:
            parts = parts[len(s):]
            return parts
    return parts


def strip_duplicates(parts):
    ret = []
    for p in parts:
        if len(ret) == 0 or p != ret[-1]:
            ret.append(p)
    return ret


def statname(host, name):
    nameparts = name.split('.')
    parts = []
    if cfg.name_prefix:
        parts.append(cfg.name_prefix)
    if cfg.name_prefix_parts:
        parts.extend(cfg.name_prefix_parts)
    if host:
        parts.extend(hostname(host))
    parts.extend(nameparts)
    if cfg.name_postfix_parts:
        parts.extend(cfg.name_postfix_parts)
    if cfg.name_postfix:
        parts.append(cfg.name_postfix)
    if cfg.name_replace_char is not None:
        parts = [p.replace(".", cfg.name_replace_char) for p in parts]
    if cfg.name_strip_duplicates:
        parts = strip_duplicates(parts)
    return ".".join(parts)


class DebugSocket(object):
    def sendall(self, data):
        sys.stdout.write(data)


class CarbonClient(client.Client):
    def __init__(self, cfg, pipe):
        super(CarbonClient, self).__init__(pipe)
        self.debug = cfg.debug
        self.ip = cfg.graphite_ip
        self.port = cfg.graphite_port
        self.max_reconnects = cfg.graphite_max_reconnects
        self.reconnect_delay = cfg.graphite_reconnect_delay
        self.backoff_factor = cfg.graphite_backoff_factor
        self.backoff_max = cfg.graphite_backoff_max
        if self.max_reconnects <= 0:
            self.max_reconnects = sys.maxint
        self.connected = False

    def connect(self):
        if self.debug:
            log.debug("Connected the debug socket.")
            self.sock = DebugSocket()
            return
        reconnect_delay = self.reconnect_delay
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        for i in xrange(self.max_reconnects):
            try:
                self.sock.connect((self.ip, self.port))
                self.connected = True
                log.info("Connected to Carbon at %s:%s", self.ip, self.port)
                return
            except socket.error as e:
                if i >= self.max_reconnects:
                    raise
                log.error("Failed to connect to %s:%s: %s", self.ip, self.port, e)
                if reconnect_delay > 0:
                    time.sleep(reconnect_delay)
                    if self.backoff_factor:
                        reconnect_delay *= self.backoff_factor
                        if self.backoff_max:
                            reconnect_delay = min(reconnect_delay, self.backoff_max)
        raise socket.error("Failed to connect to %s:%s after %s attempts" % (self.ip, self.port, self.max_reconnects))

    def reconnect(self):
        self.close()
        self.connect()

    def close(self):
        try:
            self.sock.close()
        except:
            pass
        self.connected = False

    def send_message(self, mesg):
        if not self.connected:
            self.connect()
        self.sock.sendall(mesg)


class PlaintextClient(CarbonClient):
    def send(self, host, name, value, mtime, metadata=None):
        stat = statname(host, name)
        mesg = "%s %s %s\n" % (stat, value, mtime)
        for i in xrange(self.max_reconnects):
            try:
                self.send_message(mesg)
                return
            except socket.error as err:
                log.error("Failed to send data to Carbon server: %s", err)
                try:
                    self.reconnect()
                except socket.error as err:
                    log.error("Failed reconnect to Carbon server: %s", err)
        log.error("Dropping message %s", mesg)


class PickleClient(CarbonClient):
    def __init__(self, cfg, pipe):
        super(PickleClient, self).__init__(cfg, pipe)
        self.buffer_size = cfg.graphite_pickle_buffer_size
        self.buffer = []

    def send(self, host, name, value, mtime, metadata=None):
        stat = statname(host, name)
        self.buffer.append((stat, (mtime, value)))
        if len(self.buffer) >= self.buffer_size:
            self.transmit()

    def transmit(self):
        payload = pickle.dumps(self.buffer, protocol=-1)
        header = struct.pack("!L", len(payload))
        self.buffer = []
        for i in xrange(self.max_reconnects):
            try:
                self.send_message(header + payload)
                return
            except socket.error as err:
                log.error("Failed to send data to Carbon server: %s", err)
                try:
                    self.reconnect()
                except socket.error as err:
                    log.error("Failed reconnect to Carbon server: %s", err)
        log.error("Dropping buffer!")
