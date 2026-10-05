import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import '../auth/auth_controller.dart';

/// Managers (their team) and HR (everyone) download reports as Excel or PDF:
/// a report made now, or a "ready report" made by a schedule. Employees never see this screen.
class ReportsScreen extends StatelessWidget {
  const ReportsScreen({super.key, this.showLogout = false});

  /// true when this is the account's only screen (staff without an employee record).
  final bool showLogout;

  @override
  Widget build(BuildContext context) => DefaultTabController(
        length: 2,
        child: Scaffold(
          appBar: AppBar(
            title: const Text('Reports'),
            actions: [if (showLogout) const _LogoutButton()],
            bottom: const TabBar(tabs: [Tab(text: 'Create a report'), Tab(text: 'Ready reports')]),
          ),
          body: const TabBarView(children: [_CreateTab(), _ReadyTab()]),
        ),
      );
}

class _LogoutButton extends ConsumerWidget {
  const _LogoutButton();

  @override
  Widget build(BuildContext context, WidgetRef ref) => IconButton(
        tooltip: 'Log out',
        icon: const Icon(Icons.logout),
        onPressed: () => ref.read(authControllerProvider.notifier).logout(),
      );
}

final _day = DateFormat('yyyy-MM-dd');

/// Downloads, saves on the phone and offers to open the file. Shared by both tabs.
Future<void> downloadAndSave(BuildContext context, WidgetRef ref, Future<DownloadedFile> Function() fetch) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    final file = await fetch();
    final saver = ref.read(fileSaverProvider);
    final saved = await saver.save(file.bytes, file.filename, file.mediaType);
    if (saved.location.isEmpty) {
      // Android 8-9: the file stays inside the app, so open it straight away.
      if (!await saver.open(saved)) {
        messenger.showSnackBar(const SnackBar(content: Text('No app on this phone can open this file.')));
      }
      return;
    }
    messenger.showSnackBar(SnackBar(
      content: Text('Saved to ${saved.location}: ${saved.filename}'),
      duration: const Duration(seconds: 6),
      action: SnackBarAction(
        label: 'OPEN',
        onPressed: () async {
          if (!await saver.open(saved)) {
            messenger.showSnackBar(const SnackBar(content: Text('No app on this phone can open this file.')));
          }
        },
      ),
    ));
  } on ApiException catch (e) {
    messenger.showSnackBar(SnackBar(content: Text(e.message)));
  } catch (_) {
    messenger.showSnackBar(const SnackBar(content: Text('The file could not be saved on this phone.')));
  }
}

// --- Create a report ------------------------------------------------------------------------

enum _Kind {
  daily('Daily report'),
  weekly('Weekly report'),
  monthly('Monthly report'),
  period('Attendance summary (dates)'),
  late('Late arrivals'),
  absence('Absences'),
  suspicious('Suspicious attendance');

  const _Kind(this.label);
  final String label;
}

class _CreateTab extends ConsumerStatefulWidget {
  const _CreateTab();

  @override
  ConsumerState<_CreateTab> createState() => _CreateTabState();
}

class _CreateTabState extends ConsumerState<_CreateTab> {
  _Kind _kind = _Kind.daily;
  DateTime _date = DateTime.now();
  DateTime _month = DateTime(DateTime.now().year, DateTime.now().month);
  DateTimeRange _range = DateTimeRange(
      start: DateTime(DateTime.now().year, DateTime.now().month), end: DateTime.now());
  String _format = 'excel';
  bool _busy = false;

  Map<String, dynamic> _body() => {
        'report': _kind.name,
        if (_kind == _Kind.daily || _kind == _Kind.weekly) 'date': _day.format(_date),
        if (_kind == _Kind.monthly) 'month': DateFormat('yyyy-MM').format(_month),
        if (_kind.index >= _Kind.period.index) ...{
          'date_from': _day.format(_range.start),
          'date_to': _day.format(_range.end),
        },
      };

