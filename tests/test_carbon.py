

import unittest
from unittest.mock import patch
import bucky3.carbon as carbon


def carbon_verify(carbon_module, expected_values):
    for v in carbon_module.buffer:
        if v in expected_values:
            expected_values.remove(v)
        else:
            assert False, str(v) + " was not expected"
    if expected_values:
        assert False, "missing " + str(expected_values.pop())


def carbon_setup(timestamps, **extra_cfg):
    def run(fun, self):
        with patch('time.time') as system_time:
            buf = tuple(timestamps)
            system_time.side_effect = tuple(buf)
            cfg = dict(flush_interval=1, name_mapping=('bucket', 'foo', 'value'))
            cfg.update(**extra_cfg)
            carbon_module = carbon.CarbonClient('carbon_test', cfg, None)
            carbon_module.init_cfg()
            expected_output = fun(self, carbon_module)
            if expected_output is None:
                return
            carbon_verify(carbon_module, expected_output)

    if callable(timestamps):
        fun = timestamps
        timestamps = None
        return lambda self: run(fun, self)
    else:
        def wrapper(fun):
            return lambda self: run(fun, self)

        return wrapper


class TestCarbonClient(unittest.TestCase):
    @carbon_setup(timestamps=range(1, 100))
    def test_simple_multi_values(self, carbon_module):
        carbon_module.process_values(2, 'val1', dict(x=1, y=2), 1, {})
        carbon_module.process_values(2, 'val/2', dict(a=1.23, b=10.10), 1, {})
        carbon_module.process_values(2, 'val1', dict(y=10, z=11), 2, {})
        return [
            'val1.x 1 1\n',
            'val1.y 2 1\n',
            'val_2.a 1.23 1\n',
            'val_2.b 10.1 1\n',
            'val1.y 10 2\n',
            'val1.z 11 2\n',
        ]

    @carbon_setup(timestamps=range(1, 100))
    def test_multi_values(self, carbon_module):
        carbon_module.process_values(2, 'val1', dict(x=1.002, y=0.2), 1, dict(path='/foo/bar', foo='world', hello='world'))
        carbon_module.process_values(2, 'val/2', dict(a=1, b=10), 1, dict(a='1', b='2'))
        carbon_module.process_values(2, 'val1', dict(y=10, z=11.1), 2, dict(path='foo.bar', hello='world'))
        return [
            'val1.world.x.world._foo_bar 1.002 1\n',
            'val1.world.y.world._foo_bar 0.2 1\n',
            'val_2.a.1.2 1 1\n',
            'val_2.b.1.2 10 1\n',
            'val1.y.world.foo_bar 10 2\n',
            'val1.z.world.foo_bar 11.1 2\n',
        ]


if __name__ == '__main__':
    unittest.main()
