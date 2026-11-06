import unittest
from services import strategy_s0 as s0

class DTest(unittest.TestCase):
 def test_whitelist(self):
  with self.assertRaisesRegex(ValueError,'白名单'):
   s0.D(action='approve',rationale='E1 超额为负，申请入库').norm()
 def test_adjust_requires_parameter(self):
  with self.assertRaisesRegex(ValueError,'参数'):
   s0.D(action='adjust',rationale='E1 超额为负，调整参数').norm()
 def test_stop_ok(self):
  self.assertEqual(s0.D(action='stop',rationale='E1 超额为负，停止',stop_reason='no_improvement').norm().action,'stop')
