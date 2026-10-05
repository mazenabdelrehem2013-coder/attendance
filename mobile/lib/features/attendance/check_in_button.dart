import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/location_service.dart';
import '../../core/theme.dart';
import 'attendance_providers.dart';
import 'check_in_service.dart';
import 'qr_scan_screen.dart';

/// The big CHECK IN / CHECK OUT button, plus the phone-approval notice.
class CheckInPanel extends ConsumerWidget {
  const CheckInPanel({super.key, required this.nextAction, required this.qrRequired});

  final String nextAction; // CHECK_IN / CHECK_OUT
  final bool qrRequired;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final phone = ref.watch(phoneProvider);
    final checkIn = nextAction == 'CHECK_IN';
    final button = FilledButton.icon(
      key: Key(checkIn ? 'checkIn' : 'checkOut'),
      style: FilledButton.styleFrom(backgroundColor: checkIn ? AppColors.checkedIn : AppColors.rejected),
      onPressed: phone.value?.approved == true
          ? () => _start(context, ref, phone.requireValue.id)
          : null,
      icon: Icon(checkIn ? Icons.login : Icons.logout),
      label: Text(checkIn ? 'CHECK IN' : 'CHECK OUT'),
    );

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      phone.when(
        loading: () => const SizedBox.shrink(),
        error: (e, _) => _Notice(
          icon: Icons.phonelink_erase,
          color: AppColors.rejected,
          text: e is ApiException ? e.message : "This phone couldn't be registered.",
          action: TextButton(onPressed: () => ref.invalidate(phoneProvider), child: const Text('Try again')),
        ),
        data: (p) => switch (p.status) {
          'ACTIVE' => const SizedBox.shrink(),
          'PENDING_APPROVAL' => _Notice(
              icon: Icons.hourglass_top,
              color: AppColors.late,
              text: 'This phone is waiting for HR approval. You can check in once HR has approved it.',
              action: TextButton(onPressed: () => ref.invalidate(phoneProvider), child: const Text('Check again')),
            ),
          _ => const _Notice(
              icon: Icons.block,
              color: AppColors.rejected,
              text: "This phone can't be used for attendance. Please contact HR.",
            ),
        },
      ),
      button,
      if (qrRequired)
        const Padding(
          padding: EdgeInsets.only(top: 6),
          child: Text('You will scan the QR code on the office screen.', textAlign: TextAlign.center),
        ),
    ]);
  }

  Future<void> _start(BuildContext context, WidgetRef ref, String deviceId) async {
    String? qr;
    if (qrRequired) {
      qr = await Navigator.of(context).push<String>(MaterialPageRoute(builder: (_) => const QrScanScreen()));
      if (qr == null || !context.mounted) return;
    }
    final stage = ValueNotifier(CheckInStage.preparing);
    final navigator = Navigator.of(context);
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => PopScope(canPop: false, child: _ProgressDialog(stage)),
    );
    try {
      final outcome = await ref.read(checkInServiceProvider).run(
            action: nextAction,
            deviceId: deviceId,
            qrToken: qr,
            onStage: (s) => stage.value = s,
          );
      navigator.pop();
      if (context.mounted) await _showOutcome(context, outcome);
    } on LocationProblem catch (p) {
      navigator.pop();
      if (context.mounted) await _showLocationProblem(context, ref, p);
    } on ApiException catch (e) {
      navigator.pop();
      if (context.mounted) await _showMessage(context, 'Not completed', e.message);
    } finally {
      ref.invalidate(todayProvider);
    }
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.icon, required this.color, required this.text, this.action});
  final IconData icon;
  final Color color;
  final String text;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Card(
        color: color.withValues(alpha: 0.08),
        margin: const EdgeInsets.only(bottom: 12),
        child: ListTile(leading: Icon(icon, color: color), title: Text(text), trailing: action),
      );
}

class _ProgressDialog extends StatelessWidget {
  const _ProgressDialog(this.stage);
  final ValueNotifier<CheckInStage> stage;

  @override
  Widget build(BuildContext context) => AlertDialog(
        content: ValueListenableBuilder(
          valueListenable: stage,
          builder: (_, s, _) => Row(children: [
            const CircularProgressIndicator(),
            const SizedBox(width: 20),
            Expanded(
              child: Text(switch (s) {
                CheckInStage.preparing => 'Preparing…',
                CheckInStage.locating => 'Getting your location…',
                CheckInStage.verifying => 'Verifying…',
              }),
            ),
          ]),
        ),
      );
}

Future<void> _showOutcome(BuildContext context, CheckOutcome o) {
  final isIn = o.eventType == 'CHECK_IN';
  final (title, color, icon) = switch (o.result) {
    'ACCEPTED' => (isIn ? 'Checked in' : 'Checked out', AppColors.checkedIn, Icons.check_circle),
    'FLAGGED' => ('Recorded – pending review', AppColors.pending, Icons.hourglass_top),
    _ => ('Not accepted', AppColors.rejected, Icons.cancel),
  };
  return showModalBottomSheet<void>(
    context: context,
    builder: (ctx) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, color: color, size: 72),
          const SizedBox(height: 12),
          Text(title,
              key: const Key('outcomeTitle'),
              style: Theme.of(ctx).textTheme.headlineSmall?.copyWith(color: color, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Text(o.message, textAlign: TextAlign.center),
          const SizedBox(height: 8),
          Text([
            formatTime(o.serverTime),
            if (o.location != null) o.location!,
            if (o.distanceMeters != null) '${o.distanceMeters} m from the office point',
          ].join('  ·  ')),
          const SizedBox(height: 20),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('OK')),
        ]),
      ),
    ),
  );
}

Future<void> _showLocationProblem(BuildContext context, WidgetRef ref, LocationProblem p) => showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Location needed'),
        content: Text(p.message),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Close')),
          if (p.canOpenSettings)
            FilledButton(
              onPressed: () {
                Navigator.of(ctx).pop();
                ref.read(locationServiceProvider).openSettings(p.kind);
              },
              child: const Text('Open settings'),
            ),
        ],
      ),
    );

Future<void> _showMessage(BuildContext context, String title, String message) => showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('OK'))],
      ),
    );
