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
}
