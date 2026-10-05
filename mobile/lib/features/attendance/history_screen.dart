import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import 'attendance_providers.dart';

class HistoryScreen extends ConsumerStatefulWidget {
  const HistoryScreen({super.key});

  @override
  ConsumerState<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends ConsumerState<HistoryScreen> {
  DateTime _month = DateTime(DateTime.now().year, DateTime.now().month);

  void _shift(int months) => setState(() => _month = DateTime(_month.year, _month.month + months));

  @override
  Widget build(BuildContext context) {
    final days = ref.watch(historyProvider(_month));
    final isCurrentMonth = _month.year == DateTime.now().year && _month.month == DateTime.now().month;

    return Scaffold(
      appBar: AppBar(title: const Text('My attendance')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          child: Row(children: [
            IconButton(onPressed: () => _shift(-1), icon: const Icon(Icons.chevron_left), tooltip: 'Previous month'),
            Expanded(
              child: Text(DateFormat('MMMM yyyy').format(_month),
                  textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleMedium),
            ),
            IconButton(
              onPressed: isCurrentMonth ? null : () => _shift(1),
              icon: const Icon(Icons.chevron_right),
              tooltip: 'Next month',
            ),
          ]),
        ),
        Expanded(
          child: days.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text(e is ApiException ? e.message : 'Something went wrong.')),
            data: (list) => list.isEmpty
                ? const Center(child: Text('No attendance recorded this month.'))
                : ListView(children: [_Summary(list), for (final d in list) _DayTile(d)]),
          ),
        ),
      ]),
    );
  }
}

class _Summary extends StatelessWidget {
  const _Summary(this.days);
  final List<AttendanceDay> days;

  @override
  Widget build(BuildContext context) {
    final present = days.where((d) => d.dayStatus == 'PRESENT').length;
    final late = days.where((d) => d.dayStatus == 'LATE').length;
    final minutes = days.fold<int>(0, (sum, d) => sum + d.workedMinutes);
    return Card(
      margin: const EdgeInsets.all(12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [
          _Stat('Present', '$present'),
          _Stat('Late', '$late'),
          _Stat('Worked', formatMinutes(minutes)),
        ]),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Column(children: [
        Text(value, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
        Text(label),
      ]);
}

class _DayTile extends StatelessWidget {
  const _DayTile(this.d);
  final AttendanceDay d;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text(DateFormat('EEE d MMM').format(d.date)),
      subtitle: Text('${formatTime(d.firstCheckInAt)} – ${formatTime(d.lastCheckOutAt)}'
          '   ·   ${formatMinutes(d.workedMinutes)}'
          '${d.location != null ? '   ·   ${d.location}' : ''}'),
      trailing: StatusChip(statusForDay(d.dayStatus, d.verificationStatus)),
    );
  }
}
