import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/providers.dart';
import '../../models/models.dart';

final profileProvider = FutureProvider.autoDispose<Profile>((ref) async {
  final json = await ref.watch(apiClientProvider).get('/employees/me');
  return Profile.fromJson(json as Map<String, dynamic>);
});

final todayProvider = FutureProvider.autoDispose<Today>((ref) async {
  final json = await ref.watch(apiClientProvider).get('/attendance/today');
  return Today.fromJson(json as Map<String, dynamic>);
});

/// History for one calendar month (key: first day of the month).
final historyProvider = FutureProvider.autoDispose.family<List<AttendanceDay>, DateTime>((ref, month) async {
  final fmt = DateFormat('yyyy-MM-dd');
  final last = DateTime(month.year, month.month + 1, 0);
  final json = await ref.watch(apiClientProvider).get(
    '/attendance/history',
    query: {'from': fmt.format(month), 'to': fmt.format(last)},
  );
  return [for (final d in json as List) AttendanceDay.fromJson(d as Map<String, dynamic>)];
});
