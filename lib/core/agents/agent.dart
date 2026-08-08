enum AgentRole { planner, researcher, reasoner, coder, vision, translator, evidence, navigator, synthesizer, quality }

enum AgentStatus { idle, queued, running, completed, failed, disabled }

class AiAgent {
  const AiAgent({
    required this.id,
    required this.name,
    required this.role,
    required this.capabilities,
    this.enabled = true,
    this.maxSteps = 6,
  });

  final String id;
  final String name;
  final AgentRole role;
  final Set<String> capabilities;
  final bool enabled;
  final int maxSteps;
}

const defaultAgents = <AiAgent>[
  AiAgent(id: 'planner', name: 'Planner', role: AgentRole.planner, capabilities: {'planning', 'routing'}),
  AiAgent(id: 'researcher', name: 'Researcher', role: AgentRole.researcher, capabilities: {'research', 'web_search'}),
  AiAgent(id: 'reasoner', name: 'Reasoner', role: AgentRole.reasoner, capabilities: {'reasoning'}),
  AiAgent(id: 'coder', name: 'Coder', role: AgentRole.coder, capabilities: {'coding'}),
  AiAgent(id: 'vision', name: 'Vision', role: AgentRole.vision, capabilities: {'vision', 'ocr'}),
  AiAgent(id: 'translator', name: 'Translator', role: AgentRole.translator, capabilities: {'translation'}),
  AiAgent(id: 'evidence', name: 'Evidence', role: AgentRole.evidence, capabilities: {'evidence', 'citation'}),
  AiAgent(id: 'navigator', name: 'Navigator', role: AgentRole.navigator, capabilities: {'navigation', 'mapping'}),
  AiAgent(id: 'synthesizer', name: 'Synthesizer', role: AgentRole.synthesizer, capabilities: {'synthesis'}),
  AiAgent(id: 'quality', name: 'Quality Gate', role: AgentRole.quality, capabilities: {'quality', 'verification'}),
];
