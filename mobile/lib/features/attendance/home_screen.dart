import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../auth/auth_controller.dart';
import '../auth/change_password_screen.dart';
import '../reports/reports_screen.dart';
import 'attendance_providers.dart';
import 'check_in_button.dart';
import 'check_in_service.dart';
import 'history_screen.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  Future<void> _refresh(WidgetRef ref) async {
    ref.invalidate(profileProvider);
    ref.invalidate(todayProvider);
    ref.invalidate(phoneProvider);
    await Future.wait([ref.read(profileProvider.future), ref.read(todayProvider.future)]);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(profileProvider);
    final today = ref.watch(todayProvider);
    final auth = ref.watch(authControllerProvider);
    final canReport = auth is AuthLoggedIn && auth.user.canDownloadReports;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Attendance'),
        actions: [
          if (canReport)
            IconButton(
              tooltip: 'Reports',
              icon: const Icon(Icons.assessment),
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ReportsScreen())),
            ),
          IconButton(
            tooltip: 'History',
            icon: const Icon(Icons.calendar_month),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const HistoryScreen())),
          ),
          PopupMenuButton<String>(
            onSelected: (value) {
              if (value == 'password') {
                Navigator.of(context)
                    .push(MaterialPageRoute(builder: (_) => const ChangePasswordScreen()));
              } else if (value == 'logout') {
                ref.read(authControllerProvider.notifier).logout();
              }
            },
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'password', child: Text('Change password')),
              PopupMenuItem(value: 'logout', child: Text('Log out')),
            ],
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _refresh(ref),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _AsyncSection(value: profile, builder: (p) => _ProfileCard(p)),
            const SizedBox(height: 12),
            const _ClockCard(),
            const SizedBox(height: 12),
            _AsyncSection(value: today, builder: (t) => _TodaySection(t)),
          ],
        ),
      ),
    );
  }
}

/// Shows a spinner, the data, or a friendly error with a retry button.
class _AsyncSection<T> extends ConsumerWidget {
  const _AsyncSection({required this.value, required this.builder});
  final AsyncValue<T> value;
  final Widget Function(T) builder;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return value.when(
      data: builder,
      loading: () => const Card(
          child: Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()))),
      error: (e, _) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(children: [
            Text(e is ApiException ? e.message : 'Something went wrong.', textAlign: TextAlign.center),
            TextButton(
              onPressed: () {
                ref.invalidate(profileProvider);
                ref.invalidate(todayProvider);
              },
              child: const Text('Try again'),
            ),
          ]),
        ),
      ),
    );
  }
}

class _ProfileCard extends StatelessWidget {
  const _ProfileCard(this.p);
  final Profile p;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final location = p.primaryLocation;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(p.fullName, style: text.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Text([p.employeeCode, if (p.department != null) p.department].join('  ·  '), style: text.bodyMedium),
          const Divider(height: 24),
          _Info(Icons.supervisor_account_outlined, 'Manager', p.manager ?? '—'),
          _Info(Icons.location_on_outlined, 'Location',
              location == null ? 'None assigned - contact HR' : location.name),
          if (p.locations.length > 1)
            Padding(
              padding: const EdgeInsets.only(left: 32),
              child: Text('Also: ${p.locations.where((l) => l != location).map((l) => l.name).join(', ')}',
                  style: text.bodySmall),
            ),
        ]),
      ),
    );
  }
}

class _Info extends StatelessWidget {
  const _Info(this.icon, this.label, this.value);
  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(children: [
          Icon(icon, size: 20, color: AppColors.neutral),
          const SizedBox(width: 12),
          Text('$label: ', style: const TextStyle(color: AppColors.neutral)),
          Expanded(child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600))),
        ]),
      );
}

/// Current date and time, ticking. (Attendance time itself always comes from the server.)
class _ClockCard extends StatefulWidget {
  const _ClockCard();

  @override
  State<_ClockCard> createState() => _ClockCardState();
}

class _ClockCardState extends State<_ClockCard> {
  late Timer _timer;
  DateTime _now = DateTime.now();

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => setState(() => _now = DateTime.now()));
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 16),
        child: Row(children: [
          // Long dates ("Wednesday, 30 September 2026") wrap instead of overflowing on narrow phones.
          Expanded(child: Text(DateFormat('EEEE, d MMMM yyyy').format(_now), style: text.titleMedium)),
          const SizedBox(width: 12),
          Text(DateFormat('HH:mm:ss').format(_now),
              style: text.titleLarge?.copyWith(fontFeatures: const [FontFeature.tabularFigures()])),
        ]),
      ),
    );
  }
}

class _TodaySection extends StatelessWidget {
  const _TodaySection(this.t);
  final Today t;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final day = t.attendance;
    final status = statusForToday(
      state: t.state,
      dayType: t.dayType,
      dayStatus: day?.dayStatus,
      verificationStatus: day?.verificationStatus,
    );
    final lastRejected = t.attempts.isNotEmpty && t.attempts.first.result == 'REJECTED';

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text("Today's status", style: text.labelLarge),
            const SizedBox(height: 10),
            StatusChip(status, large: true),
            const SizedBox(height: 12),
            Text(_dayLine(t), style: text.bodyMedium),
            if (day != null) ...[
              const SizedBox(height: 8),
              Text('First check-in ${formatTime(day.firstCheckInAt)}   ·   '
                  'Worked ${formatMinutes(day.workedMinutes)}'),
            ],
          ]),
        ),
      ),
      const SizedBox(height: 12),
      const Card(
        child: ListTile(
          leading: Icon(Icons.my_location),
          title: Text('Location status'),
          subtitle: Text('Your location is checked by the server only at the moment you check in or out.'),
        ),
      ),
      const SizedBox(height: 16),
      CheckInPanel(nextAction: t.nextAction, qrRequired: t.qrRequired),
      if (lastRejected)
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Card(
            color: AppColors.rejected.withValues(alpha: 0.08),
            child: ListTile(
              leading: const Icon(Icons.error_outline, color: AppColors.rejected),
              title: const Text('Last attempt was not accepted'),
              subtitle: Text(t.attempts.first.message),
            ),
          ),
        ),
      if (t.attempts.isNotEmpty) ...[
        const SizedBox(height: 16),
        Text("Today's attempts", style: text.titleSmall),
        for (final a in t.attempts)
          ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            leading: Icon(statusForAttempt(a.result).icon, color: statusForAttempt(a.result).color),
            title: Text('${a.eventType == 'CHECK_IN' ? 'Check-in' : 'Check-out'}  ${formatTime(a.time)}'),
            subtitle: Text(a.message),
          ),
      ],
    ]);
  }

  static String _dayLine(Today t) => switch (t.dayType) {
        'HOLIDAY' => 'Holiday${t.dayDescription != null ? ': ${t.dayDescription}' : ''}',
        'ON_LEAVE' => 'You are on leave today',
        'NON_WORKING_DAY' => 'Not a working day',
        _ => t.scheduledStart == null
            ? 'Working day'
            : 'Working hours ${shortTime(t.scheduledStart)} – ${shortTime(t.scheduledEnd)}',
      };
}
