import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

class AppColors {
  static const brand = Color(0xFF1F5FAD);
  static const checkedIn = Color(0xFF1E8E3E); // green
  static const checkedOut = Color(0xFF1F5FAD); // blue
  static const late = Color(0xFFE37400); // amber
  static const pending = Color(0xFF8E44AD); // purple
  static const rejected = Color(0xFFC5221F); // red
  static const neutral = Color(0xFF5F6368); // grey
}

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: AppColors.brand);
  return ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    inputDecorationTheme: const InputDecorationTheme(border: OutlineInputBorder()),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(56),
        textStyle: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, letterSpacing: 1),
      ),
    ),
  );
}

/// One clear status for the employee, with a color and an icon.
class StatusView {
  const StatusView(this.label, this.color, this.icon);
  final String label;
  final Color color;
  final IconData icon;
}

StatusView statusForToday({
  required String state,
  required String dayType,
  String? dayStatus,
  String? verificationStatus,
}) {
  if (verificationStatus == 'PENDING_REVIEW' && state != 'CHECKED_IN') {
    return const StatusView('Pending review', AppColors.pending, Icons.hourglass_top);
  }
  switch (state) {
    case 'CHECKED_IN':
      if (verificationStatus == 'PENDING_REVIEW') {
        return const StatusView('Checked in · Pending review', AppColors.pending, Icons.hourglass_top);
      }
      return dayStatus == 'LATE'
          ? const StatusView('Checked in · Late', AppColors.late, Icons.schedule)
          : const StatusView('Checked in', AppColors.checkedIn, Icons.check_circle);
    case 'CHECKED_OUT':
      return dayStatus == 'LATE'
          ? const StatusView('Checked out · Late', AppColors.late, Icons.logout)
          : const StatusView('Checked out', AppColors.checkedOut, Icons.logout);
  }
  return switch (dayType) {
    'HOLIDAY' => const StatusView('Holiday', AppColors.neutral, Icons.celebration),
    'ON_LEAVE' => const StatusView('On leave', AppColors.neutral, Icons.beach_access),
    'NON_WORKING_DAY' => const StatusView('Day off', AppColors.neutral, Icons.weekend),
    _ => const StatusView('Not checked in', AppColors.neutral, Icons.radio_button_unchecked),
  };
}

StatusView statusForDay(String? dayStatus, String? verificationStatus) {
  if (verificationStatus == 'PENDING_REVIEW') {
    return const StatusView('Pending review', AppColors.pending, Icons.hourglass_top);
  }
  return switch (dayStatus) {
    'PRESENT' => const StatusView('Present', AppColors.checkedIn, Icons.check_circle),
    'LATE' => const StatusView('Late', AppColors.late, Icons.schedule),
    'ABSENT' => const StatusView('Absent', AppColors.rejected, Icons.cancel),
    'HOLIDAY' => const StatusView('Holiday', AppColors.neutral, Icons.celebration),
    'ON_LEAVE' => const StatusView('On leave', AppColors.neutral, Icons.beach_access),
    'NON_WORKING_DAY' => const StatusView('Day off', AppColors.neutral, Icons.weekend),
    _ => const StatusView('—', AppColors.neutral, Icons.remove),
  };
}

StatusView statusForAttempt(String result) => switch (result) {
      'ACCEPTED' => const StatusView('Accepted', AppColors.checkedIn, Icons.check_circle),
      'FLAGGED' => const StatusView('Pending review', AppColors.pending, Icons.hourglass_top),
      _ => const StatusView('Rejected', AppColors.rejected, Icons.cancel),
    };

class StatusChip extends StatelessWidget {
  const StatusChip(this.status, {super.key, this.large = false});
  final StatusView status;
  final bool large;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: large ? 16 : 10, vertical: large ? 10 : 4),
      decoration: BoxDecoration(
        color: status.color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: status.color.withValues(alpha: 0.5)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(status.icon, color: status.color, size: large ? 26 : 16),
        SizedBox(width: large ? 10 : 6),
        Flexible(
          child: Text(
            status.label,
            style: TextStyle(
              color: status.color,
              fontWeight: FontWeight.w700,
              fontSize: large ? 20 : 13,
            ),
          ),
        ),
      ]),
    );
  }
}

// --- Formatting ----------------------------------------------------------------------------

final _time = DateFormat('HH:mm');
String formatTime(DateTime? t) => t == null ? '—' : _time.format(t);

String formatMinutes(int minutes) {
  final h = minutes ~/ 60, m = minutes % 60;
  return h == 0 ? '${m}m' : '${h}h ${m.toString().padLeft(2, '0')}m';
}

/// "09:00:00" -> "09:00"
String shortTime(String? hhmmss) => hhmmss == null ? '' : hhmmss.substring(0, 5);
