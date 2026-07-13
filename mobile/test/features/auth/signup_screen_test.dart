import 'dart:convert';

import 'package:evagg_driver/core/api/api_client.dart';
import 'package:evagg_driver/core/auth/auth_session.dart';
import 'package:evagg_driver/features/auth/signup_screen.dart';
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

AuthSession _sessionWith(Future<http.Response> Function(http.Request) handler) {
  final client = ApiClient(baseUrl: 'https://api.example.com', httpClient: MockClient(handler));
  return AuthSession(apiClient: client, tokenStorage: _InMemoryTokenStorage());
}

void main() {
  testWidgets('successful signup logs the driver in', (tester) async {
    final session = _sessionWith((request) async {
      expect(request.url.path, '/auth/signup');
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      expect(body['full_name'], 'Jane Driver');
      return http.Response(
        jsonEncode({
          'access_token': 'a',
          'refresh_token': 'r',
          'driver': {'id': 'd-1', 'email': 'driver@example.com', 'full_name': 'Jane Driver'},
        }),
        200,
      );
    });

    await tester.pumpWidget(MaterialApp(
      home: SignupScreen(authSession: session, onSwitchToLogin: () {}),
    ));
    await tester.enterText(find.byKey(const Key('signup-full-name-field')), 'Jane Driver');
    await tester.enterText(find.byKey(const Key('signup-email-field')), 'driver@example.com');
    await tester.enterText(find.byKey(const Key('signup-password-field')), 'hunter2');
    await tester.tap(find.byKey(const Key('signup-submit-button')));
    await tester.pumpAndSettle();

    expect(session.isAuthenticated, isTrue);
  });

  testWidgets('a failed signup (e.g. email already registered) shows an inline error', (tester) async {
    final session = _sessionWith((request) async => http.Response(jsonEncode({'detail': 'already registered'}), 409));

    await tester.pumpWidget(MaterialApp(
      home: SignupScreen(authSession: session, onSwitchToLogin: () {}),
    ));
    await tester.enterText(find.byKey(const Key('signup-full-name-field')), 'Jane Driver');
    await tester.enterText(find.byKey(const Key('signup-email-field')), 'driver@example.com');
    await tester.enterText(find.byKey(const Key('signup-password-field')), 'hunter2');
    await tester.tap(find.byKey(const Key('signup-submit-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('signup-error')), findsOneWidget);
    expect(session.isAuthenticated, isFalse);
  });
}
