import unittest
from nexion.core import Unit, Task, Swarm, Facility, FacilityRegistry, demo

class NexionTest(unittest.TestCase):
    def test_failover(self):
        swarm=Swarm([Unit("a",{"inspect"},90),Unit("b",{"inspect"},80)],
                    [Task("t","inspect")])
        swarm.dispatch()
        self.assertEqual(swarm.tasks["t"].assigned_to,"a")
        swarm.fail_unit("a");swarm.dispatch()
        self.assertEqual(swarm.tasks["t"].assigned_to,"b")
    def test_noncapable_not_assigned(self):
        swarm=Swarm([Unit("a",{"inspect"})],[Task("t","fabricate")])
        swarm.dispatch()
        self.assertIsNone(swarm.tasks["t"].assigned_to)
    def test_low_energy_is_not_assigned(self):
        swarm=Swarm([Unit("a",{"inspect"},19)],[Task("t","inspect")])
        swarm.dispatch()
        self.assertEqual(swarm.tasks["t"].state,"pending")
    def test_unauthorized_facility_denied(self):
        with self.assertRaises(PermissionError):
            FacilityRegistry().register(Facility("factory","operator",{"cut"},""))
    def test_real_connection_denied_even_after_operator_verification(self):
        with self.assertRaises(PermissionError):
            FacilityRegistry().register(Facility("factory","operator",{"cut"},"ref",True,"live"))
    def test_simulated_facility_only_proposes(self):
        registry=FacilityRegistry()
        registry.register(Facility("factory","operator",{"print3d"},"approval-ref",True))
        self.assertFalse(registry.propose_job("factory","print3d")["executed"])
        with self.assertRaises(PermissionError):
            registry.propose_job("factory","laser")
    def test_demo(self):
        result=demo()
        self.assertTrue(result["unverified_factory_blocked"])
        self.assertEqual(result["real_equipment_commands_sent"],0)
        self.assertEqual([t["state"] for t in result["swarm"]["tasks"]],["completed","completed"])

if __name__=="__main__":
    unittest.main()
