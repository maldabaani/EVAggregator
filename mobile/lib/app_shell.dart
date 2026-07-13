import 'package:flutter/material.dart';

import 'core/navigation/tab_switcher.dart';

/// The authenticated app's bottom-nav shell. Session tracking isn't a tab
/// here yet — it needs an active-session lookup keyed by driver that this
/// phase doesn't have — wiring it to nothing would just be a fake tab, so
/// it waits for that backend work rather than shipping now.
class AppShell extends StatefulWidget {
  final Widget homeScreen;
  final Widget mapScreen;
  final Widget vehiclesScreen;
  final Widget walletScreen;
  final Widget routePlannerScreen;
  final Widget accountScreen;
  final TabSwitcher? tabSwitcher;

  const AppShell({
    super.key,
    required this.homeScreen,
    required this.mapScreen,
    required this.vehiclesScreen,
    required this.walletScreen,
    required this.routePlannerScreen,
    required this.accountScreen,
    this.tabSwitcher,
  });

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;

  @override
  void initState() {
    super.initState();
    widget.tabSwitcher?.attach((index) => setState(() => _index = index));
  }

  @override
  Widget build(BuildContext context) {
    final tabs = [
      widget.homeScreen,
      widget.mapScreen,
      widget.vehiclesScreen,
      widget.walletScreen,
      widget.routePlannerScreen,
      widget.accountScreen,
    ];
    return Scaffold(
      body: IndexedStack(index: _index, children: tabs),
      bottomNavigationBar: NavigationBar(
        key: const Key('app-bottom-nav'),
        selectedIndex: _index,
        onDestinationSelected: (index) => setState(() => _index = index),
        destinations: const [
          NavigationDestination(key: Key('nav-home'), icon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(key: Key('nav-map'), icon: Icon(Icons.map), label: 'Map'),
          NavigationDestination(key: Key('nav-vehicles'), icon: Icon(Icons.directions_car), label: 'My Cars'),
          NavigationDestination(key: Key('nav-wallet'), icon: Icon(Icons.account_balance_wallet), label: 'Wallet'),
          NavigationDestination(key: Key('nav-route'), icon: Icon(Icons.alt_route), label: 'Route'),
          NavigationDestination(key: Key('nav-account'), icon: Icon(Icons.person), label: 'Account'),
        ],
      ),
    );
  }
}
