/// Task 5.1 — client-side pin clustering below a zoom threshold, so
/// thousands of pins are never rendered at low zoom. This is a performance
/// concern, not a correctness one: cluster boundaries are recomputed on
/// zoom/pan (debounced by the caller, e.g. 200ms), not on every frame.
library;

class MapPin {
  final String id;
  final double lat;
  final double lng;

  const MapPin({required this.id, required this.lat, required this.lng});
}

class ClusterGroup {
  final double lat;
  final double lng;
  final List<MapPin> pins;

  const ClusterGroup({required this.lat, required this.lng, required this.pins});

  int get count => pins.length;
}

const double clusterZoomThreshold = 12;

/// At or above [zoomThreshold], every pin renders individually (no
/// clustering). Below it, pins are grouped into a grid whose cell size
/// shrinks as zoom increases, so clusters get finer as the map zooms in.
List<ClusterGroup> clusterPins(
  List<MapPin> pins,
  double zoom, {
  double zoomThreshold = clusterZoomThreshold,
}) {
  if (zoom >= zoomThreshold) {
    return pins.map((p) => ClusterGroup(lat: p.lat, lng: p.lng, pins: [p])).toList();
  }

  final cellSize = _cellSizeForZoom(zoom);
  final buckets = <String, List<MapPin>>{};
  for (final pin in pins) {
    final cellX = (pin.lat / cellSize).floor();
    final cellY = (pin.lng / cellSize).floor();
    final key = '$cellX:$cellY';
    buckets.putIfAbsent(key, () => []).add(pin);
  }

  return buckets.values.map((group) {
    final avgLat = group.map((p) => p.lat).reduce((a, b) => a + b) / group.length;
    final avgLng = group.map((p) => p.lng).reduce((a, b) => a + b) / group.length;
    return ClusterGroup(lat: avgLat, lng: avgLng, pins: group);
  }).toList();
}

double _cellSizeForZoom(double zoom) => 10.0 / (zoom + 1);
