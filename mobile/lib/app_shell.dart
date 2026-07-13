import 'package:flutter/material.dart';

/// The authenticated app's bottom-nav shell. Session tracking and usage
/// insights aren't tabs here yet — both need real backend data this phase
/// doesn't have (an active-session lookup keyed by driver, and a
/// driver-scoped usage rollup) — wiring them to nothing would just be a
/// fake tab, so they wait for that backend work rather than shipping now.
class AppShell extends StatefulWidget {
  final Widget mapScreen;
  final Widget vehiclesScreen;
  final Widget accountScreen;

  const AppShell({
    super.key,
    required this.mapScreen,
    required this.vehiclesScreen,
    required this.accountScreen,
  });

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final tabs = [widget.mapScreen, widget.vehiclesScreen, widget.accountScreen];
    return Scaffold(
      body: IndexedStack(index: _index, children: tabs),
      bottomNavigationBar: NavigationBar(
        key: const Key('app-bottom-nav'),
        selectedIndex: _index,
        onDestinationSelected: (index) => setState(() => _index = index),
        destinations: const [
          NavigationDestination(key: Key('nav-map'), icon: Icon(Icons.map), label: 'Map'),
          NavigationDestination(key: Key('nav-vehicles'), icon: Icon(Icons.directions_car), label: 'My Cars'),
          NavigationDestination(key: Key('nav-account'), icon: Icon(Icons.person), label: 'Account'),
        ],
      ),
    );
  }
}
