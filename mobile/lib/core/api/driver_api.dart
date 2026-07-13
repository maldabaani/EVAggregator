import '../models/charger_filter.dart';
import '../models/payment_method.dart';
import '../models/reservation.dart';
import '../models/reward.dart';
import '../models/route_plan.dart';
import '../models/vehicle.dart';
import '../../features/analytics/usage_insights.dart';
import '../../features/map/map_query.dart';
import '../../features/map/map_screen.dart' show StartChargingResult;
import '../../features/map/pin_clustering.dart';
import '../../features/session/session_tracking.dart';
import 'api_client.dart';

/// Covers the whole planet — used only for the location-name search below,
/// which has no dedicated geocoding endpoint to call, unlike the map's pin
/// fetch (which always passes the current viewport's real bbox).
const LatLngBounds worldBounds = LatLngBounds(minLat: -90, minLng: -180, maxLat: 90, maxLng: 180);

/// The mobile app's backend facade: translates typed calls into the actual
/// `GET /map/chargers` and `/driver/vehicles` REST contracts, so screens
/// depend on plain Dart types/functions (matching their existing
/// `PinsFetcher`/`SearchExecutor`-style injection) rather than on
/// [ApiClient] or JSON shapes directly.
class DriverApi {
  final ApiClient client;

  DriverApi(this.client);

  Future<List<MapPin>> fetchChargers(LatLngBounds bbox, ChargerFilter filter) async {
    final response = await client.get(
      '/map/chargers',
      query: buildMapQueryParams(bbox, filter),
      authorized: false,
    );
    final data = (response as Map<String, dynamic>)['data'] as List<dynamic>;
    return data
        .map(
          (item) => MapPin(
            id: item['id'] as String,
            lat: (item['lat'] as num).toDouble(),
            lng: (item['lng'] as num).toDouble(),
          ),
        )
        .toList();
  }

  /// No geocoding backend exists yet, so this searches published station
  /// *names* by substring rather than resolving arbitrary place names —
  /// honest about what it can do rather than faking a richer search.
  Future<List<String>> searchStations(String query) async {
    final trimmed = query.trim();
    if (trimmed.isEmpty) return [];
    final response = await client.get(
      '/map/chargers',
      query: buildMapQueryParams(worldBounds, const ChargerFilter()),
      authorized: false,
    );
    final data = (response as Map<String, dynamic>)['data'] as List<dynamic>;
    final lowerQuery = trimmed.toLowerCase();
    return data
        .map((item) => (item['name'] as String?) ?? (item['id'] as String))
        .where((name) => name.toLowerCase().contains(lowerQuery))
        .toList();
  }

  Future<List<Vehicle>> fetchVehicles() async {
    final response = await client.get('/driver/vehicles');
    final data = (response as Map<String, dynamic>)['data'] as List<dynamic>;
    return data.map((item) => Vehicle.fromJson(item as Map<String, dynamic>)).toList();
  }

  Future<Vehicle> createVehicle(String make, String model, String connectorType, double batteryCapacityKwh) async {
    final response = await client.post(
      '/driver/vehicles',
      body: {
        'make': make,
        'model': model,
        'connector_type': connectorType,
        'battery_capacity_kwh': batteryCapacityKwh,
      },
    );
    return Vehicle.fromJson(response as Map<String, dynamic>);
  }

  Future<void> setPlugAndCharge(String vehicleId, bool enabled) async {
    await client.patch('/driver/vehicles/$vehicleId/plug-and-charge', body: {'enabled': enabled});
  }

  Future<void> deleteVehicle(String vehicleId) async {
    await client.delete('/driver/vehicles/$vehicleId');
  }

  /// `driver_id` is required by the request shape but always overwritten
  /// server-side (see evagg.driver_app.session_start_forwarder) with the
  /// identity from this call's own bearer token, so it's sent empty here.
  Future<StartChargingResult> startCharging(String chargerId, int connectorId) async {
    final response = await client.post(
      '/charging/session/start/app',
      body: {'charger_id': chargerId, 'connector_id': connectorId, 'driver_id': ''},
    );
    final map = response as Map<String, dynamic>;
    return StartChargingResult(sessionId: map['session_id'] as String);
  }

  Future<void> stopCharging(String sessionId) async {
    await client.post('/charging/session/$sessionId/stop');
  }

