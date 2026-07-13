import 'package:flutter/material.dart';

import 'app_shell.dart';
import 'core/api/api_client.dart';
import 'core/api/driver_api.dart';
import 'core/auth/auth_session.dart';
import 'features/account/account_screen.dart';
import 'features/auth/login_screen.dart';
import 'features/auth/signup_screen.dart';
import 'features/map/map_screen.dart';
import 'features/vehicles/vehicle_list_screen.dart';
import 'features/wallet/wallet_screen.dart';

/// Root widget, separated from `main()` so widget tests can construct it
/// with a fake [ApiClient]/[AuthSession] instead of the real HTTP/
/// shared_preferences-backed ones `main()` wires up.
class EvAggregatorApp extends StatefulWidget {
  final ApiClient apiClient;
  final AuthSession authSession;

  const EvAggregatorApp({super.key, required this.apiClient, required this.authSession});

  @override
  State<EvAggregatorApp> createState() => _EvAggregatorAppState();
}

class _EvAggregatorAppState extends State<EvAggregatorApp> {
  bool _showSignup = false;

  @override
  void initState() {
    super.initState();
    widget.authSession.restoreSession();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'EV Aggregator',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal), useMaterial3: true),
      home: AnimatedBuilder(
        animation: widget.authSession,
        builder: (context, _) {
          if (widget.authSession.isRestoring) {
            return const Scaffold(
              body: Center(child: CircularProgressIndicator(key: Key('app-restoring'))),
            );
          }
          if (!widget.authSession.isAuthenticated) {
            return _showSignup
                ? SignupScreen(
                    authSession: widget.authSession,
                    onSwitchToLogin: () => setState(() => _showSignup = false),
                  )
                : LoginScreen(
                    authSession: widget.authSession,
                    onSwitchToSignup: () => setState(() => _showSignup = true),
                  );
          }
          final driverApi = DriverApi(widget.apiClient);
          return AppShell(
            mapScreen: MapScreen(
              searchExecutor: driverApi.searchStations,
              pinsFetcher: driverApi.fetchChargers,
              onStartCharging: driverApi.startCharging,
              onStopCharging: driverApi.stopCharging,
              onReserve: driverApi.reserveCharger,
              onCancelReservation: driverApi.cancelReservation,
            ),
            vehiclesScreen: VehicleListScreen(
              fetcher: driverApi.fetchVehicles,
              creator: driverApi.createVehicle,
              toggler: driverApi.setPlugAndCharge,
              deleter: driverApi.deleteVehicle,
            ),
            walletScreen: WalletScreen(
              fetchBalance: driverApi.getWalletBalance,
              topUp: driverApi.topUpWallet,
              fetchPaymentMethod: driverApi.getPaymentMethod,
              setPaymentMethod: driverApi.setPaymentMethod,
            ),
            accountScreen: AccountScreen(
              authSession: widget.authSession,
              fetchReservations: driverApi.fetchReservations,
              cancelReservation: driverApi.cancelReservation,
            ),
          );
        },
      ),
    );
  }
}
