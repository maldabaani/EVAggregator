import 'package:flutter/material.dart';

import '../../core/models/charger_filter.dart';
import 'search_debouncer.dart';

/// Task 5.1 — live map discovery screen. The actual map rendering (pins,
/// clustering, live status colors) needs a chosen map SDK (Google Maps /
/// Mapbox / flutter_map) and API credentials neither of which are decided
/// yet — this wires the filter/search interaction layer (already unit
/// tested in isolation in map_query.dart, live_status_feed.dart,
/// pin_clustering.dart, search_debouncer.dart) around a placeholder map
/// area, so the real map widget can drop in without touching this logic.
class MapScreen extends StatefulWidget {
  final SearchExecutor searchExecutor;

  const MapScreen({super.key, required this.searchExecutor});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  late final DebouncedSearchController _searchController;
  ChargerFilter _filter = const ChargerFilter();
  List<String> _searchResults = [];

  @override
  void initState() {
    super.initState();
    _searchController = DebouncedSearchController(executor: widget.searchExecutor);
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
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
  }

  @override
  Widget build(BuildContext context) {
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
            const Expanded(
              child: Center(child: Text('Map view (provider TBD)')),
            ),
        ],
      ),
    );
  }
}
