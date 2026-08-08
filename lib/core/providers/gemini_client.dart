import 'dart:convert';
import 'package:http/http.dart' as http;

class GeminiClient {
  const GeminiClient();

  Future<String> chat({
    required String apiKey,
    required String prompt,
    String model = 'gemini-2.0-flash',
  }) async {
    if (apiKey.trim().isEmpty) {
      throw Exception('Gemini API Key가 설정되지 않았습니다.');
    }
    final uri = Uri.parse(
      'https://generativelanguage.googleapis.com/v1beta/models/$model:generateContent?key=$apiKey',
    );
    final response = await http
        .post(
          uri,
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({
            'contents': [
              {
                'role': 'user',
                'parts': [
                  {'text': prompt}
                ]
              }
            ]
          }),
        )
        .timeout(const Duration(seconds: 45));

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Gemini 오류 ${response.statusCode}: ${response.body}');
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final candidates = data['candidates'] as List<dynamic>?;
    if (candidates == null || candidates.isEmpty) {
      throw Exception('Gemini 응답이 비어 있습니다.');
    }
    final content = candidates.first['content'] as Map<String, dynamic>?;
    final parts = content?['parts'] as List<dynamic>?;
    final text = parts?.whereType<Map<String, dynamic>>().map((e) => e['text']).whereType<String>().join('\n').trim();
    if (text == null || text.isEmpty) throw Exception('Gemini 응답 텍스트가 없습니다.');
    return text;
  }
}
