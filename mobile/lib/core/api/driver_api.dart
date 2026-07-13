import '../models/charger_filter.dart';
import '../models/vehicle.dart';
import '../../features/map/map_query.dart';
import '../../features/map/map_screen.dart' show StartChargingResult;
import '../../features/map/pin_clustering.dart';
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
}
