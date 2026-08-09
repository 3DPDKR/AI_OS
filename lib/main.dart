import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:image_picker/image_picker.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'core/providers/gemini_client.dart';

void main() => runApp(const AiOsApp());
const secureStorage = FlutterSecureStorage();
const native = MethodChannel('ai_os/native');

class AiOsApp extends StatelessWidget {
  const AiOsApp({super.key});
  @override Widget build(BuildContext context) => MaterialApp(title:'AI OS',debugShowCheckedModeBanner:false,theme:ThemeData(useMaterial3:true,colorSchemeSeed:Colors.indigo),home:const MainShell());
}
class MainShell extends StatefulWidget { const MainShell({super.key}); @override State<MainShell> createState()=>_MainShellState(); }
class _MainShellState extends State<MainShell> {
  int index=0;
  @override Widget build(BuildContext context)=>Scaffold(body:SafeArea(child:IndexedStack(index:index,children:const [ChatPage(),AiRoomPage(),HistoryPage(),SettingsPage()])),bottomNavigationBar:NavigationBar(selectedIndex:index,onDestinationSelected:(v)=>setState(()=>index=v),destinations:const [NavigationDestination(icon:Icon(Icons.chat_bubble_outline),label:'채팅'),NavigationDestination(icon:Icon(Icons.hub_outlined),label:'AI 대화방'),NavigationDestination(icon:Icon(Icons.history),label:'기록'),NavigationDestination(icon:Icon(Icons.settings_outlined),label:'설정')]));
}
class ChatPage extends StatefulWidget { const ChatPage({super.key}); @override State<ChatPage> createState()=>_ChatPageState(); }
class _ChatPageState extends State<ChatPage> {
  final input=TextEditingController(); final gemini=const GeminiClient(); final stt=SpeechToText(); final msgs=<Map<String,String>>[];
  String? name,text; bool busy=false,listening=false;
  Future<void> doc() async { try { final r=await native.invokeMapMethod<String,dynamic>('openDocument'); if(r!=null&&mounted){setState((){name=r['name']?.toString();text=r['text']?.toString();});} } catch(e){if(mounted)ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text('문서를 열 수 없습니다: $e')));} }
  Future<void> add() async { await showModalBottomSheet<void>(context:context,builder:(x)=>SafeArea(child:Wrap(children:[
    ListTile(leading:const Icon(Icons.camera_alt_outlined),title:const Text('카메라 촬영'),onTap:() async {Navigator.pop(x);if(await Permission.camera.request().isGranted){final f=await ImagePicker().pickImage(source:ImageSource.camera);if(f!=null&&mounted)setState(()=>name=f.name);}}),
    ListTile(leading:const Icon(Icons.photo_library_outlined),title:const Text('사진 선택'),onTap:() async {Navigator.pop(x);final f=await ImagePicker().pickImage(source:ImageSource.gallery);if(f!=null&&mounted)setState(()=>name=f.name);}),
    ListTile(leading:const Icon(Icons.description_outlined),title:const Text('문서 선택'),subtitle:const Text('PDF · TXT · MD · CSV · JSON 등'),onTap:(){Navigator.pop(x);doc();}),
  ]))); }
  Future<void> voice() async { if(listening){await stt.stop();if(mounted)setState(()=>listening=false);return;} if(!await Permission.microphone.request().isGranted)return; if(!await stt.initialize())return; if(mounted)setState(()=>listening=true); await stt.listen(onResult:(r){input.text=r.recognizedWords;input.selection=TextSelection.collapsed(offset:input.text.length);if(r.finalResult&&mounted)setState(()=>listening=false);}); }
  String local(String q){final d=(text??'').trim();if(d.isNotEmpty){final s=d.length>1800?d.substring(0,1800):d;return '문서 읽기 완료 (${d.length}자)\n\n$s\n\n질문: ${q.isEmpty?'문서를 검토해줘':q}';}return '입력을 처리했습니다. 연결된 생성형 AI가 없으면 로컬 기본 처리 모드로 동작합니다.';}
  Future<void> send() async { final q=input.text.trim();if(q.isEmpty&&name==null)return;setState((){msgs.add({'u':q.isEmpty?'${name??'첨부'} 분석':q,'a':''});input.clear();busy=true;});final k=await secureStorage.read(key:'gemini_api_key')??'';String a;if(k.isNotEmpty){try{var p=q;if((text??'').isNotEmpty)p+='\n\n문서:\n$text';a=await gemini.chat(apiKey:k,prompt:p);}catch(_){a=local(q);}}else{a=local(q);}if(mounted)setState((){msgs.add({'u':'','a':a});name=null;text=null;busy=false;}); }
  @override Widget build(BuildContext context)=>Column(children:[
    const ListTile(title:Text('AI OS',style:TextStyle(fontSize:25,fontWeight:FontWeight.bold)),subtitle:Text('최상의 결과를 위한 AI 운영체제')),
    Expanded(child:msgs.isEmpty?const Center(child:Text('무엇을 도와드릴까요?',style:TextStyle(fontSize:20))):ListView.builder(itemCount:msgs.length,itemBuilder:(_,i){final m=msgs[i];final u=m['u']!.isNotEmpty;return Align(alignment:u?Alignment.centerRight:Alignment.centerLeft,child:Card(child:Padding(padding:const EdgeInsets.all(12),child:Text(u?m['u']!:m['a']!))));})),
    if(name!=null) ListTile(leading:const Icon(Icons.attach_file),title:Text(name!),subtitle:Text(text==null?'첨부됨':'내용 읽기 완료'),trailing:IconButton(icon:const Icon(Icons.close),onPressed:()=>setState((){name=null;text=null;}))),
    if(busy) const LinearProgressIndicator(),
    Padding(padding:const EdgeInsets.all(8),child:Row(children:[IconButton(onPressed:add,icon:const Icon(Icons.add_circle_outline)),Expanded(child:TextField(controller:input,minLines:1,maxLines:5,decoration:const InputDecoration(hintText:'메시지',border:OutlineInputBorder()))),IconButton(onPressed:voice,icon:Icon(listening?Icons.mic:Icons.mic_none)),IconButton(onPressed:busy?null:send,icon:const Icon(Icons.send))]))
  ]);
}
class AiRoomPage extends StatefulWidget { const AiRoomPage({super.key}); @override State<AiRoomPage> createState()=>_AiRoomPageState(); }
class _AiRoomPageState extends State<AiRoomPage> {
  final topics=<String>['AI OS 개발']; String topic='AI OS 개발'; final input=TextEditingController(); final lines=<String>[];
  void newTopic(){final c=TextEditingController();showDialog<void>(context:context,builder:(d)=>AlertDialog(title:const Text('새 주제'),content:TextField(controller:c),actions:[TextButton(onPressed:()=>Navigator.pop(d),child:const Text('취소')),FilledButton(onPressed:(){final t=c.text.trim();if(t.isNotEmpty)setState((){topics.add(t);topic=t;lines.clear();});Navigator.pop(d);},child:const Text('생성'))]));}
  void send(){final q=input.text.trim();if(q.isEmpty)return;setState((){lines.add('나: $q');lines.add('Planner: 요청 분석');lines.add('Reviewer: 결과 검토');lines.add('Judge: 최종 결과 선정');input.clear();});}
  @override Widget build(BuildContext context)=>Column(children:[ListTile(title:const Text('AI 대화방',style:TextStyle(fontSize:25,fontWeight:FontWeight.bold)),subtitle:DropdownButton<String>(value:topic,isExpanded:true,items:topics.map((t)=>DropdownMenuItem(value:t,child:Text(t))).toList(),onChanged:(v){if(v!=null)setState(()=>topic=v);}),trailing:IconButton(onPressed:newTopic,icon:const Icon(Icons.add))),Expanded(child:lines.isEmpty?Center(child:Text('주제: $topic\nAI 회의에 직접 참여할 수 있습니다.',textAlign:TextAlign.center)):ListView.builder(itemCount:lines.length,itemBuilder:(_,i)=>ListTile(title:Text(lines[i])))),Padding(padding:const EdgeInsets.all(8),child:Row(children:[Expanded(child:TextField(controller:input,decoration:const InputDecoration(hintText:'AI 회의에 참여',border:OutlineInputBorder()))),IconButton(onPressed:send,icon:const Icon(Icons.send))]))]);
}
class HistoryPage extends StatelessWidget { const HistoryPage({super.key}); @override Widget build(BuildContext context)=>const Center(child:Text('대화 및 작업 기록')); }
class SettingsPage extends StatefulWidget { const SettingsPage({super.key}); @override State<SettingsPage> createState()=>_SettingsPageState(); }
class _SettingsPageState extends State<SettingsPage> with WidgetsBindingObserver {
  bool freeFirst=true,paid=false,mic=false,cam=false; final enabled=<String,bool>{'Gemini':true,'Groq':false,'OpenRouter Free':false,'Hugging Face':false,'OpenAI API':false,'Claude API':false};
  @override void initState(){super.initState();WidgetsBinding.instance.addObserver(this);load();}
  @override void dispose(){WidgetsBinding.instance.removeObserver(this);super.dispose();}
  @override void didChangeAppLifecycleState(AppLifecycleState state){if(state==AppLifecycleState.resumed)load();}
  Future<void> load() async {final m=await Permission.microphone.isGranted;final c=await Permission.camera.isGranted;final f=(await secureStorage.read(key:'free_first'))!='false';final p=(await secureStorage.read(key:'paid_enabled'))=='true';for(final k in enabled.keys.toList()){final v=await secureStorage.read(key:'provider_$k');if(v!=null)enabled[k]=v=='true';}if(mounted)setState((){mic=m;cam=c;freeFirst=f;paid=p;});}
  Future<void> request(Permission permission) async {final s=await permission.request();if(s.isPermanentlyDenied)await openAppSettings();await load();}
  Future<void> toggle(String k,bool v) async {setState(()=>enabled[k]=v);await secureStorage.write(key:'provider_$k',value:'$v');}
  Future<void> keyDialog(String p) async {final k=p=='Gemini'?'gemini_api_key':'${p.toLowerCase().replaceAll(' ','_')}_api_key';final c=TextEditingController(text:await secureStorage.read(key:k)??'');if(!mounted)return;await showDialog<void>(context:context,builder:(d)=>AlertDialog(title:Text('$p API 설정'),content:TextField(controller:c,obscureText:true,decoration:const InputDecoration(labelText:'API Key (선택사항)',border:OutlineInputBorder())),actions:[TextButton(onPressed:()=>Navigator.pop(d),child:const Text('취소')),FilledButton(onPressed:() async {await secureStorage.write(key:k,value:c.text.trim());if(d.mounted)Navigator.pop(d);},child:const Text('저장'))]));}
  @override Widget build(BuildContext context)=>ListView(children:[
    const ListTile(title:Text('설정',style:TextStyle(fontSize:25,fontWeight:FontWeight.bold)),subtitle:Text('AI 선택 · API · 권한 · 음성 · 저장공간')),
    SwitchListTile(value:freeFirst,onChanged:(v){setState(()=>freeFirst=v);secureStorage.write(key:'free_first',value:'$v');},title:const Text('무료 AI 우선')),
    SwitchListTile(value:paid,onChanged:(v){setState(()=>paid=v);secureStorage.write(key:'paid_enabled',value:'$v');},title:const Text('유료 API 사용 허용'),subtitle:const Text('기본 OFF')),
    const Divider(),
    ...enabled.entries.map((e)=>Card(child:Column(children:[SwitchListTile(value:e.value,onChanged:(v)=>toggle(e.key,v),title:Text(e.key)),TextButton.icon(onPressed:()=>keyDialog(e.key),icon:const Icon(Icons.key),label:const Text('API 설정'))]))),
    const Divider(),
    ListTile(leading:const Icon(Icons.mic),title:const Text('마이크 권한'),subtitle:Text(mic?'허용됨 ✓':'음성 입력에 필요'),trailing:mic?null:TextButton(onPressed:()=>request(Permission.microphone),child:const Text('요청'))),
    ListTile(leading:const Icon(Icons.camera_alt),title:const Text('카메라 권한'),subtitle:Text(cam?'허용됨 ✓':'카메라 촬영에 필요'),trailing:cam?null:TextButton(onPressed:()=>request(Permission.camera),child:const Text('요청'))),
    const ListTile(leading:Icon(Icons.description_outlined),title:Text('문서 권한'),subtitle:Text('시스템 문서 선택기 사용 · 전체 저장소 권한 불필요')),
    const ListTile(leading:Icon(Icons.storage),title:Text('저장공간'),subtitle:Text('내부 저장 최소화 · 보안 저장소에 API Key 보관')),
    const Divider(),const ListTile(title:Text('AI OS'),subtitle:Text('Version 0.4.0\nCreator: Daehyun Kang'))
  ]);
}
