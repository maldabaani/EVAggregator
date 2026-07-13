import 'dart:convert';

import 'package:evagg_driver/core/api/api_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('GET decodes a successful JSON response', () async {
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        expect(request.url.toString(), 'https://api.example.com/things');
        return http.Response(jsonEncode({'data': ['a', 'b']}), 200);
      }),
    );

    final result = await client.get('/things', authorized: false);

    expect(result, {'data': ['a', 'b']});
  });

  test('query parameters are attached to the request URL', () async {
    late Uri capturedUri;
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        capturedUri = request.url;
        return http.Response('{}', 200);
      }),
    );

    await client.get('/things', query: {'bbox': '1,2,3,4'}, authorized: false);

    expect(capturedUri.queryParameters['bbox'], '1,2,3,4');
  });

  test('an authorized request attaches the bearer token', () async {
    late Map<String, String> capturedHeaders;
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      accessToken: 'token-123',
      httpClient: MockClient((request) async {
        capturedHeaders = request.headers;
        return http.Response('{}', 200);
      }),
    );

    await client.get('/things');

    expect(capturedHeaders['Authorization'], 'Bearer token-123');
  });

  test('an unauthorized request omits the Authorization header even with a token set', () async {
    late Map<String, String> capturedHeaders;
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      accessToken: 'token-123',
      httpClient: MockClient((request) async {
        capturedHeaders = request.headers;
        return http.Response('{}', 200);
      }),
    );

    await client.get('/things', authorized: false);

    expect(capturedHeaders.containsKey('Authorization'), isFalse);
  });

  test('POST sends a JSON-encoded body', () async {
    late String capturedBody;
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        capturedBody = request.body;
        return http.Response('{}', 200);
      }),
    );

    await client.post('/things', body: {'name': 'X'}, authorized: false);

    expect(jsonDecode(capturedBody), {'name': 'X'});
  });

  test('a non-2xx response throws an ApiException carrying the "detail" message', () async {
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        return http.Response(jsonEncode({'detail': 'not found'}), 404);
      }),
    );

    await expectLater(
      client.get('/things', authorized: false),
      throwsA(isA<ApiException>().having((e) => e.message, 'message', 'not found').having(
            (e) => e.statusCode,
            'statusCode',
            404,
          )),
    );
  });

  test('a 401 triggers onUnauthorized and retries once with the refreshed token', () async {
    var callCount = 0;
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      accessToken: 'expired-token',
      httpClient: MockClient((request) async {
        callCount++;
        if (request.headers['Authorization'] == 'Bearer expired-token') {
          return http.Response('', 401);
        }
        expect(request.headers['Authorization'], 'Bearer fresh-token');
        return http.Response(jsonEncode({'ok': true}), 200);
      }),
    );
    client.onUnauthorized = () async => 'fresh-token';

    final result = await client.get('/things');

    expect(result, {'ok': true});
    expect(callCount, 2);
  });

  test('a 401 with no successful refresh surfaces the original 401 as an ApiException', () async {
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      accessToken: 'expired-token',
      httpClient: MockClient((request) async => http.Response('', 401)),
    );
    client.onUnauthorized = () async => null;

    await expectLater(
      client.get('/things'),
      throwsA(isA<ApiException>().having((e) => e.statusCode, 'statusCode', 401)),
    );
  });

  test('an empty response body is returned as null rather than a JSON decode error', () async {
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async => http.Response('', 204)),
    );

    final result = await client.delete('/things', authorized: false);

    expect(result, isNull);
  });
}
