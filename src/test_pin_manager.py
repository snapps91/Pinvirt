import unittest
from typing import List, Dict, Set, Tuple
from pinvirt import (
    generate_cpu_allocation,
    build_ovirt_pinning_string,
    get_used_logical_cpus,
    save_pinning,
    load_pinning
)

import os
import json

# Type aliases
CpuInfo = List[Tuple[int, int, int]]
PinningMap = Dict[str, List[int]]
TEST_PIN_FILE = "cpu_pinning_map.json"


class TestPinManager(unittest.TestCase):

    def setUp(self):
        # Reset dummy JSON file
        if os.path.exists(TEST_PIN_FILE):
            os.remove(TEST_PIN_FILE)

    def tearDown(self):
        if os.path.exists(TEST_PIN_FILE):
            os.remove(TEST_PIN_FILE)

    def test_get_used_logical_cpus(self):
        pinning_data: PinningMap = {
            "vm1": [0, 2, 4],
            "vm2": [6, 8]
        }
        expected = {0, 2, 4, 6, 8}
        result = get_used_logical_cpus(pinning_data)
        self.assertEqual(result, expected)

    def test_build_ovirt_pinning_string(self):
        cpus = [0, 2, 4, 6]
        expected = "0#0_1#2_2#4_3#6"
        result = build_ovirt_pinning_string(cpus)
        self.assertEqual(result, expected)

    def test_generate_cpu_allocation_multi_socket(self):
        topology: CpuInfo = [
            (0, 0, 0), (16, 0, 0),
            (1, 1, 0), (17, 1, 0),
            (18, 0, 1), (2, 0, 1),
            (19, 1, 1), (3, 1, 1),
        ]
        used: Set[int] = {0, 1}
        result = generate_cpu_allocation(topology, 2, used, target_socket=0, allow_multi_socket=True)
        self.assertCountEqual(result, [18, 19])  # Correct values based on core_map input

    def test_generate_cpu_allocation_multi_socket(self):
        topology: CpuInfo = [
            (0, 0, 0), (16, 0, 0),
            (1, 1, 0), (17, 1, 0),
            (2, 0, 1), (18, 0, 1),
            (3, 1, 1), (19, 1, 1),
        ]
        used: Set[int] = {0, 1}
        
        result = generate_cpu_allocation(topology, 2, used, target_socket=0, allow_multi_socket=True)

        expected = [16, 17]  # Correct order from available cores on socket 0
        self.assertEqual(result, expected)

    def test_save_and_load_pinning(self):
        data: PinningMap = {"vm1": [0, 1, 2]}
        save_pinning(data)
        loaded = load_pinning()
        self.assertEqual(loaded, data)


if __name__ == "__main__":
    unittest.main()
