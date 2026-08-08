import 'agent.dart';

class AgentTask {
  const AgentTask({
    required this.id,
    required this.topicId,
    required this.goal,
    required this.requiredCapabilities,
  });

  final String id;
  final String topicId;
  final String goal;
  final Set<String> requiredCapabilities;
}

class AgentRoomEvent {
  const AgentRoomEvent({
    required this.agent,
    required this.message,
    required this.status,
    required this.createdAt,
  });

  final AiAgent agent;
  final String message;
  final AgentStatus status;
  final DateTime createdAt;
}
