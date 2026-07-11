import 'package:evagg_driver/features/map/pin_clustering.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final pins = List.generate(
    20,
    (i) => MapPin(id: 'CP-$i', lat: 25.0 + (i * 0.001), lng: 55.0 + (i * 0.001)),
  );

  test('test_cluster_recompute_on_zoom_change', () {
    final zoomedOut = clusterPins(pins, 4);
    final zoomedIn = clusterPins(pins, 15);

    // Zoomed out: pins that are close together collapse into fewer groups.
    expect(zoomedOut.length, lessThan(pins.length));
    // Zoomed in past the threshold: no clustering at all, one group per pin.
    expect(zoomedIn.length, pins.length);
    for (final group in zoomedIn) {
      expect(group.count, 1);
    }
  });

  test('clusters recompute to fewer groups as zoom decreases further', () {
    final atZoom6 = clusterPins(pins, 6);
    final atZoom2 = clusterPins(pins, 2);

    // Coarser grid at lower zoom -> groups pins together at least as much.
    expect(atZoom2.length, lessThanOrEqualTo(atZoom6.length));
  });

  test('a cluster group is positioned at the average of its member pins', () {
    final closePins = [
      const MapPin(id: 'a', lat: 10.0, lng: 20.0),
      const MapPin(id: 'b', lat: 10.0, lng: 20.0),
    ];

    final groups = clusterPins(closePins, 0);

    expect(groups.length, 1);
    expect(groups.first.lat, 10.0);
    expect(groups.first.lng, 20.0);
    expect(groups.first.count, 2);
  });

  test('empty pin list produces no clusters', () {
    expect(clusterPins(const [], 5), isEmpty);
  });
}
