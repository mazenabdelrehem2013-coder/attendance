import 'package:flutter/services.dart';

/// Where a downloaded file was saved.
class SavedFile {
  SavedFile({required this.uri, required this.location, required this.filename, required this.mediaType});
  final String uri;

  /// e.g. "Downloads/Attendance"; empty when the file is kept inside the app (Android 8-9).
  final String location;
  final String filename;
  final String mediaType;
}

/// Saves downloaded reports on the phone and opens them (implemented in MainActivity.kt).
abstract class FileSaver {
  Future<SavedFile> save(Uint8List bytes, String filename, String mediaType);

  /// false = no app on the phone can open this kind of file.
  Future<bool> open(SavedFile file);
}

class NativeFileSaver implements FileSaver {
  static const _channel = MethodChannel('attendance/files');

  @override
  Future<SavedFile> save(Uint8List bytes, String filename, String mediaType) async {
    final result = (await _channel.invokeMapMethod<String, String>(
        'save', {'bytes': bytes, 'filename': filename, 'mimeType': mediaType}))!;
    return SavedFile(uri: result['uri']!, location: result['location']!, filename: filename, mediaType: mediaType);
  }

  @override
  Future<bool> open(SavedFile file) async =>
      (await _channel.invokeMethod<bool>('open', {'uri': file.uri, 'mimeType': file.mediaType})) ?? false;
}
