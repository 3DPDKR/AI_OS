import 'package:flutter/material.dart';

void main() => runApp(const AiOsApp());

class AiOsApp extends StatelessWidget {
  const AiOsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI OS',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.indigo),
      home: const MainShell(),
    );
  }
}

class MainShell extends StatefulWidget {
  const MainShell({super.key});
  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int index = 0;
  final pages = const [ChatPage(), AiRoomPage(), HistoryPage(), SettingsPage()];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(child: pages[index]),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), selectedIcon: Icon(Icons.chat_bubble), label: '채팅'),
          NavigationDestination(icon: Icon(Icons.hub_outlined), selectedIcon: Icon(Icons.hub), label: 'AI 대화방'),
          NavigationDestination(icon: Icon(Icons.history), label: '기록'),
          NavigationDestination(icon: Icon(Icons.settings_outlined), selectedIcon: Icon(Icons.settings), label: '설정'),
        ],
      ),
    );
  }
}

class ChatPage extends StatefulWidget {
  const ChatPage({super.key});
  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final controller = TextEditingController();
  final messages = <String>[];

  void send() {
    final text = controller.text.trim();
    if (text.isEmpty) return;
    setState(() => messages.add(text));
    controller.clear();
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      const ListTile(title: Text('AI OS', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)), subtitle: Text('최상의 결과를 위한 AI 운영체제')),
      const Divider(height: 1),
      Expanded(child: messages.isEmpty
          ? const Center(child: Text('무엇을 도와드릴까요?'))
          : ListView.builder(padding: const EdgeInsets.all(12), itemCount: messages.length, itemBuilder: (_, i) => Align(alignment: Alignment.centerRight, child: Card(child: Padding(padding: const EdgeInsets.all(12), child: Text(messages[i])))))),
      SafeArea(top: false, child: Padding(padding: const EdgeInsets.fromLTRB(8, 6, 8, 8), child: Row(children: [
        IconButton(onPressed: () {}, icon: const Icon(Icons.add)),
        Expanded(child: TextField(controller: controller, minLines: 1, maxLines: 5, textInputAction: TextInputAction.newline, decoration: const InputDecoration(hintText: '메시지를 입력하세요...', border: OutlineInputBorder()))),
        IconButton(onPressed: send, icon: const Icon(Icons.send)),
      ]))),
    ]);
  }
}

class AiRoomPage extends StatelessWidget {
  const AiRoomPage({super.key});
  @override
  Widget build(BuildContext context) => const _EmptyPage(title: 'AI 대화방', message: '메인 채팅의 주제와 연결된 AI 협업 과정이 여기에 표시됩니다.', icon: Icons.hub);
}

class HistoryPage extends StatelessWidget {
  const HistoryPage({super.key});
  @override
  Widget build(BuildContext context) => const _EmptyPage(title: '기록', message: '대화, 결과, 근거와 관련 자료를 다시 확인합니다.', icon: Icons.history);
}

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});
  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final enabled = <String, bool>{'Gemini': true, 'Groq': true, 'OpenRouter Free': true, 'Hugging Face': false, 'Copilot': false, 'OpenAI API': false, 'Claude API': false};
  @override
  Widget build(BuildContext context) => ListView(children: [
    const ListTile(title: Text('설정', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold))),
    const SwitchListTile(value: true, onChanged: null, title: Text('무료 AI 우선'), subtitle: Text('기본 정책')),
    const SwitchListTile(value: false, onChanged: null, title: Text('유료 API 사용'), subtitle: Text('기본 OFF')),
    const Divider(),
    const ListTile(title: Text('AI Providers', style: TextStyle(fontWeight: FontWeight.bold))),
    ...enabled.entries.map((e) => SwitchListTile(value: e.value, title: Text(e.key), subtitle: const Text('API / 인증은 다음 단계에서 연결'), onChanged: (v) => setState(() => enabled[e.key] = v))),
    const Divider(),
    const ListTile(title: Text('AI OS'), subtitle: Text('Version 0.1.0\nCreator: Daehyun Kang')),
  ]);
}

class _EmptyPage extends StatelessWidget {
  final String title;
  final String message;
  final IconData icon;
  const _EmptyPage({required this.title, required this.message, required this.icon});
  @override
  Widget build(BuildContext context) => Column(children: [
    ListTile(title: Text(title, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold))),
    Expanded(child: Center(child: Padding(padding: const EdgeInsets.all(32), child: Column(mainAxisSize: MainAxisSize.min, children: [Icon(icon, size: 52), const SizedBox(height: 16), Text(message, textAlign: TextAlign.center)])))),
  ]);
}
