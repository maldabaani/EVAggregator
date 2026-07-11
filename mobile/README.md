# EV Aggregator — Driver App (Flutter)

Flutter driver app: map discovery, charging session auth/tracking, insights.
See `../docs/00_Engineering_Standards.md` for shared conventions.

## Quickstart

```bash
flutter pub get
flutter analyze
flutter test
flutter run   # needs a connected device/emulator or a desktop/web target
```

## Status

Map discovery (Task 5.1) has its filter/search/clustering/live-status logic
implemented and unit-tested; the actual map rendering (pins on a real map)
needs a map SDK + API credentials that haven't been chosen yet (Google Maps /
Mapbox / flutter_map) — `lib/features/map/map_screen.dart` documents this as
a placeholder pending that decision.
