/// Task 5.1 — filter state for the live map, persisted in local app state
/// (not the URL — this is a mobile app) and re-applied on map re-entry
/// within the session.
class ChargerFilter {
  final double? minKw;
  final double? maxPrice;
  final String? connectorType;
  final bool availableOnly;

  const ChargerFilter({
    this.minKw,
    this.maxPrice,
    this.connectorType,
    this.availableOnly = false,
  });

  ChargerFilter copyWith({
    double? minKw,
    double? maxPrice,
    String? connectorType,
    bool? availableOnly,
  }) {
    return ChargerFilter(
      minKw: minKw ?? this.minKw,
      maxPrice: maxPrice ?? this.maxPrice,
      connectorType: connectorType ?? this.connectorType,
      availableOnly: availableOnly ?? this.availableOnly,
    );
  }

  @override
  bool operator ==(Object other) =>
      other is ChargerFilter &&
      other.minKw == minKw &&
      other.maxPrice == maxPrice &&
      other.connectorType == connectorType &&
      other.availableOnly == availableOnly;

  @override
  int get hashCode => Object.hash(minKw, maxPrice, connectorType, availableOnly);
}

class LatLngBounds {
  final double minLat;
  final double minLng;
  final double maxLat;
  final double maxLng;

  const LatLngBounds({
    required this.minLat,
    required this.minLng,
    required this.maxLat,
    required this.maxLng,
  });
}
