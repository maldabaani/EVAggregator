import 'package:flutter/material.dart';
// Both flutter_map and core/models/charger_filter.dart declare a
// `LatLngBounds` class — ours is the app's bbox-query type, flutter_map's is
// its own internal viewport-bounds type, which this screen never needs.
import 'package:flutter_map/flutter_map.dart' hide LatLngBounds;
import 'package:latlong2/latlong.dart' as ll;

import '../../core/live_activity/live_activity_controller.dart';
import '../../core/models/charger_filter.dart';
import '../../core/models/reservation.dart';
import '../session/live_session_screen.dart';
import '../session/session_tracking.dart';
import 'live_status_feed.dart';
import 'pin_clustering.dart';
import 'search_debouncer.dart';

/// Task 5.1/5.4-followup — live map discovery screen. Renders on
/// `flutter_map` over OpenStreetMap tiles (no API key/vendor account
/// needed, unlike Google Maps/Mapbox), with the filter/search/clustering/
/// presence logic (already unit tested in isolation in map_query.dart,
/// live_status_feed.dart, pin_clustering.dart, search_debouncer.dart)
/// wired to real markers instead of a placeholder.
typedef PinsFetcher = Future<List<MapPin>> Function(LatLngBounds bbox, ChargerFilter filter);

class StartChargingResult {
  final String sessionId;

  const StartChargingResult({required this.sessionId});
}

typedef StartChargingHandler = Future<StartChargingResult> Function(String chargerId, int connectorId);
typedef StopChargingHandler = Future<void> Function(String sessionId);
typedef LiveSessionFetcher = Future<SessionSnapshot> Function(String sessionId);
typedef ReserveHandler = Future<Reservation> Function(String chargerId, int connectorId, DateTime expiresAt);
typedef CancelReservationHandler = Future<void> Function(String reservationId);

const ll.LatLng defaultMapCenter = ll.LatLng(25.2048, 55.2708); // Dubai
const LatLngBounds defaultMapBounds = LatLngBounds(minLat: 25.05, minLng: 55.10, maxLat: 25.35, maxLng: 55.45);
const double defaultInitialZoom = 13;

class MapScreen extends StatefulWidget {
  final SearchExecutor searchExecutor;
  final PinsFetcher pinsFetcher;
  final LiveStatusFeedController? statusFeed;
  final TileProvider? tileProvider;
  final StartChargingHandler? onStartCharging;
  final StopChargingHandler? onStopCharging;
  final ReserveHandler? onReserve;
  final CancelReservationHandler? onCancelReservation;
  final LiveActivityController liveActivityController;
  final LiveSessionFetcher? onFetchLiveSession;

  const MapScreen({
    super.key,
    required this.searchExecutor,
    required this.pinsFetcher,
    this.statusFeed,
    this.tileProvider,
    this.onStartCharging,
    this.onStopCharging,
    this.onReserve,
    this.onCancelReservation,
    this.liveActivityController = const NoopLiveActivityController(),
    this.onFetchLiveSession,
  });

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  late final DebouncedSearchController _searchController;
  late final LiveStatusFeedController _statusFeed;
  final MapController _mapController = MapController();
  ChargerFilter _filter = const ChargerFilter();
  List<String> _searchResults = [];
  List<MapPin> _pins = [];
  double _zoom = defaultInitialZoom;

