import 'dart:convert';

import 'package:evagg_driver/core/api/api_client.dart';
import 'package:evagg_driver/core/auth/auth_session.dart';
import 'package:evagg_driver/features/account/account_screen.dart';
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
  testWidgets('shows the logged-in driver\'s name and email', (tester) async {
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        return http.Response(
          jsonEncode({
            'access_token': 'a',
            'refresh_token': 'r',
            'driver': {'id': 'd-1', 'email': 'driver@example.com', 'full_name': 'Jane Driver'},
          }),
          200,
        );
      }),
    );
    final session = AuthSession(apiClient: client, tokenStorage: _InMemoryTokenStorage());
    await session.login(email: 'driver@example.com', password: 'hunter2');

    await tester.pumpWidget(MaterialApp(home: AccountScreen(authSession: session)));

    expect(find.text('Jane Driver'), findsOneWidget);
    expect(find.text('driver@example.com'), findsOneWidget);
  });

  testWidgets('tapping Log out calls AuthSession.logout', (tester) async {
    final client = ApiClient(
      baseUrl: 'https://api.example.com',
      httpClient: MockClient((request) async {
        return http.Response(
          jsonEncode({
            'access_token': 'a',
            'refresh_token': 'r',
            'driver': {'id': 'd-1', 'email': 'driver@example.com', 'full_name': 'Jane Driver'},
          }),
          200,
        );
      }),
    );
    final session = AuthSession(apiClient: client, tokenStorage: _InMemoryTokenStorage());
    await session.login(email: 'driver@example.com', password: 'hunter2');

    await tester.pumpWidget(MaterialApp(home: AccountScreen(authSession: session)));
    await tester.tap(find.byKey(const Key('logout-button')));
    await tester.pumpAndSettle();

    expect(session.isAuthenticated, isFalse);
  });
}
