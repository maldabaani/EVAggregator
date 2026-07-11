import 'package:evagg_driver/core/models/charger_filter.dart';
import 'package:evagg_driver/features/map/map_query.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const bbox = LatLngBounds(minLat: 24.0, minLng: 54.0, maxLat: 26.0, maxLng: 56.0);

  test('test_filter_params_correctly_applied_to_map_query', () {
    const filter = ChargerFilter(
      minKw: 50,
      maxPrice: 2.5,
      connectorType: 'CCS2',
      availableOnly: true,
    );

    final params = buildMapQueryParams(bbox, filter);

    expect(params['bbox'], '24.0,54.0,26.0,56.0');
    expect(params['min_kw'], '50.0');
    expect(params['max_price'], '2.5');
    expect(params['connector_type'], 'CCS2');
    expect(params['available_only'], 'true');
  });

  test('omits unset filter params rather than sending empty values', () {
    const filter = ChargerFilter();

    final params = buildMapQueryParams(bbox, filter);

    expect(params.containsKey('min_kw'), isFalse);
    expect(params.containsKey('max_price'), isFalse);
    expect(params.containsKey('connector_type'), isFalse);
    expect(params.containsKey('available_only'), isFalse);
  });

  test('availableOnly false is omitted, not sent as "false"', () {
    const filter = ChargerFilter(availableOnly: false);

    final params = buildMapQueryParams(bbox, filter);

    expect(params.containsKey('available_only'), isFalse);
  });
}
