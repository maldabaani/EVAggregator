import 'dart:convert';

import 'package:evagg_driver/core/api/api_client.dart';
import 'package:evagg_driver/core/auth/auth_session.dart';
import 'package:evagg_driver/features/auth/login_screen.dart';
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
  testWidgets('successful login clears the error and calls AuthSession.login', (tester) async {
    final session = _sessionWith((request) async {
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
      home: LoginScreen(authSession: session, onSwitchToSignup: () {}),
    ));
    await tester.enterText(find.byKey(const Key('login-email-field')), 'driver@example.com');
    await tester.enterText(find.byKey(const Key('login-password-field')), 'hunter2');
    await tester.tap(find.byKey(const Key('login-submit-button')));
    await tester.pumpAndSettle();

    expect(session.isAuthenticated, isTrue);
    expect(find.byKey(const Key('login-error')), findsNothing);
  });

  testWidgets('a failed login shows an inline error and stays on the login screen', (tester) async {
    final session = _sessionWith((request) async => http.Response(jsonEncode({'detail': 'invalid'}), 401));

    await tester.pumpWidget(MaterialApp(
      home: LoginScreen(authSession: session, onSwitchToSignup: () {}),
    ));
    await tester.enterText(find.byKey(const Key('login-email-field')), 'driver@example.com');
    await tester.enterText(find.byKey(const Key('login-password-field')), 'wrong');
    await tester.tap(find.byKey(const Key('login-submit-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-error')), findsOneWidget);
    expect(session.isAuthenticated, isFalse);
  });

  testWidgets('tapping the switch-to-signup link invokes the callback', (tester) async {
    final session = _sessionWith((request) async => http.Response('', 500));
    var switched = false;

    await tester.pumpWidget(MaterialApp(
      home: LoginScreen(authSession: session, onSwitchToSignup: () => switched = true),
    ));
    await tester.tap(find.byKey(const Key('switch-to-signup-button')));

    expect(switched, isTrue);
  });
}
