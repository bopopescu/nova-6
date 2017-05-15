# (c) Copyright 2015 - 2017  StorPool
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock

from nova.tests.unit.virt.libvirt.volume import test_volume
from nova.virt.libvirt.volume import storpool as vol_sp

test_attached = {}


class MockStorPoolExc(Exception):
    def __init__(self, msg):
        super(MockStorPoolExc, self).__init__(msg)


def storpoolVolumeName(vid):
    return 'os--volume--{id}'.format(id=vid)


def storpoolVolumePath(vid):
    return '/dev/storpool/' + storpoolVolumeName(vid)


class MockStorPoolConnector(object):
    def __init__(self, inst):
        self.inst = inst

    def connect_volume(self, connection_info):
        self.inst.assertIn('client_id', connection_info)
        self.inst.assertIn('volume', connection_info)
        self.inst.assertIn('access_mode', connection_info)

        v = connection_info['volume']
        if v in test_attached:
            raise MockStorPoolExc('Duplicate volume attachment')
        test_attached[v] = {
            'info': connection_info,
            'path': storpoolVolumePath(v)
        }
        return {'type': 'block', 'path': test_attached[v]['path']}

    def disconnect_volume(self, connection_info, device_info):
        self.inst.assertIn('client_id', connection_info)
        self.inst.assertIn('volume', connection_info)

        v = connection_info['volume']
        if v not in test_attached:
            raise MockStorPoolExc('Unknown volume to detach')
        self.inst.assertIs(test_attached[v]['info'], connection_info)
        del test_attached[v]


class MockStorPoolInitiator(object):
    def __init__(self, inst):
        self.inst = inst

    def factory(self, proto, helper):
        self.inst.assertEqual(proto, 'STORPOOL')
        self.inst.assertIsNotNone(helper)
        return MockStorPoolConnector(self.inst)


class LibvirtStorPoolVolumeDriverTestCase(
        test_volume.LibvirtVolumeBaseTestCase):

    def mock_storpool(f):
        def _config_inner_inner1(inst, *args, **kwargs):
            @mock.patch(
                'os_brick.initiator.connector.InitiatorConnector',
                new=MockStorPoolInitiator(inst))
            def _config_inner_inner2():
                return f(inst, *args, **kwargs)

            return _config_inner_inner2()

        return _config_inner_inner1

    def assertStorpoolAttached(self, names):
        self.assertListEqual(sorted(test_attached.keys()), sorted(names))

    def conn_info(self, volume):
        return {
            'data': {
                'access_mode': 'rw',
                'client_id': '1',
                'volume': volume
            }, 'serial': volume
        }

    @mock_storpool
    def test_storpool_config(self):
        libvirt_driver = vol_sp.LibvirtStorPoolVolumeDriver(self.fake_host)
        ci = self.conn_info('1')
        ci['data']['device_path'] = '/dev/storpool/something'
        c = libvirt_driver.get_config(ci, self.disk_info)
        self.assertEqual('block', c.source_type)
        self.assertEqual('/dev/storpool/something', c.source_path)

    @mock_storpool
    def test_storpool_attach_detach(self):
        libvirt_driver = vol_sp.LibvirtStorPoolVolumeDriver(self.fake_host)
        self.assertDictEqual({}, test_attached)

        ci_1 = self.conn_info('1')
        libvirt_driver.connect_volume(ci_1, self.disk_info)
        self.assertStorpoolAttached(('1',))

        ci_2 = self.conn_info('2')
        libvirt_driver.connect_volume(ci_2, self.disk_info)
        self.assertStorpoolAttached(('1', '2'))

        self.assertRaises(MockStorPoolExc,
                          libvirt_driver.connect_volume,
                          ci_2, self.disk_info)

        libvirt_driver.disconnect_volume(ci_1, None)
        self.assertStorpoolAttached(('2',))

        self.assertRaises(MockStorPoolExc,
                          libvirt_driver.disconnect_volume,
                          ci_1, self.disk_info)

        libvirt_driver.disconnect_volume(ci_2, self.disk_info)
        self.assertDictEqual({}, test_attached)