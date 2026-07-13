import 'dart:convert';

import 'package:evagg_driver/core/api/api_client.dart';
import 'package:evagg_driver/core/auth/auth_session.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class InMemoryTokenStorage implements TokenStorage {
  String? stored;

  @override
  Future<String?> readRefreshToken() async => stored;

  @override
  Future<void> saveRefreshToken(String token) async => stored = token;

  @override
  Future<void> clearRefreshToken() async => stored = null;
}

http.Response _sessionResponse({
  String accessToken = 'access-1',
  String refreshToken = 'refresh-1',
  String driverId = 'driver-1',
}) {
  return http.Response(
    jsonEncode({
      'access_token': accessToken,
      'refresh_token': refreshToken,
      'driver': {'id': driverId, 'email': 'driver@example.com', 'full_name': 'Jane Driver'},
    }),
    200,
  );
}

void main() {
  test('login populates the driver profile and persists the refresh token', () async {
    final storage = InMemoryTokenStorage();
    final apiClient = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        expect(request.url.path, '/auth/login');
        return _sessionResponse();
      }),
    );
    final session = AuthSession(apiClient: apiClient, tokenStorage: storage);

    await session.login(email: 'driver@example.com', password: 'hunter2');

    expect(session.isAuthenticated, isTrue);
    expect(session.driver?.email, 'driver@example.com');
    expect(apiClient.accessToken, 'access-1');
    expect(storage.stored, 'refresh-1');
  });

  test('signup populates the driver profile the same way login does', () async {
    final apiClient = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        expect(request.url.path, '/auth/signup');
        return _sessionResponse(driverId: 'driver-2');
      }),
    );
    final session = AuthSession(apiClient: apiClient, tokenStorage: InMemoryTokenStorage());

    await session.signup(email: 'driver@example.com', fullName: 'Jane Driver', password: 'hunter2');

    expect(session.driver?.id, 'driver-2');
  });

  test('a failed login throws and leaves the session unauthenticated', () async {
    final apiClient = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async => http.Response(jsonEncode({'detail': 'invalid'}), 401)),
    );
    final session = AuthSession(apiClient: apiClient, tokenStorage: InMemoryTokenStorage());

    await expectLater(session.login(email: 'x@example.com', password: 'wrong'), throwsA(isA<ApiException>()));
    expect(session.isAuthenticated, isFalse);
  });

  test('logout clears the driver, the access token, and the persisted refresh token', () async {
    final storage = InMemoryTokenStorage();
    final apiClient = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async => _sessionResponse()),
    );
    final session = AuthSession(apiClient: apiClient, tokenStorage: storage);
    await session.login(email: 'driver@example.com', password: 'hunter2');

    await session.logout();

    expect(session.isAuthenticated, isFalse);
    expect(apiClient.accessToken, isNull);
    expect(storage.stored, isNull);
  });

  test('restoreSession silently logs the driver back in from a stored refresh token', () async {
    final storage = InMemoryTokenStorage()..stored = 'stored-refresh-token';
    final apiClient = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        expect(request.url.path, '/auth/refresh');
        expect(jsonDecode(request.body), {'refresh_token': 'stored-refresh-token'});
        return _sessionResponse(accessToken: 'restored-access');
      }),
    );
    final session = AuthSession(apiClient: apiClient, tokenStorage: storage);

    await session.restoreSession();

    expect(session.isRestoring, isFalse);
    expect(session.isAuthenticated, isTrue);
    expect(apiClient.accessToken, 'restored-access');
  });

  test('restoreSession with no stored refresh token leaves the session unauthenticated', () async {
    final apiClient = ApiClient(baseUrl: 'https://api.example.com', httpClient: MockClient((r) async => http.Response('', 500)));
    final session = AuthSession(apiClient: apiClient, tokenStorage: InMemoryTokenStorage());

    await session.restoreSession();

    expect(session.isRestoring, isFalse);
    expect(session.isAuthenticated, isFalse);
  });

  test('restoreSession with a stale/rejected refresh token clears storage rather than looping', () async {
    final storage = InMemoryTokenStorage()..stored = 'stale-token';
    final apiClient = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async => http.Response(jsonEncode({'detail': 'expired'}), 401)),
    );
    final session = AuthSession(apiClient: apiClient, tokenStorage: storage);

    await session.restoreSession();

    expect(session.isAuthenticated, isFalse);
    expect(storage.stored, isNull);
  });

  test('an ambient 401 during a normal API call silently refreshes without notifying listeners', () async {
    final storage = InMemoryTokenStorage();
    final apiClient = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        if (request.url.path == '/auth/login') {
          return _sessionResponse(accessToken: 'about-to-expire');
        }
        if (request.url.path == '/auth/refresh') {
          return _sessionResponse(accessToken: 'new-access-token');
        }
        if (request.headers['Authorization'] == 'Bearer about-to-expire') {
          return http.Response('', 401);
        }
        return http.Response(jsonEncode({'ok': true}), 200);
      }),
    );
    final session = AuthSession(apiClient: apiClient, tokenStorage: storage);
    await session.login(email: 'driver@example.com', password: 'hunter2');

    var notifyCount = 0;
    session.addListener(() => notifyCount++);
    final result = await apiClient.get('/driver/vehicles');

    expect(result, {'ok': true});
    expect(notifyCount, 0);
  });
}
