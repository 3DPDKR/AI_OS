enum ProviderKind { free, paid, mixed }

enum ProviderStatus { notConfigured, ready, checking, error }

class ProviderConfig {
  const ProviderConfig({
    required this.id,
    required this.name,
    required this.kind,
    required this.defaultModel,
    this.enabled = false,
    this.requiresApiKey = true,
    this.status = ProviderStatus.notConfigured,
  });

  final String id;
  final String name;
  final ProviderKind kind;
  final String defaultModel;
  final bool enabled;
  final bool requiresApiKey;
  final ProviderStatus status;

  ProviderConfig copyWith({bool? enabled, ProviderStatus? status}) => ProviderConfig(
        id: id,
        name: name,
        kind: kind,
        defaultModel: defaultModel,
        enabled: enabled ?? this.enabled,
        requiresApiKey: requiresApiKey,
        status: status ?? this.status,
      );
}

const defaultProviders = <ProviderConfig>[
  ProviderConfig(id: 'gemini', name: 'Gemini', kind: ProviderKind.free, defaultModel: 'gemini-2.0-flash', enabled: true),
  ProviderConfig(id: 'groq', name: 'Groq', kind: ProviderKind.free, defaultModel: 'llama-3.3-70b-versatile', enabled: true),
  ProviderConfig(id: 'openrouter', name: 'OpenRouter Free', kind: ProviderKind.free, defaultModel: 'openrouter/free', enabled: true),
  ProviderConfig(id: 'huggingface', name: 'Hugging Face', kind: ProviderKind.free, defaultModel: 'auto'),
  ProviderConfig(id: 'openai', name: 'OpenAI API', kind: ProviderKind.paid, defaultModel: 'gpt-4o-mini'),
  ProviderConfig(id: 'claude', name: 'Claude API', kind: ProviderKind.paid, defaultModel: 'claude-sonnet'),
];
