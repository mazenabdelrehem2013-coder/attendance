package com.raya.attendance

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.ContentValues
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.provider.Settings
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import android.util.Base64
import androidx.core.content.FileProvider
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.StandardIntegrityManager.PrepareIntegrityTokenRequest
import com.google.android.play.core.integrity.StandardIntegrityManager.StandardIntegrityToken
import com.google.android.play.core.integrity.StandardIntegrityManager.StandardIntegrityTokenProvider
import com.google.android.play.core.integrity.StandardIntegrityManager.StandardIntegrityTokenRequest
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * Device security for attendance (called from Dart through the "attendance/device" channel):
 *  - an EC P-256 key pair created INSIDE the Android Keystore (hardware-backed; StrongBox when
 *    available). The private key can't be read or copied by anyone, including this app.
 *  - signing of each attendance request with that key (SHA256withECDSA)
 *  - the phone fingerprint: SHA-256 of ANDROID_ID (stable for this app until a factory reset)
 *  - Google Play Integrity tokens bound to the request hash (Standard API)
 *
 * And, on the "attendance/files" channel, saving downloaded reports and opening them.
 */
class MainActivity : FlutterActivity() {
    private val keyAlias = "attendance_device_key_v1"
    private var integrityProvider: StandardIntegrityTokenProvider? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "attendance/device")
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "publicKey" -> result.success(publicKeyBase64())
                        "sign" -> result.success(sign(call.argument<String>("payload")!!))
                        "fingerprint" -> result.success(fingerprint())
                        "deviceInfo" -> result.success(
                            mapOf("model" to "${Build.MANUFACTURER} ${Build.MODEL}",
                                  "osVersion" to "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
                        )
                        "integrityToken" -> integrityToken(
                            call.argument<String>("requestHash")!!,
                            call.argument<String>("cloudProjectNumber")!!.toLong(),
                            result,
                        )
                        else -> result.notImplemented()
                    }
                } catch (e: Exception) {
                    result.error("DEVICE_ERROR", e.message, null)
                }
            }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "attendance/files")
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "save" -> result.success(saveFile(
                            call.argument<ByteArray>("bytes")!!,
                            call.argument<String>("filename")!!,
                            call.argument<String>("mimeType")!!,
                        ))
                        "open" -> result.success(openFile(
                            call.argument<String>("uri")!!, call.argument<String>("mimeType")!!))
                        else -> result.notImplemented()
                    }
                } catch (e: Exception) {
                    result.error("FILE_ERROR", e.message, null)
                }
            }
    }

    /**
     * Android 10+: saved in the phone's Downloads/Attendance folder (no permission needed).
     * Android 8-9: kept inside the app; the person opens it (and can save/share it from there).
     */
    private fun saveFile(bytes: ByteArray, filename: String, mimeType: String): Map<String, String> {
        val safeName = filename.replace(Regex("[^A-Za-z0-9._-]"), "_")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, safeName)
                put(MediaStore.Downloads.MIME_TYPE, mimeType)
                put(MediaStore.Downloads.RELATIVE_PATH, "${Environment.DIRECTORY_DOWNLOADS}/Attendance")
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: throw IllegalStateException("Could not create the file in Downloads")
            contentResolver.openOutputStream(uri)!!.use { it.write(bytes) }
            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            contentResolver.update(uri, values, null, null)
            return mapOf("uri" to uri.toString(), "location" to "Downloads/Attendance")
        }
        val dir = File(cacheDir, "reports").apply { mkdirs() }
        val file = File(dir, safeName).apply { writeBytes(bytes) }
        val uri = FileProvider.getUriForFile(this, "$packageName.files", file)
        return mapOf("uri" to uri.toString(), "location" to "")
    }

    /** Opens the file in an app that can show it (Excel, Sheets, a PDF viewer...). */
    private fun openFile(uri: String, mimeType: String): Boolean {
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(Uri.parse(uri), mimeType)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        return try {
            startActivity(intent)
            true
        } catch (e: ActivityNotFoundException) {
            false // no app on the phone can open this kind of file
        }
    }

    private fun keyStore(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    private fun ensureKey() {
        if (keyStore().containsAlias(keyAlias)) return
        fun generate(strongBox: Boolean) {
            val builder = KeyGenParameterSpec.Builder(keyAlias, KeyProperties.PURPOSE_SIGN)
                .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256)
            if (strongBox && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) builder.setIsStrongBoxBacked(true)
            KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").run {
                initialize(builder.build())
                generateKeyPair()
            }
        }
        try {
            generate(strongBox = true)
        } catch (e: StrongBoxUnavailableException) {
            generate(strongBox = false) // phone has no StrongBox chip: regular hardware Keystore
        }
    }

    private fun publicKeyBase64(): String {
        ensureKey()
        val encoded = keyStore().getCertificate(keyAlias).publicKey.encoded // X.509 SubjectPublicKeyInfo DER
        return Base64.encodeToString(encoded, Base64.NO_WRAP)
    }

    private fun sign(payload: String): String {
        ensureKey()
        val key = keyStore().getKey(keyAlias, null) as PrivateKey
        val signature = Signature.getInstance("SHA256withECDSA").run {
            initSign(key)
            update(payload.toByteArray(Charsets.UTF_8))
            sign()
        }
        return Base64.encodeToString(signature, Base64.NO_WRAP)
    }

    @SuppressLint("HardwareIds")
    private fun fingerprint(): String {
        val androidId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: ""
        val digest = MessageDigest.getInstance("SHA-256").digest(androidId.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }

    private fun integrityToken(requestHash: String, cloudProjectNumber: Long, result: MethodChannel.Result) {
        fun request(provider: StandardIntegrityTokenProvider) {
            provider.request(StandardIntegrityTokenRequest.builder().setRequestHash(requestHash).build())
                .addOnSuccessListener { token: StandardIntegrityToken -> result.success(token.token()) }
                .addOnFailureListener { e -> result.error("INTEGRITY_ERROR", e.message, null) }
        }
        integrityProvider?.let { return request(it) }
        IntegrityManagerFactory.createStandard(applicationContext)
            .prepareIntegrityToken(
                PrepareIntegrityTokenRequest.builder().setCloudProjectNumber(cloudProjectNumber).build()
            )
            .addOnSuccessListener { provider ->
                integrityProvider = provider
                request(provider)
            }
            .addOnFailureListener { e -> result.error("INTEGRITY_ERROR", e.message, null) }
    }
}
