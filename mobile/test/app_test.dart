import 'dart:convert';

import 'package:evagg_driver/app.dart';
import 'package:evagg_driver/core/api/api_client.dart';
import 'package:evagg_driver/core/auth/auth_session.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _InMemoryTokenStorage implements TokenStorage {
  String? stored;
  @override
  Future<String?> readRefreshToken() async => stored;
  @override
  Future<void> saveRefreshToken(String token) async => stored = token;
  @override
  Future<void> clearRefreshToken() async => stored = null;
}

void main() {
  testWidgets('an unauthenticated driver sees the login screen after session restore settles', (tester) async {
    final client = ApiClient(baseUrl: 'https://api.example.com', httpClient: MockClient((r) async => http.Response('', 500)));
    final session = AuthSession(apiClient: client, tokenStorage: _InMemoryTokenStorage());

    await tester.pumpWidget(EvAggregatorApp(apiClient: client, authSession: session));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-email-field')), findsOneWidget);
  });

  testWidgets('logging in reveals the authenticated app shell with its bottom nav', (tester) async {
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        if (request.url.path == '/auth/login') {
          return http.Response(
            jsonEncode({
              'access_token': 'a',
              'refresh_token': 'r',
              'driver': {'id': 'd-1', 'email': 'driver@example.com', 'full_name': 'Jane Driver'},
            }),
            200,
          );
        }
        // The app shell mounts MapScreen immediately, which fetches pins —
        // an empty result is enough to prove the shell itself rendered.
        return http.Response(jsonEncode({'data': []}), 200);
      }),
    );
    final session = AuthSession(apiClient: client, tokenStorage: _InMemoryTokenStorage());

    await tester.pumpWidget(EvAggregatorApp(apiClient: client, authSession: session));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('login-email-field')), 'driver@example.com');
    await tester.enterText(find.byKey(const Key('login-password-field')), 'hunter2');
    await tester.tap(find.byKey(const Key('login-submit-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('app-bottom-nav')), findsOneWidget);
  });

  testWidgets('switching to signup and back toggles between the two screens', (tester) async {
    final client = ApiClient(baseUrl: 'https://api.example.com', httpClient: MockClient((r) async => http.Response('', 500)));
    final session = AuthSession(apiClient: client, tokenStorage: _InMemoryTokenStorage());

    await tester.pumpWidget(EvAggregatorApp(apiClient: client, authSession: session));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('switch-to-signup-button')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('signup-email-field')), findsOneWidget);

    await tester.tap(find.byKey(const Key('switch-to-login-button')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('login-email-field')), findsOneWidget);
  });
}
