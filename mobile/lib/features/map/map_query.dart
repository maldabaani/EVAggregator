import '../../core/models/charger_filter.dart';

/// Task 5.1 — builds the query params for `GET /map/chargers`, which builds
/// on Epic 4 Task 4.3's visibility-filtered query by adding these filter
/// params on top.
Map<String, String> buildMapQueryParams(LatLngBounds bbox, ChargerFilter filter) {
  final params = <String, String>{
    'bbox': '${bbox.minLat},${bbox.minLng},${bbox.maxLat},${bbox.maxLng}',
  };

  if (filter.minKw != null) {
    params['min_kw'] = filter.minKw!.toString();
  }
  if (filter.maxPrice != null) {
    params['max_price'] = filter.maxPrice!.toString();
  }
  if (filter.connectorType != null) {
    params['connector_type'] = filter.connectorType!;
  }
  if (filter.availableOnly) {
    params['available_only'] = 'true';
  }

  return params;
}
