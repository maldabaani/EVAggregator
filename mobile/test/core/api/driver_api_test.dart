import 'dart:convert';

import 'package:evagg_driver/core/api/api_client.dart';
import 'package:evagg_driver/core/api/driver_api.dart';
import 'package:evagg_driver/core/models/charger_filter.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _bbox = LatLngBounds(minLat: 25.05, minLng: 55.10, maxLat: 25.35, maxLng: 55.45);

void main() {
  test('fetchChargers maps the /map/chargers response into MapPin objects', () async {
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          expect(request.url.path, '/map/chargers');
          expect(request.url.queryParameters['bbox'], '25.05,55.1,25.35,55.45');
          return http.Response(
            jsonEncode({
              'data': [
                {'id': 'CP-1', 'name': 'Station 1', 'lat': 25.2, 'lng': 55.27, 'status': 'AVAILABLE'},
              ],
            }),
            200,
          );
        }),
      ),
    );

    final pins = await api.fetchChargers(_bbox, const ChargerFilter());

    expect(pins, hasLength(1));
    expect(pins.single.id, 'CP-1');
    expect(pins.single.lat, 25.2);
    expect(pins.single.lng, 55.27);
  });

  test('searchStations filters published station names by substring, case-insensitively', () async {
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          return http.Response(
            jsonEncode({
              'data': [
                {'id': 'CP-1', 'name': 'Downtown Mall', 'lat': 25.2, 'lng': 55.27},
                {'id': 'CP-2', 'name': 'Airport Terminal', 'lat': 25.3, 'lng': 55.4},
              ],
            }),
            200,
          );
        }),
      ),
    );

    final results = await api.searchStations('mall');

    expect(results, ['Downtown Mall']);
  });

  test('searchStations returns no results and makes no request for a blank query', () async {
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          fail('should not make a network request for a blank query');
        }),
      ),
    );

    final results = await api.searchStations('   ');

    expect(results, isEmpty);
  });

  test('createVehicle posts the vehicle fields and parses the created Vehicle', () async {
    late Map<String, dynamic> capturedBody;
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'id': 'v-1',
              'make': 'Tesla',
              'model': 'Model 3',
              'connector_type': 'CCS2',
              'battery_capacity_kwh': 75.0,
              'plug_and_charge_enabled': false,
            }),
            200,
          );
        }),
      ),
    );

    final vehicle = await api.createVehicle('Tesla', 'Model 3', 'CCS2', 75.0);

    expect(capturedBody['make'], 'Tesla');
    expect(vehicle.id, 'v-1');
    expect(vehicle.batteryCapacityKwh, 75.0);
  });

  test('setPlugAndCharge PATCHes the enabled flag to the right vehicle', () async {
    late String capturedPath;
    late String capturedMethod;
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          capturedPath = request.url.path;
          capturedMethod = request.method;
          return http.Response('', 200);
        }),
      ),
    );

    await api.setPlugAndCharge('v-1', true);

    expect(capturedPath, '/driver/vehicles/v-1/plug-and-charge');
    expect(capturedMethod, 'PATCH');
  });

  test('startCharging posts charger/connector and parses the session id', () async {
    late Map<String, dynamic> capturedBody;
    late String capturedPath;
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        accessToken: 'token-1',
        httpClient: MockClient((request) async {
          capturedPath = request.url.path;
          capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode({'session_id': 'session-1', 'charger_id': 'CP-1'}), 200);
        }),
      ),
    );

    final result = await api.startCharging('CP-1', 2);

    expect(capturedPath, '/charging/session/start/app');
    expect(capturedBody['charger_id'], 'CP-1');
    expect(capturedBody['connector_id'], 2);
    expect(result.sessionId, 'session-1');
  });

  test('stopCharging posts to the session stop path', () async {
    late String capturedPath;
    late String capturedMethod;
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          capturedPath = request.url.path;
          capturedMethod = request.method;
          return http.Response('', 200);
        }),
      ),
    );

    await api.stopCharging('session-1');

    expect(capturedPath, '/charging/session/session-1/stop');
    expect(capturedMethod, 'POST');
  });

  test('deleteVehicle sends a DELETE to the vehicle path', () async {
    late String capturedMethod;
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          capturedMethod = request.method;
          return http.Response('', 204);
        }),
      ),
    );

    await api.deleteVehicle('v-1');

    expect(capturedMethod, 'DELETE');
  });

  test('getWalletBalance parses balance_minor_units', () async {
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          expect(request.url.path, '/wallet/balance');
          return http.Response(jsonEncode({'balance_minor_units': 1234}), 200);
        }),
      ),
    );

    final balance = await api.getWalletBalance();

    expect(balance, 1234);
  });

  test('topUpWallet posts the amount, token, and currency', () async {
    late Map<String, dynamic> capturedBody;
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          expect(request.url.path, '/wallet/topup');
          capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response('', 200);
        }),
      ),
    );

    await api.topUpWallet(5000, 'tok-1', 'AED');

    expect(capturedBody['amount_minor_units'], 5000);
    expect(capturedBody['psp_token'], 'tok-1');
    expect(capturedBody['currency'], 'AED');
  });

  test('getPaymentMethod returns null when none is set', () async {
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async => http.Response(jsonEncode({'data': null}), 200)),
      ),
    );

    final method = await api.getPaymentMethod();

    expect(method, isNull);
  });

  test('getPaymentMethod parses a set payment method', () async {
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          return http.Response(
            jsonEncode({
              'data': {'type': 'direct_card', 'psp_token': 'tok-1', 'is_default': true},
            }),
            200,
          );
        }),
      ),
    );

    final method = await api.getPaymentMethod();

    expect(method?.type, 'direct_card');
    expect(method?.pspToken, 'tok-1');
  });

  test('setPaymentMethod posts type and psp_token and parses the response', () async {
    late Map<String, dynamic> capturedBody;
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          expect(request.url.path, '/wallet/payment-method');
          capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({'type': 'wallet_balance', 'psp_token': null, 'is_default': true}),
            200,
          );
        }),
      ),
    );

    final method = await api.setPaymentMethod('wallet_balance', null);

    expect(capturedBody['type'], 'wallet_balance');
    expect(method.type, 'wallet_balance');
  });

  test('reserveCharger posts charger/connector/expiry and parses the reservation', () async {
    late Map<String, dynamic> capturedBody;
    final expiresAt = DateTime.now().add(const Duration(hours: 1));
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          expect(request.url.path, '/driver/reservations');
          capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'id': 'r-1',
              'charger_id': 'CP-1',
              'connector_id': 1,
              'expires_at': expiresAt.toUtc().toIso8601String(),
            }),
            200,
          );
        }),
      ),
    );

    final reservation = await api.reserveCharger('CP-1', 1, expiresAt);

    expect(capturedBody['charger_id'], 'CP-1');
    expect(reservation.id, 'r-1');
  });

  test('fetchReservations parses the reservation list', () async {
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          expect(request.url.path, '/driver/reservations');
          return http.Response(
            jsonEncode({
              'data': [
                {'id': 'r-1', 'charger_id': 'CP-1', 'connector_id': 1, 'expires_at': '2026-01-01T00:00:00Z'},
              ],
            }),
            200,
          );
        }),
      ),
    );

    final reservations = await api.fetchReservations();

    expect(reservations, hasLength(1));
    expect(reservations.single.chargerId, 'CP-1');
  });

  test('cancelReservation sends a DELETE to the reservation path', () async {
    late String capturedMethod;
    late String capturedPath;
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          capturedMethod = request.method;
          capturedPath = request.url.path;
          return http.Response('', 204);
        }),
      ),
    );

    await api.cancelReservation('r-1');

    expect(capturedMethod, 'DELETE');
    expect(capturedPath, '/driver/reservations/r-1');
  });

  test('getRewards parses the balance and catalog', () async {
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          expect(request.url.path, '/driver/rewards');
          return http.Response(
            jsonEncode({
              'balance': 150,
              'catalog': [
                {'id': 'free-coffee', 'name': 'Free coffee voucher', 'points_cost': 100},
              ],
            }),
            200,
          );
        }),
      ),
    );

    final rewards = await api.getRewards();

    expect(rewards.balance, 150);
    expect(rewards.catalog.single.id, 'free-coffee');
    expect(rewards.catalog.single.pointsCost, 100);
  });

  test('redeemReward posts the reward id and parses the new balance', () async {
    late Map<String, dynamic> capturedBody;
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          expect(request.url.path, '/driver/rewards/redeem');
          capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode({'balance': 50}), 200);
        }),
      ),
    );

    final balance = await api.redeemReward('free-coffee');

    expect(capturedBody['reward_id'], 'free-coffee');
    expect(balance, 50);
  });

  test('planRoute posts the vehicle/origin/destination and parses the plan', () async {
    late Map<String, dynamic> capturedBody;
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          expect(request.url.path, '/driver/route-plan');
          capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'distance_km': 132.0,
              'duration_minutes': 90.0,
              'charging_stop_needed': true,
              'suggested_charger': {'id': 'CP-1', 'name': 'Station 1', 'lat': 24.4, 'lng': 54.3},
            }),
            200,
          );
        }),
      ),
    );

    final plan = await api.planRoute('v-1', 25.2, 55.3, 24.4, 54.3);

    expect(capturedBody['vehicle_id'], 'v-1');
    expect(capturedBody['origin'], {'lat': 25.2, 'lng': 55.3});
    expect(capturedBody['destination'], {'lat': 24.4, 'lng': 54.3});
    expect(plan.distanceKm, 132.0);
    expect(plan.chargingStopNeeded, isTrue);
    expect(plan.suggestedCharger?.id, 'CP-1');
  });

  test('planRoute parses a plan with no suggested charger', () async {
    final api = DriverApi(
      ApiClient(
        baseUrl: 'https://api.example.com',
        httpClient: MockClient((request) async {
          return http.Response(
            jsonEncode({
              'distance_km': 10.0,
              'duration_minutes': 8.0,
              'charging_stop_needed': false,
              'suggested_charger': null,
            }),
            200,
          );
        }),
      ),
    );

    final plan = await api.planRoute('v-1', 25.2, 55.3, 25.21, 55.31);

    expect(plan.chargingStopNeeded, isFalse);
    expect(plan.suggestedCharger, isNull);
  });
}
