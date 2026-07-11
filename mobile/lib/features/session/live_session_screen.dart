import 'package:flutter/material.dart';

import 'session_tracking.dart';

/// Task 5.3 — live session tracking screen. Polls session state (energy,
/// power, cost, status) on a fixed interval and lets the driver stop the
/// session, surfacing a "connection lost" banner rather than freezing
/// silently if the feed goes stale (same failure mode the map's live
/// status feed guards against in Task 5.1).
class LiveSessionScreen extends StatefulWidget {
  final SessionFetcher sessionFetcher;
  final SessionStopper sessionStopper;
  final Duration pollInterval;
  final Duration staleAfter;

  const LiveSessionScreen({
    super.key,
    required this.sessionFetcher,
    required this.sessionStopper,
    this.pollInterval = defaultPollInterval,
    this.staleAfter = defaultSessionStaleAfter,
  });

  @override
  State<LiveSessionScreen> createState() => _LiveSessionScreenState();
}

class _LiveSessionScreenState extends State<LiveSessionScreen> {
  late final SessionTrackingController _controller;
  SessionSnapshot? _snapshot;
  bool _stopping = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _controller = SessionTrackingController(
      fetcher: widget.sessionFetcher,
      stopper: widget.sessionStopper,
      pollInterval: widget.pollInterval,
      staleAfter: widget.staleAfter,
      onUpdate: (snapshot) {
        if (mounted) setState(() => _snapshot = snapshot);
      },
      // A failed poll doesn't change `_snapshot`, but staleness (computed
      // fresh from the controller on every build) needs a rebuild to be
      // reflected in the stale banner — otherwise it would only update on
      // the next successful poll, defeating the point of the banner.
      onFetchError: (_) {
        if (mounted) setState(() {});
      },
    );
    _controller.start();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _confirmAndStop() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Stop charging?'),
        content: const Text('This will end your current charging session.'),
        actions: [
          TextButton(
            key: const Key('stop-session-cancel'),
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            key: const Key('stop-session-confirm'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Stop charging'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() {
      _stopping = true;
      _errorMessage = null;
    });
    try {
      await _controller.stop();
      if (!mounted) return;
      setState(() {
        _stopping = false;
        _snapshot = _snapshot == null
            ? null
            : SessionSnapshot(
                status: SessionStatus.finished,
                energyKwh: _snapshot!.energyKwh,
                powerKw: 0,
                costMinorUnits: _snapshot!.costMinorUnits,
                currency: _snapshot!.currency,
                startedAt: _snapshot!.startedAt,
                updatedAt: _snapshot!.updatedAt,
              );
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _stopping = false;
        _errorMessage = 'Could not stop the session. Please try again.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final snapshot = _snapshot;
    return Scaffold(
      appBar: AppBar(title: const Text('Charging session')),
      body: snapshot == null
          ? const Center(child: CircularProgressIndicator(key: Key('session-loading')))
          : Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_controller.isStale)
                    Container(
                      key: const Key('stale-banner'),
                      padding: const EdgeInsets.all(8),
                      color: Colors.amber.shade100,
                      child: const Text('Connection lost — showing last known values'),
                    ),
                  if (_errorMessage != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(_errorMessage!, style: const TextStyle(color: Colors.red)),
                    ),
                  const SizedBox(height: 16),
                  Text(
                    formatElapsed(DateTime.now().difference(snapshot.startedAt)),
                    key: const Key('elapsed-time'),
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                  const SizedBox(height: 24),
                  _MetricRow(label: 'Energy delivered', value: '${snapshot.energyKwh.toStringAsFixed(2)} kWh', metricKey: 'energy-value'),
                  _MetricRow(label: 'Power', value: '${snapshot.powerKw.toStringAsFixed(1)} kW', metricKey: 'power-value'),
                  _MetricRow(
                    label: 'Cost so far',
                    value: formatCost(snapshot.costMinorUnits, snapshot.currency),
                    metricKey: 'cost-value',
                  ),
                  _MetricRow(label: 'Status', value: snapshot.status.name, metricKey: 'status-value'),
                  const Spacer(),
                  if (snapshot.status != SessionStatus.finished)
                    ElevatedButton(
                      key: const Key('stop-session-button'),
                      onPressed: _stopping ? null : _confirmAndStop,
                      child: _stopping
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Stop charging'),
                    )
                  else
                    const Text('Session ended', key: Key('session-ended-label'), textAlign: TextAlign.center),
                ],
              ),
            ),
    );
  }
}

class _MetricRow extends StatelessWidget {
  final String label;
  final String value;
  final String metricKey;

  const _MetricRow({required this.label, required this.value, required this.metricKey});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(value, key: Key(metricKey), style: const TextStyle(fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}
