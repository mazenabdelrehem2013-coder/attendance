import CryptoKit
import Flutter
import QuickLook
import UIKit

/// The iOS side of the two channels MainActivity.kt implements on Android.
///
/// "attendance/device":
///  - an EC P-256 key pair created INSIDE the Secure Enclave (simulator: the keychain). The
///    private key can't be read or copied by anyone, including this app.
///  - signing of each attendance request with that key (ECDSA with SHA-256, DER - the same
///    format as Android's SHA256withECDSA, so the server verifies both the same way)
///  - the phone fingerprint: SHA-256 of a random ID kept in this phone's keychain (never synced
///    or backed up to another phone; survives reinstalling the app, like ANDROID_ID)
///  - no Play Integrity on iOS: "integrityToken" fails and the app sends none.
///
/// "attendance/files": saving downloaded reports (Files app > On My iPhone > Raya Attendance)
/// and opening them in a preview that can also share or save them elsewhere.
@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private let keyTag = "attendance_device_key_v1".data(using: .utf8)!
  private let installIdAccount = "attendance_device_id_v1"
  private var preview: FilePreview?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    let messenger = engineBridge.pluginRegistry.registrar(forPlugin: "AttendanceNative")!.messenger()

    FlutterMethodChannel(name: "attendance/device", binaryMessenger: messenger)
      .setMethodCallHandler { [weak self] call, result in
        guard let self = self else { return }
        let args = call.arguments as? [String: Any]
        do {
          switch call.method {
          case "publicKey": result(try self.publicKeyBase64())
          case "sign": result(try self.sign(args?["payload"] as? String ?? ""))
          case "fingerprint": result(try self.fingerprint())
          case "deviceInfo":
            result(["model": "Apple \(Self.modelIdentifier())",
                    "osVersion": "iOS \(UIDevice.current.systemVersion)"])
          case "integrityToken":
            result(FlutterError(code: "INTEGRITY_ERROR", message: "Play Integrity is Android only", details: nil))
          default: result(FlutterMethodNotImplemented)
          }
        } catch {
          result(FlutterError(code: "DEVICE_ERROR", message: error.localizedDescription, details: nil))
        }
      }

    FlutterMethodChannel(name: "attendance/files", binaryMessenger: messenger)
      .setMethodCallHandler { [weak self] call, result in
        guard let self = self else { return }
        let args = call.arguments as? [String: Any]
        do {
          switch call.method {
          case "save":
            guard let bytes = args?["bytes"] as? FlutterStandardTypedData,
                  let filename = args?["filename"] as? String else {
              throw DeviceError("bad arguments")
            }
            result(try self.saveFile(bytes.data, filename))
          case "open": result(self.openFile(args?["uri"] as? String ?? ""))
          default: result(FlutterMethodNotImplemented)
          }
        } catch {
          result(FlutterError(code: "FILE_ERROR", message: error.localizedDescription, details: nil))
        }
      }
  }

  // MARK: - Device key

  private func existingKey() -> SecKey? {
    let query: [String: Any] = [
      kSecClass as String: kSecClassKey,
      kSecAttrApplicationTag as String: keyTag,
      kSecAttrKeyType as String: kSecAttrKeyTypeECSECPrimeRandom,
      kSecReturnRef as String: true,
    ]
    var item: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let found = item else { return nil }
    return (found as! SecKey)
  }

  private func createKey(secureEnclave: Bool) throws -> SecKey {
    var error: Unmanaged<CFError>?
    guard let access = SecAccessControlCreateWithFlags(
      nil, kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
      secureEnclave ? .privateKeyUsage : [], &error) else {
      throw error!.takeRetainedValue() as Error
    }
    var attributes: [String: Any] = [
      kSecAttrKeyType as String: kSecAttrKeyTypeECSECPrimeRandom,
      kSecAttrKeySizeInBits as String: 256,
      kSecPrivateKeyAttrs as String: [
        kSecAttrIsPermanent as String: true,
        kSecAttrApplicationTag as String: keyTag,
        kSecAttrAccessControl as String: access,
      ] as [String: Any],
    ]
    if secureEnclave { attributes[kSecAttrTokenID as String] = kSecAttrTokenIDSecureEnclave }
    guard let key = SecKeyCreateRandomKey(attributes as CFDictionary, &error) else {
      throw error!.takeRetainedValue() as Error
    }
    return key
  }

  private func deviceKey() throws -> SecKey {
    if let key = existingKey() { return key }
    // Every iPhone that runs iOS 15 has a Secure Enclave; the simulator doesn't.
    if SecureEnclave.isAvailable { return try createKey(secureEnclave: true) }
    return try createKey(secureEnclave: false)
  }

  /// X.509 SubjectPublicKeyInfo DER, base64 - the same as Android's PublicKey.getEncoded().
  private func publicKeyBase64() throws -> String {
    guard let publicKey = SecKeyCopyPublicKey(try deviceKey()) else { throw DeviceError("no public key") }
    var error: Unmanaged<CFError>?
    guard let raw = SecKeyCopyExternalRepresentation(publicKey, &error) as Data? else {
      throw error!.takeRetainedValue() as Error
    }
    // raw = 04 || X || Y (65 bytes); prefix the fixed DER header for an EC P-256 public key.
    let header: [UInt8] = [
      0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02, 0x01,
      0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03, 0x01, 0x07, 0x03, 0x42, 0x00,
    ]
    return (Data(header) + raw).base64EncodedString()
  }

  private func sign(_ payload: String) throws -> String {
    var error: Unmanaged<CFError>?
    guard let signature = SecKeyCreateSignature(
      try deviceKey(), .ecdsaSignatureMessageX962SHA256, Data(payload.utf8) as CFData, &error) as Data? else {
      throw error!.takeRetainedValue() as Error
    }
    return signature.base64EncodedString()
  }

  // MARK: - Phone fingerprint

  private func fingerprint() throws -> String {
    let id = try installId()
    return SHA256.hash(data: Data(id.utf8)).map { String(format: "%02x", $0) }.joined()
  }

  private func installId() throws -> String {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrAccount as String: installIdAccount,
      kSecReturnData as String: true,
    ]
    var item: CFTypeRef?
    if SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
       let data = item as? Data, let id = String(data: data, encoding: .utf8) {
      return id
    }
    let id = UUID().uuidString
    let add: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrAccount as String: installIdAccount,
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
      kSecValueData as String: Data(id.utf8),
    ]
    let status = SecItemAdd(add as CFDictionary, nil)
    guard status == errSecSuccess else { throw DeviceError("keychain error \(status)") }
    return id
  }

  /// e.g. "iPhone16,2" (Apple doesn't give apps the marketing name).
  private static func modelIdentifier() -> String {
    var info = utsname()
    uname(&info)
    let machine = withUnsafeBytes(of: &info.machine) { bytes in
      String(decoding: bytes.prefix(while: { $0 != 0 }), as: UTF8.self)
    }
    return machine.isEmpty ? UIDevice.current.model : machine
  }

  // MARK: - Files

  /// Saved in the app's Documents/Attendance folder, which the Files app shows under
  /// On My iPhone > Raya Attendance (UIFileSharingEnabled in Info.plist).
  private func saveFile(_ bytes: Data, _ filename: String) throws -> [String: String] {
    let safeName = filename.replacingOccurrences(of: "[^A-Za-z0-9._-]", with: "_", options: .regularExpression)
    let documents = try FileManager.default.url(
      for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
    let dir = documents.appendingPathComponent("Attendance", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let file = dir.appendingPathComponent(safeName)
    try bytes.write(to: file, options: [.atomic, .completeFileProtection])
    return ["uri": file.absoluteString, "location": "Files > On My iPhone > Raya Attendance > Attendance"]
  }

  /// Shows the file (PDF, Excel...) in Apple's preview, which also has the Share button.
  private func openFile(_ uri: String) -> Bool {
    guard let url = URL(string: uri), FileManager.default.fileExists(atPath: url.path),
          QLPreviewController.canPreview(url as QLPreviewItem),
          let root = Self.topViewController() else { return false }
    let preview = FilePreview(url)
    self.preview = preview // the controller only keeps a weak reference to its data source
    let controller = QLPreviewController()
    controller.dataSource = preview
    root.present(controller, animated: true)
    return true
  }

  private static func topViewController() -> UIViewController? {
    let window = UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .flatMap { $0.windows }
      .first { $0.isKeyWindow }
    var top = window?.rootViewController
    while let presented = top?.presentedViewController { top = presented }
    return top
  }
}

private final class FilePreview: NSObject, QLPreviewControllerDataSource {
  private let url: URL
  init(_ url: URL) { self.url = url }
  func numberOfPreviewItems(in controller: QLPreviewController) -> Int { 1 }
  func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem {
    url as QLPreviewItem
  }
}

private struct DeviceError: LocalizedError {
  let message: String
  init(_ message: String) { self.message = message }
  var errorDescription: String? { message }
}