  Future<void> _download() async {
    setState(() => _busy = true);
    await downloadAndSave(context, ref, () => ref.read(apiClientProvider).download('/reports/export/$_format', data: _body()));
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
        context: context, initialDate: _date, firstDate: DateTime(2024), lastDate: DateTime.now());
    if (picked != null) setState(() => _date = picked);
  }

  Future<void> _pickRange() async {
    final picked = await showDateRangePicker(
        context: context, initialDateRange: _range, firstDate: DateTime(2024), lastDate: DateTime.now());
    if (picked != null) setState(() => _range = picked);
  }

  @override
  Widget build(BuildContext context) {
    final nowMonth = DateTime(DateTime.now().year, DateTime.now().month);
    return ListView(padding: const EdgeInsets.all(16), children: [
      DropdownButtonFormField<_Kind>(
        key: const Key('reportKind'),
        initialValue: _kind,
        decoration: const InputDecoration(labelText: 'Report'),
        items: [for (final k in _Kind.values) DropdownMenuItem(value: k, child: Text(k.label))],
        onChanged: (k) => setState(() => _kind = k ?? _kind),
      ),
      const SizedBox(height: 16),
      if (_kind == _Kind.daily || _kind == _Kind.weekly)
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.event),
          title: Text(_kind == _Kind.weekly ? 'Week of ${DateFormat('d MMM yyyy').format(_date)}'
              : DateFormat('EEEE d MMM yyyy').format(_date)),
          trailing: TextButton(onPressed: _pickDate, child: const Text('CHANGE')),
        ),
      if (_kind == _Kind.monthly)
        Row(children: [
          IconButton(
              tooltip: 'Previous month',
              icon: const Icon(Icons.chevron_left),
              onPressed: () => setState(() => _month = DateTime(_month.year, _month.month - 1))),
          Expanded(child: Text(DateFormat('MMMM yyyy').format(_month), textAlign: TextAlign.center)),
          IconButton(
              tooltip: 'Next month',
              icon: const Icon(Icons.chevron_right),
              onPressed: _month == nowMonth ? null : () => setState(() => _month = DateTime(_month.year, _month.month + 1))),
        ]),
      if (_kind.index >= _Kind.period.index)
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.date_range),
          title: Text('${DateFormat('d MMM').format(_range.start)} – ${DateFormat('d MMM yyyy').format(_range.end)}'),
          trailing: TextButton(onPressed: _pickRange, child: const Text('CHANGE')),
        ),
      const SizedBox(height: 16),
      SegmentedButton<String>(
        segments: const [
          ButtonSegment(value: 'excel', label: Text('Excel'), icon: Icon(Icons.table_chart)),
          ButtonSegment(value: 'pdf', label: Text('PDF'), icon: Icon(Icons.picture_as_pdf)),
        ],
        selected: {_format},
        onSelectionChanged: (s) => setState(() => _format = s.first),
      ),
      const SizedBox(height: 24),
      FilledButton.icon(
        key: const Key('download'),
        onPressed: _busy ? null : _download,
        icon: _busy
            ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
            : const Icon(Icons.download),
        label: Text(_busy ? 'Preparing…' : 'DOWNLOAD'),
      ),
      const SizedBox(height: 12),
      const Text('Managers get their own team; HR gets every employee. '
          'Files are saved in the phone\'s Downloads/Attendance folder.',
          style: TextStyle(color: Colors.black54)),
    ]);
  }
}

// --- Ready reports --------------------------------------------------------------------------

class ReadyReport {
  ReadyReport.fromJson(Map<String, dynamic> j)
      : id = j['id'] as String,
        title = j['title'] as String,
        period = j['period'] as String,
        scope = j['scope'] as String,
        format = j['format'] as String,
        filename = j['filename'] as String,
        sizeBytes = j['size_bytes'] as int;

  final String id, title, period, scope, format, filename;
  final int sizeBytes;
}

final readyReportsProvider = FutureProvider.autoDispose<List<ReadyReport>>((ref) async {
  final body = await ref.watch(apiClientProvider).get('/reports/ready', query: {'limit': 100}) as Map<String, dynamic>;
  return [for (final r in body['items'] as List) ReadyReport.fromJson(r as Map<String, dynamic>)];
});

class _ReadyTab extends ConsumerStatefulWidget {
  const _ReadyTab();

  @override
  ConsumerState<_ReadyTab> createState() => _ReadyTabState();
}

class _ReadyTabState extends ConsumerState<_ReadyTab> {
  String? _downloading;

  Future<void> _get(ReadyReport r) async {
    setState(() => _downloading = r.id);
    await downloadAndSave(context, ref, () => ref.read(apiClientProvider).download('/reports/ready/${r.id}/download'));
    if (mounted) setState(() => _downloading = null);
  }

  @override
  Widget build(BuildContext context) {
    final list = ref.watch(readyReportsProvider);
    return RefreshIndicator(
      onRefresh: () => ref.refresh(readyReportsProvider.future),
      child: list.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ListView(children: [
          Padding(
            padding: const EdgeInsets.all(24),
            child: Text(e is ApiException ? e.message : 'Something went wrong.', textAlign: TextAlign.center),
          ),
        ]),
        data: (items) => items.isEmpty
            ? ListView(children: const [
                Padding(
                  padding: EdgeInsets.all(24),
                  child: Text('No ready reports yet. HR can schedule reports in the web dashboard.',
                      textAlign: TextAlign.center),
                ),
              ])
            : ListView.separated(
                itemCount: items.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final r = items[i];
                  final kb = (r.sizeBytes / 1024).ceil();
                  return ListTile(
                    leading: Icon(r.format == 'PDF' ? Icons.picture_as_pdf : Icons.table_chart),
                    title: Text(r.title),
                    subtitle: Text('${r.period}\n${r.scope} · ${r.format == 'PDF' ? 'PDF' : 'Excel'} · $kb KB'),
                    isThreeLine: true,
                    trailing: _downloading == r.id
                        ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.download),
                    onTap: _downloading == null ? () => _get(r) : null,
                  );
                },
              ),
      ),
    );
  }
}
