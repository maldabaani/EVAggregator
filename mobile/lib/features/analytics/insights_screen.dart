import 'package:flutter/material.dart';

import '../session/session_tracking.dart' show formatCost;
import 'usage_insights.dart';

/// Task 5.4 — driver analytics & insights dashboard. Fetches the driver's
/// own daily usage (grouped server-side from their completed-session
/// history) for the trailing [periodDays] and the equal-length period
/// immediately before it, so the dashboard can show a spend trend rather
/// than just a flat total.
typedef UsageFetcher = Future<List<DailyUsagePoint>> Function(DateTime from, DateTime to);

class InsightsScreen extends StatefulWidget {
  final UsageFetcher fetcher;
  final int periodDays;
  final DateTime Function()? now;

  const InsightsScreen({
    super.key,
    required this.fetcher,
    this.periodDays = 7,
    this.now,
  });

  @override
  State<InsightsScreen> createState() => _InsightsScreenState();
}

class _InsightsScreenState extends State<InsightsScreen> {
  bool _loading = true;
  String? _error;
  List<DailyUsagePoint> _currentPoints = [];
  UsageSummary _currentSummary = UsageSummary.zero;
  UsageSummary _previousSummary = UsageSummary.zero;

  @override
  void initState() {
    super.initState();
    _load();
  }

  ({DateTime currentFrom, DateTime currentTo, DateTime previousFrom, DateTime previousTo}) _periodBounds() {
    final now = (widget.now ?? DateTime.now)();
    final today = DateTime(now.year, now.month, now.day);
    final currentFrom = today.subtract(Duration(days: widget.periodDays - 1));
    final previousTo = currentFrom.subtract(const Duration(days: 1));
    final previousFrom = previousTo.subtract(Duration(days: widget.periodDays - 1));
    return (currentFrom: currentFrom, currentTo: today, previousFrom: previousFrom, previousTo: previousTo);
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final bounds = _periodBounds();
    try {
      final results = await Future.wait([
        widget.fetcher(bounds.currentFrom, bounds.currentTo),
        widget.fetcher(bounds.previousFrom, bounds.previousTo),
      ]);
      if (!mounted) return;
      setState(() {
        _currentPoints = results[0];
        _currentSummary = summarize(results[0]);
        _previousSummary = summarize(results[1]);
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load your usage data. Please try again.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Your charging insights')),
      body: _loading
          ? const Center(child: CircularProgressIndicator(key: Key('insights-loading')))
          : _error != null
              ? _ErrorState(message: _error!, onRetry: _load)
              : _buildContent(context),
    );
  }

  Widget _buildContent(BuildContext context) {
    final change = percentSpendChange(_currentSummary, _previousSummary);
    final busiest = busiestDay(_currentPoints);
    final favorite = favoriteSite(_currentPoints);
    final maxKwh = _currentPoints.fold<double>(0, (m, p) => p.kwhTotal > m ? p.kwhTotal : m);

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              Expanded(
                child: _SummaryCard(
                  label: 'Sessions',
                  value: '${_currentSummary.totalSessions}',
                  valueKey: 'total-sessions-value',
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _SummaryCard(
                  label: 'Energy',
                  value: '${_currentSummary.totalKwh.toStringAsFixed(1)} kWh',
                  valueKey: 'total-kwh-value',
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _SummaryCard(
            label: 'Total spend',
            value: formatCost(_currentSummary.totalCostMinorUnits, 'AED'),
            valueKey: 'total-spend-value',
            trailing: change == null
                ? null
                : Text(
                    key: const Key('spend-change-value'),
                    '${change >= 0 ? '+' : ''}${(change * 100).toStringAsFixed(0)}% vs previous period',
                    style: TextStyle(color: change > 0 ? Colors.red : Colors.green),
                  ),
          ),
          const SizedBox(height: 24),
          if (busiest != null)
            ListTile(
              key: const Key('busiest-day-tile'),
              leading: const Icon(Icons.calendar_today),
              title: const Text('Busiest day'),
              subtitle: Text(
                key: const Key('busiest-day-value'),
                '${busiest.date.year}-${busiest.date.month.toString().padLeft(2, '0')}-${busiest.date.day.toString().padLeft(2, '0')} '
                '(${busiest.sessionCount} session${busiest.sessionCount == 1 ? '' : 's'})',
              ),
            ),
          if (favorite != null)
            ListTile(
              key: const Key('favorite-site-tile'),
              leading: const Icon(Icons.ev_station),
              title: const Text('Favorite charging site'),
              subtitle: Text(favorite, key: const Key('favorite-site-value')),
            ),
          const SizedBox(height: 16),
          if (_currentPoints.isEmpty)
            const Center(child: Text('No charging sessions in this period yet.'))
          else
            Column(
              key: const Key('usage-bar-chart'),
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: _currentPoints
                  .map((point) => _UsageBar(point: point, maxKwh: maxKwh == 0 ? 1 : maxKwh))
                  .toList(),
            ),
        ],
      ),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final String label;
  final String value;
  final String valueKey;
  final Widget? trailing;

  const _SummaryCard({required this.label, required this.value, required this.valueKey, this.trailing});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: Theme.of(context).textTheme.labelMedium),
            Text(value, key: Key(valueKey), style: Theme.of(context).textTheme.headlineSmall),
            ?trailing,
          ],
        ),
      ),
    );
  }
}

class _UsageBar extends StatelessWidget {
  final DailyUsagePoint point;
  final double maxKwh;

  const _UsageBar({required this.point, required this.maxKwh});

  @override
  Widget build(BuildContext context) {
    final fraction = (point.kwhTotal / maxKwh).clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(
            width: 48,
            child: Text('${point.date.month}/${point.date.day}', style: Theme.of(context).textTheme.bodySmall),
          ),
          Expanded(
            child: FractionallySizedBox(
              alignment: Alignment.centerLeft,
              widthFactor: fraction == 0 ? 0.01 : fraction,
              child: Container(height: 12, color: Theme.of(context).colorScheme.primary),
            ),
          ),
          const SizedBox(width: 8),
          Text('${point.kwhTotal.toStringAsFixed(1)} kWh', style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _ErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(message, key: const Key('insights-error-message')),
          const SizedBox(height: 12),
          ElevatedButton(key: const Key('insights-retry-button'), onPressed: onRetry, child: const Text('Retry')),
        ],
      ),
    );
  }
}
