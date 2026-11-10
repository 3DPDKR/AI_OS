"""Offline only: no network, hardware actuation or manufacturing commands."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Set
import json

@dataclass
class Unit:
    name: str
    capabilities: Set[str]
    energy_percent: int = 100
    online: bool = True
    active_task: Optional[str] = None

    def can_do(self, capability: str) -> bool:
        return (self.online and self.energy_percent >= 20
                and capability in self.capabilities and self.active_task is None)

@dataclass
class Task:
    name: str
    required_capability: str
    state: str = "pending"
    assigned_to: Optional[str] = None

@dataclass(frozen=True)
class Facility:
    name: str
    operator: str
    permitted_capabilities: Set[str]
    evidence_reference: str
    operator_verified: bool = False
    connection_mode: str = "simulation"

class FacilityRegistry:
    def __init__(self):
        self.approved: Dict[str, Facility] = {}
        self.audit: List[dict] = []

    def register(self, facility: Facility) -> None:
        if not facility.operator_verified or not facility.evidence_reference.strip():
            raise PermissionError("Facility-specific authorization evidence required")
        if facility.connection_mode != "simulation":
            raise PermissionError("Live equipment connections are disabled")
        if not facility.permitted_capabilities:
            raise ValueError("At least one capability is required")
        self.approved[facility.name] = facility
        self.audit.append({"event":"registered","facility":facility.name,"mode":"simulation"})

    def propose_job(self, facility_name: str, capability: str) -> dict:
        facility = self.approved.get(facility_name)
        if facility is None or capability not in facility.permitted_capabilities:
            raise PermissionError("Facility or capability not approved")
        record = {"event":"simulation_only_proposal","facility":facility_name,
                  "capability":capability,"executed":False}
        self.audit.append(record)
        return record

class Swarm:
    def __init__(self, units: List[Unit], tasks: List[Task]):
        if len({u.name for u in units}) != len(units):
            raise ValueError("Duplicate unit")
        if len({t.name for t in tasks}) != len(tasks):
            raise ValueError("Duplicate task")
        self.units = {u.name:u for u in units}
        self.tasks = {t.name:t for t in tasks}
        self.events: List[dict] = []

    def dispatch(self) -> None:
        for task in self.tasks.values():
            if task.state != "pending":
                continue
            available = sorted((u for u in self.units.values()
                                if u.can_do(task.required_capability)),
                               key=lambda u:(-u.energy_percent,u.name))
            if not available:
                self.events.append({"event":"unassigned","task":task.name})
                continue
            unit = available[0]
            unit.active_task,task.assigned_to,task.state = task.name,unit.name,"assigned"
            self.events.append({"event":"assigned","task":task.name,"unit":unit.name})

    def fail_unit(self, name: str) -> None:
        unit = self.units[name]
        unit.online = False
        if unit.active_task:
            task = self.tasks[unit.active_task]
            task.state,task.assigned_to = "pending",None
            self.events.append({"event":"failover_queued","task":task.name,"failed_unit":name})
            unit.active_task = None
        self.events.append({"event":"unit_failed","unit":name})

    def complete(self, task_name: str) -> None:
        task = self.tasks[task_name]
        if task.state != "assigned":
            raise ValueError("Task not assigned")
        unit = self.units[task.assigned_to]
        unit.active_task,task.state = None,"completed"
        self.events.append({"event":"completed","task":task.name,"unit":unit.name})

    def snapshot(self) -> dict:
        return {"units":[{**asdict(u),"capabilities":sorted(u.capabilities)}
                         for u in self.units.values()],
                "tasks":[asdict(t) for t in self.tasks.values()],
                "events":list(self.events)}

def demo() -> dict:
    swarm = Swarm([Unit("NEX-A",{"sense"},90),Unit("NEX-B",{"sense"},70),
                   Unit("NEX-C",{"navigate"},80)],
                  [Task("survey","sense"),Task("relocate","navigate")])
    swarm.dispatch()
    swarm.fail_unit("NEX-A")
    swarm.dispatch()
    swarm.complete("survey")
    swarm.complete("relocate")
    registry = FacilityRegistry()
    blocked = False
    try:
        registry.register(Facility("UNKNOWN_FACTORY","unknown",{"fabricate"},""))
    except PermissionError:
        blocked = True
    return {"swarm":swarm.snapshot(),"unverified_factory_blocked":blocked,
            "real_equipment_commands_sent":0}

if __name__ == "__main__":
    print(json.dumps(demo(),ensure_ascii=False,indent=2))