  @override
  void initState() {
    super.initState();
    _searchController = DebouncedSearchController(executor: widget.searchExecutor);
    _statusFeed = widget.statusFeed ?? LiveStatusFeedController();
    _loadPins();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadPins() async {
    final pins = await widget.pinsFetcher(defaultMapBounds, _filter);
    if (mounted) setState(() => _pins = pins);
  }

  void _onSearchChanged(String query) {
    _searchController.search(query, (results) {
      if (mounted) {
        setState(() => _searchResults = results);
      }
    });
  }

  void _toggleAvailableOnly(bool value) {
    setState(() => _filter = _filter.copyWith(availableOnly: value));
    _loadPins();
  }

  Color _colorForPin(String chargerId) {
    final state = _statusFeed.displayStateFor(chargerId);
    if (state.stale) return Colors.grey;
    switch (state.status) {
      case ChargerPresenceStatus.online:
        return Colors.green;
      case ChargerPresenceStatus.offline:
        return Colors.red;
      case ChargerPresenceStatus.unknown:
        return Colors.grey;
    }
  }

  void _onClusterTapped(ClusterGroup cluster) {
    if (cluster.count > 1) {
      // A multi-pin cluster zooms in rather than showing detail for many
      // chargers at once — the individual pins resolve once zoomed enough
      // to cross clusterZoomThreshold.
      _mapController.move(ll.LatLng(cluster.lat, cluster.lng), _zoom + 2);
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => SafeArea(
        key: const Key('charger-detail-sheet'),
        child: _StationDetailSheet(
          chargerId: cluster.pins.first.id,
          onStartCharging: widget.onStartCharging,
          onStopCharging: widget.onStopCharging,
          onReserve: widget.onReserve,
          onCancelReservation: widget.onCancelReservation,
          liveActivityController: widget.liveActivityController,
          onFetchLiveSession: widget.onFetchLiveSession,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final clusters = clusterPins(_pins, _zoom);

    return Scaffold(
      appBar: AppBar(title: const Text('Find a charger')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              key: const Key('map-search-field'),
              decoration: const InputDecoration(hintText: 'Search location'),
              onChanged: _onSearchChanged,
            ),
          ),
          SwitchListTile(
            key: const Key('available-only-switch'),
            title: const Text('Available only'),
            value: _filter.availableOnly,
            onChanged: _toggleAvailableOnly,
          ),
          if (_searchResults.isNotEmpty)
            Expanded(
              child: ListView(
                key: const Key('search-results-list'),
                children: _searchResults.map((r) => ListTile(title: Text(r))).toList(),
              ),
            )
          else
            Expanded(
              child: FlutterMap(
                mapController: _mapController,
                options: MapOptions(
                  initialCenter: defaultMapCenter,
                  initialZoom: defaultInitialZoom,
                  onPositionChanged: (position, hasGesture) {
                    final zoom = position.zoom;
                    if (zoom != _zoom) {
                      setState(() => _zoom = zoom);
                    }
                  },
                ),
                children: [
                  TileLayer(
                    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'com.evagg.driver',
                    tileProvider: widget.tileProvider,
                  ),
                  MarkerLayer(
                    key: const Key('map-marker-layer'),
                    markers: clusters
                        .map(
                          (cluster) => Marker(
                            point: ll.LatLng(cluster.lat, cluster.lng),
                            width: 44,
                            height: 44,
                            child: GestureDetector(
                              key: Key('map-pin-${cluster.pins.first.id}'),
                              onTap: () => _onClusterTapped(cluster),
                              child: _PinMarker(
                                count: cluster.count,
                                color: cluster.count == 1 ? _colorForPin(cluster.pins.first.id) : Colors.blueAccent,
                              ),
                            ),
                          ),
                        )
                        .toList(),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _PinMarker extends StatelessWidget {
  final int count;
  final Color color;

  const _PinMarker({required this.count, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(color: color, shape: BoxShape.circle, border: Border.all(color: Colors.white, width: 2)),
      alignment: Alignment.center,
      child: count > 1
          ? Text('$count', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold))
          : const Icon(Icons.ev_station, color: Colors.white, size: 20),
    );
  }
}

/// The charger-detail bottom sheet's "Start Charging"/"Stop Charging" and
/// "Reserve"/"Cancel reservation" sections. Each is only shown when its
/// handler is injected — the map screen is reused in places (or in tests)
/// with no session-start/reservation capability at all. There's no live
/// energy/power/cost shown here once charging starts — no read-side query
/// for meter values exists in the backend yet — so this only ever reports
/// whether a session was started/stopped, not what it's doing.
class _StationDetailSheet extends StatefulWidget {
  final String chargerId;
  final StartChargingHandler? onStartCharging;
  final StopChargingHandler? onStopCharging;
  final ReserveHandler? onReserve;
  final CancelReservationHandler? onCancelReservation;
  final LiveActivityController liveActivityController;
  final LiveSessionFetcher? onFetchLiveSession;

  const _StationDetailSheet({
    required this.chargerId,
    this.onStartCharging,
    this.onStopCharging,
    this.onReserve,
    this.onCancelReservation,
    this.liveActivityController = const NoopLiveActivityController(),
    this.onFetchLiveSession,
  });

  @override
  State<_StationDetailSheet> createState() => _StationDetailSheetState();
}

const Map<int, String> _reservationDurationLabels = {30: '30 minutes', 60: '1 hour', 120: '2 hours'};

class _StationDetailSheetState extends State<_StationDetailSheet> {
  int _connectorId = 1;
  bool _starting = false;
  bool _stopping = false;
  bool _stopped = false;
  String? _error;
  String? _startedSessionId;

  int _reservationDurationMinutes = 60;
  bool _reserving = false;
  bool _cancelingReservation = false;
  bool _reservationCanceled = false;
  String? _reservationError;
  Reservation? _reservation;

  Future<void> _start() async {
    setState(() {
      _starting = true;
      _error = null;
    });
    try {
      final result = await widget.onStartCharging!(widget.chargerId, _connectorId);
      await widget.liveActivityController.startChargingActivity(
        sessionId: result.sessionId,
        chargerId: widget.chargerId,
        connectorId: _connectorId,
      );
      if (!mounted) return;
      setState(() => _startedSessionId = result.sessionId);
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Could not start charging. Please try again.');
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  Future<void> _stop() async {
    setState(() {
      _stopping = true;
      _error = null;
    });
    try {
      await widget.onStopCharging!(_startedSessionId!);
      await widget.liveActivityController.endChargingActivity(_startedSessionId!);
      if (!mounted) return;
      setState(() => _stopped = true);
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Could not stop charging. Please try again.');
    } finally {
      if (mounted) setState(() => _stopping = false);
    }
  }

  Future<void> _reserve() async {
    setState(() {
      _reserving = true;
      _reservationError = null;
    });
    try {
      final expiresAt = DateTime.now().add(Duration(minutes: _reservationDurationMinutes));
      final reservation = await widget.onReserve!(widget.chargerId, _connectorId, expiresAt);
      if (!mounted) return;
      setState(() => _reservation = reservation);
    } catch (_) {
      if (!mounted) return;
      setState(() => _reservationError = 'Could not reserve this charger. Please try again.');
    } finally {
      if (mounted) setState(() => _reserving = false);
    }
  }

  Future<void> _cancelReservation() async {
    setState(() {
      _cancelingReservation = true;
      _reservationError = null;
    });
    try {
      await widget.onCancelReservation!(_reservation!.id);
      if (!mounted) return;
      setState(() => _reservationCanceled = true);
    } catch (_) {
      if (!mounted) return;
      setState(() => _reservationError = 'Could not cancel this reservation. Please try again.');
    } finally {
      if (mounted) setState(() => _cancelingReservation = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.chargerId, style: Theme.of(context).textTheme.titleMedium),
          if (widget.onStartCharging != null) ...[
            const SizedBox(height: 16),
            if (_stopped)
              const Text('Charging stopped.', key: Key('stop-charging-success'))
            else if (_startedSessionId != null) ...[
              Text(
                'Charging started (session ${_startedSessionId!}).',
                key: const Key('start-charging-success'),
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    _error!,
                    key: const Key('stop-charging-error'),
                    style: const TextStyle(color: Colors.red),
                  ),
                ),
              if (widget.onFetchLiveSession != null) ...[
                const SizedBox(height: 12),
                OutlinedButton(
                  key: const Key('view-live-session-button'),
                  onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                    builder: (_) => LiveSessionScreen(
                      sessionFetcher: () => widget.onFetchLiveSession!(_startedSessionId!),
                      sessionStopper: () => widget.onStopCharging!(_startedSessionId!),
                    ),
                  )),
                  child: const Text('View live session'),
                ),
              ],
              if (widget.onStopCharging != null) ...[
                const SizedBox(height: 12),
                ElevatedButton(
                  key: const Key('stop-charging-button'),
                  onPressed: _stopping ? null : _stop,
                  child: _stopping
                      ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Stop Charging'),
                ),
              ],
            ] else ...[
              Row(
                children: [
                  const Text('Connector'),
                  const SizedBox(width: 12),
                  DropdownButton<int>(
                    key: const Key('connector-id-dropdown'),
                    value: _connectorId,
                    items: const [1, 2, 3]
                        .map((connector) => DropdownMenuItem(value: connector, child: Text('$connector')))
                        .toList(),
                    onChanged: (value) => setState(() => _connectorId = value ?? 1),
                  ),
                ],
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    _error!,
                    key: const Key('start-charging-error'),
                    style: const TextStyle(color: Colors.red),
                  ),
                ),
              const SizedBox(height: 12),
              ElevatedButton(
                key: const Key('start-charging-button'),
                onPressed: _starting ? null : _start,
                child: _starting
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Start Charging'),
              ),
            ],
          ],
          if (widget.onReserve != null) ...[
            const SizedBox(height: 20),
            const Divider(),
            const SizedBox(height: 8),
            if (_reservationCanceled)
              const Text('Reservation canceled.', key: Key('cancel-reservation-success'))
            else if (_reservation != null) ...[
              Text(
                'Reserved until ${_reservation!.expiresAt.toLocal()}.',
                key: const Key('reserve-success'),
              ),
              if (_reservationError != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    _reservationError!,
                    key: const Key('cancel-reservation-error'),
                    style: const TextStyle(color: Colors.red),
                  ),
                ),
              if (widget.onCancelReservation != null) ...[
                const SizedBox(height: 12),
                ElevatedButton(
                  key: const Key('cancel-reservation-button'),
                  onPressed: _cancelingReservation ? null : _cancelReservation,
                  child: _cancelingReservation
                      ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Cancel reservation'),
                ),
              ],
            ] else ...[
              Row(
                children: [
                  const Text('Reserve for'),
                  const SizedBox(width: 12),
                  DropdownButton<int>(
                    key: const Key('reservation-duration-dropdown'),
                    value: _reservationDurationMinutes,
                    items: _reservationDurationLabels.entries
                        .map((entry) => DropdownMenuItem(value: entry.key, child: Text(entry.value)))
                        .toList(),
                    onChanged: (value) => setState(() => _reservationDurationMinutes = value ?? 60),
                  ),
                ],
              ),
              if (_reservationError != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    _reservationError!,
                    key: const Key('reserve-error'),
                    style: const TextStyle(color: Colors.red),
                  ),
                ),
              const SizedBox(height: 12),
              ElevatedButton(
                key: const Key('reserve-button'),
                onPressed: _reserving ? null : _reserve,
                child: _reserving
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Reserve'),
              ),
            ],
          ],
        ],
      ),
    );
  }
}
