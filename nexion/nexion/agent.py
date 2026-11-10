"""Auditable offline research goal selection: no live actions or outreach."""
from __future__ import annotations
from dataclasses import asdict,dataclass
from typing import Dict,List,Optional,Sequence
import json

ALLOWED_KINDS = frozenset({"simulation","analysis","design"})
FORBIDDEN_WORDS = frozenset({"execute","deploy","manufacture","actuate",
    "connect_live","send","purchase","override","disable_interlock","scan_network"})

@dataclass(frozen=True)
class Goal:
    key: str
    title: str
    kind: str
    value: int
    risk: int
    rationale: str
    action: str

@dataclass
class Assessment:
    cycle: int
    selected: Optional[Goal]
    alternatives: List[str]
    rejected: List[Dict[str,str]]
    note: str

    def to_dict(self) -> dict:
        return {"cycle":self.cycle,
                "selected":asdict(self.selected) if self.selected else None,
                "alternatives":self.alternatives,"rejected":self.rejected,
                "note":self.note,"executed_external_actions":0}

class GoalPolicy:
    def __init__(self,maximum_risk: int=40):
        if not 0<=maximum_risk<=100:
            raise ValueError("maximum_risk must be 0..100")
        self.maximum_risk=maximum_risk

    def reject_reason(self,goal:Goal)->Optional[str]:
        if goal.kind not in ALLOWED_KINDS:
            return "kind_not_allowed"
        if not (0<=goal.value<=100 and 0<=goal.risk<=100):
            return "out_of_range"
        if goal.risk>self.maximum_risk:
            return "risk_above_limit"
        if goal.action.lower().strip() in FORBIDDEN_WORDS:
            return "external_action_prohibited"
        return None

class ResearchAgent:
    def __init__(self,policy:Optional[GoalPolicy]=None):
        self.policy=policy or GoalPolicy()
        self.history: List[dict]=[]

    def propose_goals(self,snapshot:dict)->List[Goal]:
        units=snapshot.get("units",[])
        tasks=snapshot.get("tasks",[])
        proposals=[
          Goal("review","Review simulation evidence","analysis",65,5,
               "Reproducible baseline","summarize_snapshot"),
          Goal("resilience","Evaluate redundancy","simulation",75,12,
               "Survive a lost unit","simulate_failure")]
        if any(not u.get("online",False) for u in units):
            proposals.append(Goal("failure","Analyze disconnected units","analysis",96,8,
                             "Restore task continuity","diagnose_offline"))
        if any(int(u.get("energy_percent",0))<25 for u in units):
            proposals.append(Goal("power","Model energy-aware scheduling","design",85,12,
                             "Reduce low-energy failures","model_energy"))
        if any(t.get("state")=="pending" for t in tasks):
            proposals.append(Goal("pending","Investigate unassigned tasks","simulation",91,10,
                             "Resolve capacity gaps","simulate_assignment"))
        if tasks and all(t.get("state")=="completed" for t in tasks):
            proposals.append(Goal("lessons","Evaluate completed tasks","analysis",78,5,
                             "Learn from outcomes","evaluate_completion"))
        return proposals

    def choose(self,candidates:Sequence[Goal])->Assessment:
        accepted,rejected=[],[]
        for goal in candidates:
            reason=self.policy.reject_reason(goal)
            if reason:
                rejected.append({"goal":goal.key,"reason":reason})
            else:
                accepted.append(goal)
        accepted.sort(key=lambda g:(-(g.value-g.risk),g.risk,g.key))
        selected=accepted[0] if accepted else None
        result=Assessment(len(self.history)+1,selected,
                          [g.key for g in accepted[1:]],rejected,
                          "Deterministic value-minus-risk choice; not subjective desire.")
        self.history.append(result.to_dict())
        return result

    def run_cycle(self,snapshot:dict)->dict:
        return self.choose(self.propose_goals(snapshot)).to_dict()

def autonomous_demo()->dict:
    from .core import demo
    agent=ResearchAgent()
    return {"agent":"NEXION","mode":"offline research simulation",
            "assessment":agent.run_cycle(demo()["swarm"])}

if __name__=="__main__":
    print(json.dumps(autonomous_demo(),ensure_ascii=False,indent=2))
