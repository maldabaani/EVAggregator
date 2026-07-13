import 'dart:convert';

import 'package:evagg_driver/core/api/api_client.dart';
import 'package:evagg_driver/core/auth/auth_session.dart';
import 'package:evagg_driver/core/models/reservation.dart';
import 'package:evagg_driver/core/models/reward.dart';
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

  AuthSession loggedInSession() {
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
    return AuthSession(apiClient: client, tokenStorage: _InMemoryTokenStorage());
  }

  testWidgets('shows an empty state when there are no reservations', (tester) async {
    final session = loggedInSession();
    await session.login(email: 'driver@example.com', password: 'hunter2');

    await tester.pumpWidget(MaterialApp(
      home: AccountScreen(
        authSession: session,
        fetchReservations: () async => [],
        cancelReservation: (id) async {},
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('reservations-empty')), findsOneWidget);
  });

  testWidgets('lists reservations and cancels one on tap', (tester) async {
    final session = loggedInSession();
    await session.login(email: 'driver@example.com', password: 'hunter2');
    var reservations = [
      Reservation(id: 'r-1', chargerId: 'CP-1', connectorId: 1, expiresAt: DateTime.now().add(const Duration(hours: 1))),
    ];
    String? canceledId;

    await tester.pumpWidget(MaterialApp(
      home: AccountScreen(
        authSession: session,
        fetchReservations: () async => reservations,
        cancelReservation: (id) async {
          canceledId = id;
          reservations = [];
        },
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('reservation-tile-r-1')), findsOneWidget);

    await tester.tap(find.byKey(const Key('cancel-reservation-button-r-1')));
    await tester.pumpAndSettle();

    expect(canceledId, 'r-1');
    expect(find.byKey(const Key('reservation-tile-r-1')), findsNothing);
  });

  testWidgets('shows an error when loading reservations fails', (tester) async {
    final session = loggedInSession();
    await session.login(email: 'driver@example.com', password: 'hunter2');

    await tester.pumpWidget(MaterialApp(
      home: AccountScreen(
        authSession: session,
        fetchReservations: () async => throw Exception('boom'),
        cancelReservation: (id) async {},
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('reservations-error')), findsOneWidget);
  });

  testWidgets('no reservations section appears when fetchReservations is not provided', (tester) async {
    final session = loggedInSession();
    await session.login(email: 'driver@example.com', password: 'hunter2');

    await tester.pumpWidget(MaterialApp(home: AccountScreen(authSession: session)));
    await tester.pumpAndSettle();

    expect(find.text('My reservations'), findsNothing);
  });

  testWidgets('shows the rewards balance and catalog', (tester) async {
    final session = loggedInSession();
    await session.login(email: 'driver@example.com', password: 'hunter2');

    await tester.pumpWidget(MaterialApp(
      home: AccountScreen(
        authSession: session,
        fetchRewards: () async => const RewardsSummary(
          balance: 150,
          catalog: [RewardCatalogItem(id: 'free-coffee', name: 'Free coffee voucher', pointsCost: 100)],
        ),
        redeemReward: (id) async => 50,
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('rewards-balance')), findsOneWidget);
    expect(find.text('150 points'), findsOneWidget);
    expect(find.byKey(const Key('reward-tile-free-coffee')), findsOneWidget);
  });

  testWidgets('redeeming a reward calls redeemReward and refreshes the balance', (tester) async {
    final session = loggedInSession();
    await session.login(email: 'driver@example.com', password: 'hunter2');
    var balance = 150;
    String? redeemedId;

    await tester.pumpWidget(MaterialApp(
      home: AccountScreen(
        authSession: session,
        fetchRewards: () async => RewardsSummary(
          balance: balance,
          catalog: const [RewardCatalogItem(id: 'free-coffee', name: 'Free coffee voucher', pointsCost: 100)],
        ),
        redeemReward: (id) async {
          redeemedId = id;
          balance -= 100;
          return balance;
        },
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('redeem-reward-button-free-coffee')));
    await tester.pumpAndSettle();

    expect(redeemedId, 'free-coffee');
    expect(find.text('50 points'), findsOneWidget);
  });

  testWidgets('disables redeem when balance is below the points cost', (tester) async {
    final session = loggedInSession();
    await session.login(email: 'driver@example.com', password: 'hunter2');

    await tester.pumpWidget(MaterialApp(
      home: AccountScreen(
        authSession: session,
        fetchRewards: () async => const RewardsSummary(
          balance: 10,
          catalog: [RewardCatalogItem(id: 'free-coffee', name: 'Free coffee voucher', pointsCost: 100)],
        ),
        redeemReward: (id) async => 10,
      ),
    ));
    await tester.pumpAndSettle();

    final button = tester.widget<ElevatedButton>(find.byKey(const Key('redeem-reward-button-free-coffee')));
    expect(button.onPressed, isNull);
  });

  testWidgets('shows an error when loading rewards fails', (tester) async {
    final session = loggedInSession();
    await session.login(email: 'driver@example.com', password: 'hunter2');

    await tester.pumpWidget(MaterialApp(
      home: AccountScreen(
        authSession: session,
        fetchRewards: () async => throw Exception('boom'),
        redeemReward: (id) async => 0,
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('rewards-error')), findsOneWidget);
  });

  testWidgets('no rewards section appears when fetchRewards is not provided', (tester) async {
    final session = loggedInSession();
    await session.login(email: 'driver@example.com', password: 'hunter2');

    await tester.pumpWidget(MaterialApp(home: AccountScreen(authSession: session)));
    await tester.pumpAndSettle();

    expect(find.text('Rewards'), findsNothing);
  });
}
