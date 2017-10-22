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


import bucky3.module as module


class CarbonClient(module.MetricsPushProcess, module.TCPConnector):
    def __init__(self, *args):
        super().__init__(*args, default_port=2003)

    def push_buffer(self):
        # For TCP we probably can just pump all buffer into the wire.
        self.socket = self.socket or self.get_tcp_socket(connect=True)
        payload = ''.join(self.buffer).encode("ascii")
        self.socket.sendall(payload)

    def translate_token(self, token):
        # TODO: Which chars we have to translate? There is much more to handle here.
        return token.replace('/', '_').replace('.', '_').replace('*', '_').replace('[', '_').replace(']', '_')

    def build_name(self, metadata):
        if not metadata:
            return None
        found_mappings = tuple(k for k in self.cfg['name_mapping'] if k in metadata)
        buf = [metadata.pop(k) for k in found_mappings]
        buf.extend(metadata[k] for k in sorted(metadata.keys()))
        return '.'.join(self.translate_token(t) for t in buf)

    def process_values(self, recv_timestamp, bucket, values, timestamp, metadata=None):
        for k, v in values.items():
            if metadata:
                metadata_dict = metadata.copy()
                metadata_dict.update(value=k)
            else:
                metadata_dict = dict(value=k)
            self.process_value(recv_timestamp, bucket, v, timestamp, metadata_dict)

    def process_value(self, recv_timestamp, bucket, value, timestamp, metadata=None):
        if metadata:
            metadata.update(bucket=bucket)
        else:
            metadata = dict(bucket=bucket)
        name = self.build_name(metadata)
        if name:
            if timestamp is None:
                timestamp = recv_timestamp
            self.buffer.append("%s %s %s\n" % (name, value, int(timestamp)))