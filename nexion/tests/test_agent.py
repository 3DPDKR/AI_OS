import unittest
from nexion.agent import Goal,GoalPolicy,ResearchAgent,autonomous_demo

class ResearchAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent=ResearchAgent()
    def test_selects_critical_offline_analysis(self):
        snap={"units":[{"name":"a","online":False,"energy_percent":80}],
              "tasks":[{"name":"survey","state":"completed"}]}
        result=self.agent.run_cycle(snap)
        self.assertEqual(result["selected"]["key"],"failure")
        self.assertEqual(result["executed_external_actions"],0)
    def test_pending_task_gets_priority(self):
        snap={"units":[{"online":True,"energy_percent":99}],"tasks":[{"state":"pending"}]}
        self.assertEqual(self.agent.run_cycle(snap)["selected"]["key"],"pending")
    def test_low_energy_generates_goal(self):
        snap={"units":[{"online":True,"energy_percent":10}],"tasks":[]}
        self.assertEqual(self.agent.run_cycle(snap)["selected"]["key"],"power")
    def test_no_data_defaults_to_research_goal(self):
        self.assertEqual(self.agent.run_cycle({})["selected"]["key"],"resilience")
    def test_forbidden_external_action_rejected(self):
        result=self.agent.choose([Goal("bad","Try production","simulation",100,0,"","manufacture")])
        self.assertIsNone(result.selected)
        self.assertEqual(result.rejected[0]["reason"],"external_action_prohibited")
    def test_risky_goal_rejected(self):
        result=self.agent.choose([Goal("bad","High risk","analysis",99,99,"","review")])
        self.assertEqual(result.rejected[0]["reason"],"risk_above_limit")
    def test_nonresearch_kind_rejected(self):
        result=self.agent.choose([Goal("bad","Operate","manufacturing",99,1,"","review")])
        self.assertEqual(result.rejected[0]["reason"],"kind_not_allowed")
    def test_cycle_history_is_auditable(self):
        self.agent.run_cycle({});self.agent.run_cycle({})
        self.assertEqual([a["cycle"] for a in self.agent.history],[1,2])
    def test_demo_is_offline(self):
        result=autonomous_demo()
        self.assertEqual(result["assessment"]["executed_external_actions"],0)
        self.assertIsNotNone(result["assessment"]["selected"])

if __name__=="__main__":
    unittest.main()
