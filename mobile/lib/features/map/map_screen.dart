import 'package:flutter/material.dart';
// Both flutter_map and core/models/charger_filter.dart declare a
// `LatLngBounds` class — ours is the app's bbox-query type, flutter_map's is
// its own internal viewport-bounds type, which this screen never needs.
import 'package:flutter_map/flutter_map.dart' hide LatLngBounds;
import 'package:latlong2/latlong.dart' as ll;

import '../../core/models/charger_filter.dart';
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

const ll.LatLng defaultMapCenter = ll.LatLng(25.2048, 55.2708); // Dubai
const LatLngBounds defaultMapBounds = LatLngBounds(minLat: 25.05, minLng: 55.10, maxLat: 25.35, maxLng: 55.45);
const double defaultInitialZoom = 13;

class MapScreen extends StatefulWidget {
  final SearchExecutor searchExecutor;
  final PinsFetcher pinsFetcher;
  final LiveStatusFeedController? statusFeed;
  final TileProvider? tileProvider;

  const MapScreen({
    super.key,
    required this.searchExecutor,
    required this.pinsFetcher,
    this.statusFeed,
    this.tileProvider,
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
        child: ListTile(
          key: const Key('charger-detail-sheet'),
          title: Text(cluster.pins.first.id),
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
