package com.ghostkey.quadbrain;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class KeystoreManager {
    private static final String KEY_ALIAS = "GhostkeySovereignKey";
    private static final String ANDROID_KEYSTORE = "AndroidKeyStore";

    public static SecretKey getOrCreateKey() throws Exception {
        KeyStore keyStore = KeyStore.getInstance(ANDROID_KEYSTORE);
        keyStore.load(null);

        if (!keyStore.containsAlias(KEY_ALIAS)) {
            KeyGenerator keyGenerator = KeyGenerator.getInstance(
                    KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE);

            KeyGenParameterSpec keySpec = new KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    // In a production app, we would require user authentication here
                    // .setUserAuthenticationRequired(true) 
                    .build();

            keyGenerator.init(keySpec);
            return keyGenerator.generateKey();
        }

        return ((KeyStore.SecretKeyEntry) keyStore.getEntry(KEY_ALIAS, null)).getSecretKey();
    }

    public static String generateRandomIPCKey() {
        byte[] key = new byte[32]; // 256 bits
        new SecureRandom().nextBytes(key);
        return Base64.encodeToString(key, Base64.NO_WRAP);
    }

    public static String encryptString(String plaintext) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
        byte[] iv = cipher.getIV();
        byte[] encrypted = cipher.doFinal(plaintext.getBytes("UTF-8"));
        
        byte[] combined = new byte[iv.length + encrypted.length];
        System.arraycopy(iv, 0, combined, 0, iv.length);
        System.arraycopy(encrypted, 0, combined, iv.length, encrypted.length);
        
        return Base64.encodeToString(combined, Base64.NO_WRAP);
    }

    public static String decryptString(String encryptedBase64) throws Exception {
        byte[] combined = Base64.decode(encryptedBase64, Base64.DEFAULT);
        byte[] iv = new byte[12]; // GCM standard IV length is 12 bytes
        System.arraycopy(combined, 0, iv, 0, 12);
        byte[] encrypted = new byte[combined.length - 12];
        System.arraycopy(combined, 12, encrypted, 0, combined.length - 12);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        GCMParameterSpec spec = new GCMParameterSpec(128, iv);
        cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), spec);
        
        byte[] decrypted = cipher.doFinal(encrypted);
        return new String(decrypted, "UTF-8");
    }
}