  Future<SessionSnapshot> getSessionLiveStatus(String sessionId) async {
    final response = await client.get('/charging/session/$sessionId/live') as Map<String, dynamic>;
    return SessionSnapshot(
      status: SessionStatus.values.firstWhere(
        (s) => s.name == response['status'],
        orElse: () => SessionStatus.charging,
      ),
      energyKwh: (response['energy_kwh'] as num).toDouble(),
      powerKw: (response['power_kw'] as num).toDouble(),
      costMinorUnits: response['cost_minor_units'] as int,
      currency: response['currency'] as String,
      startedAt: DateTime.parse(response['started_at'] as String),
      updatedAt: DateTime.parse(response['updated_at'] as String),
    );
  }

  Future<int> getWalletBalance() async {
    final response = await client.get('/wallet/balance');
    return (response as Map<String, dynamic>)['balance_minor_units'] as int;
  }

  Future<void> topUpWallet(int amountMinorUnits, String pspToken, String currency) async {
    await client.post(
      '/wallet/topup',
      body: {
        'wallet_id': '',
        'psp_token': pspToken,
        'amount_minor_units': amountMinorUnits,
        'currency': currency,
      },
    );
  }

  Future<PaymentMethod?> getPaymentMethod() async {
    final response = await client.get('/wallet/payment-method');
    final data = (response as Map<String, dynamic>)['data'];
    return data == null ? null : PaymentMethod.fromJson(data as Map<String, dynamic>);
  }

  Future<PaymentMethod> setPaymentMethod(String type, String? pspToken) async {
    final response = await client.post('/wallet/payment-method', body: {'type': type, 'psp_token': pspToken});
    return PaymentMethod.fromJson(response as Map<String, dynamic>);
  }

  Future<Reservation> reserveCharger(String chargerId, int connectorId, DateTime expiresAt) async {
    final response = await client.post(
      '/driver/reservations',
      body: {'charger_id': chargerId, 'connector_id': connectorId, 'expires_at': expiresAt.toUtc().toIso8601String()},
    );
    return Reservation.fromJson(response as Map<String, dynamic>);
  }

  Future<List<Reservation>> fetchReservations() async {
    final response = await client.get('/driver/reservations');
    final data = (response as Map<String, dynamic>)['data'] as List<dynamic>;
    return data.map((item) => Reservation.fromJson(item as Map<String, dynamic>)).toList();
  }

  Future<void> cancelReservation(String reservationId) async {
    await client.delete('/driver/reservations/$reservationId');
  }

  /// `driver_id` isn't sent — the rewards forwarder always scopes the
  /// balance/redemption to the caller's own verified identity.
  Future<RewardsSummary> getRewards() async {
    final response = await client.get('/driver/rewards');
    return RewardsSummary.fromJson(response as Map<String, dynamic>);
  }

  Future<int> redeemReward(String rewardId) async {
    final response = await client.post('/driver/rewards/redeem', body: {'driver_id': '', 'reward_id': rewardId});
    return (response as Map<String, dynamic>)['balance'] as int;
  }

  /// `date_from`/`date_to` are calendar dates (no time component) — the
  /// backend's `GET /driver/usage-insights` groups by day, so only the
  /// date part matters.
  Future<List<DailyUsagePoint>> getUsageInsights(DateTime from, DateTime to) async {
    String isoDate(DateTime d) =>
        '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    final response = await client.get(
      '/driver/usage-insights',
      query: {'date_from': isoDate(from), 'date_to': isoDate(to)},
    ) as Map<String, dynamic>;
    final data = response['data'] as List<dynamic>;
    return data.map((item) => DailyUsagePoint.fromJson(item as Map<String, dynamic>)).toList();
  }

  Future<RoutePlanResult> planRoute(
    String vehicleId,
    double originLat,
    double originLng,
    double destinationLat,
    double destinationLng,
  ) async {
    final response = await client.post(
      '/driver/route-plan',
      body: {
        'vehicle_id': vehicleId,
        'origin': {'lat': originLat, 'lng': originLng},
        'destination': {'lat': destinationLat, 'lng': destinationLng},
      },
    );
    return RoutePlanResult.fromJson(response as Map<String, dynamic>);
  }
}
