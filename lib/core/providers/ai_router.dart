import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'gemini_client.dart';

class AiReply { final String text, provider; const AiReply(this.text,this.provider); }
class AiRouter {
  const AiRouter(this.storage); final FlutterSecureStorage storage;
  Future<AiReply> ask(String prompt) async {
    final paid=(await storage.read(key:'paid_enabled'))=='true';
    final order=['Gemini','Groq','OpenRouter Free','Hugging Face',if(paid)'OpenAI API',if(paid)'Claude API'];
    final errors=<String>[];
    for(final p in order){
      final enabled=(await storage.read(key:'provider_$p')) ?? (p=='Gemini'?'true':'false');
      if(enabled!='true') continue;
      try { final r=await _call(p,prompt); if(r.trim().isNotEmpty)return AiReply(r,p); } catch(e){errors.add('$p: $e');}
    }
    throw Exception(errors.isEmpty?'사용 가능한 AI가 없습니다. 설정에서 무료 Provider를 켜고 API Key를 등록하세요.':errors.join('\n'));
  }
  String _keyName(String p)=>p=='Gemini'?'gemini_api_key':'${p.toLowerCase().replaceAll(' ','_')}_api_key';
  Future<String> _call(String p,String prompt) async {
    final key=(await storage.read(key:_keyName(p)))?.trim()??'';
    if(key.isEmpty)throw Exception('API Key 없음');
    if(p=='Gemini')return const GeminiClient().chat(apiKey:key,prompt:prompt);
    if(p=='Groq')return _openAi('https://api.groq.com/openai/v1/chat/completions',key,'llama-3.3-70b-versatile',prompt);
    if(p=='OpenRouter Free')return _openAi('https://openrouter.ai/api/v1/chat/completions',key,'openrouter/free',prompt,extra:{'HTTP-Referer':'https://github.com/3DPDKR/AI_OS','X-Title':'AI OS'});
    if(p=='OpenAI API')return _openAi('https://api.openai.com/v1/chat/completions',key,'gpt-4o-mini',prompt);
    if(p=='Claude API')return _claude(key,prompt);
    if(p=='Hugging Face')return _hf(key,prompt);
    throw Exception('지원하지 않는 Provider');
  }
  Future<String> _openAi(String url,String key,String model,String prompt,{Map<String,String>? extra}) async {final r=await http.post(Uri.parse(url),headers:{'Authorization':'Bearer $key','Content-Type':'application/json',...?extra},body:jsonEncode({'model':model,'messages':[{'role':'user','content':prompt}]})).timeout(const Duration(seconds:45));if(r.statusCode<200||r.statusCode>=300)throw Exception('HTTP ${r.statusCode} ${r.body}');final d=jsonDecode(r.body);return d['choices'][0]['message']['content'].toString();}
  Future<String> _claude(String key,String prompt) async {final r=await http.post(Uri.parse('https://api.anthropic.com/v1/messages'),headers:{'x-api-key':key,'anthropic-version':'2023-06-01','content-type':'application/json'},body:jsonEncode({'model':'claude-3-5-haiku-latest','max_tokens':2048,'messages':[{'role':'user','content':prompt}]})).timeout(const Duration(seconds:45));if(r.statusCode<200||r.statusCode>=300)throw Exception('HTTP ${r.statusCode} ${r.body}');final d=jsonDecode(r.body);return d['content'][0]['text'].toString();}
  Future<String> _hf(String key,String prompt) async {final r=await http.post(Uri.parse('https://router.huggingface.co/v1/chat/completions'),headers:{'Authorization':'Bearer $key','Content-Type':'application/json'},body:jsonEncode({'model':'Qwen/Qwen2.5-7B-Instruct','messages':[{'role':'user','content':prompt}]})).timeout(const Duration(seconds:45));if(r.statusCode<200||r.statusCode>=300)throw Exception('HTTP ${r.statusCode} ${r.body}');final d=jsonDecode(r.body);return d['choices'][0]['message']['content'].toString();}
  Future<String> test(String p)=>_call(p,'한 문장으로 연결 성공이라고 답해줘.');
}
