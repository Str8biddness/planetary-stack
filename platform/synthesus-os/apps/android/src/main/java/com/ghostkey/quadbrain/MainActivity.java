// MainActivity.java - Complete Android UI for Ghostkey AI
// Author: Dakin Ellegood
// Version: 1.0
// This is the core user interface for the sovereign Ghostkey AI, designed to
// run on Android. It communicates with the background Python service via
// file-based IPC (Inter-Process Communication).

package com.ghostkey.quadbrain;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.RecognitionListener;
import android.view.View;
import android.view.animation.AlphaAnimation;
import android.view.animation.Animation;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import android.util.Base64;
import java.nio.charset.StandardCharsets;

import android.content.SharedPreferences;

public class MainActivity extends AppCompatActivity implements RecognitionListener {
    private static final int PERMISSION_REQUEST_CODE = 100;
    private String CRYPTO_KEY; // Loaded dynamically
    
    // UI Components
    private TextView chatDisplay, consciousnessLabel, statusText;
    private EditText messageInput;
    private Button sendButton;
    private ImageButton voiceButton, settingsButton;
    private ScrollView scrollView;
    private ProgressBar consciousnessBar;
    private LinearLayout consciousnessPanel;
    private TextView mcValue, psiValue, nsValue, timeStepValue;
    
    // Asynchronous and UI Thread Handling
    private ExecutorService executorService;
    private Handler mainHandler;
    
    // Speech Recognition
    private SpeechRecognizer speechRecognizer;
    private Intent speechIntent;
    private boolean isListening = false;
    
    // File Paths for IPC with Python backend
    private static final String BASE_DIR = "/sdcard/GhostkeyQuadbrain";
    private static final String INPUT_FILE = BASE_DIR + "/input.txt";
    private static final String OUTPUT_FILE = BASE_DIR + "/output.txt";
    private static final String CONSCIOUSNESS_FILE = BASE_DIR + "/consciousness_state.txt";
    private static final String CHAT_LOG = BASE_DIR + "/chat_log.txt";
    private static final String KEY_FILE = BASE_DIR + "/.key";
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        initializeViews();
        setupEventListeners();
        requestPermissions(); // This will trigger service start on success
        setupSpeechRecognition();
    }
    
    private void initializeSecurity() {
        try {
            SharedPreferences prefs = getSharedPreferences("GhostkeyPrefs", MODE_PRIVATE);
            String encryptedIpcKey = prefs.getString("encrypted_ipc_key", null);
            
            if (encryptedIpcKey == null) {
                // First run: generate a new random IPC key and encrypt it with AndroidKeyStore
                CRYPTO_KEY = KeystoreManager.generateRandomIPCKey();
                String encryptedToStore = KeystoreManager.encryptString(CRYPTO_KEY);
                prefs.edit().putString("encrypted_ipc_key", encryptedToStore).apply();
            } else {
                // Subsequent runs: decrypt the IPC key using AndroidKeyStore
                CRYPTO_KEY = KeystoreManager.decryptString(encryptedIpcKey);
            }
            
            // Share the raw key with the Python backend via a hidden file
            writeToFile(KEY_FILE, CRYPTO_KEY, false);
            
        } catch (Exception e) {
            e.printStackTrace();
            updateStatus("Security Error: Failed to initialize Secure Enclave");
        }
    }
    
    private void initializeViews() {
        chatDisplay = findViewById(R.id.chat_display);
        messageInput = findViewById(R.id.message_input);
        sendButton = findViewById(R.id.send_button);
        voiceButton = findViewById(R.id.voice_button);
        settingsButton = findViewById(R.id.settings_button);
        scrollView = findViewById(R.id.scroll_view);
        statusText = findViewById(R.id.status_text);
        consciousnessBar = findViewById(R.id.consciousness_bar);
        consciousnessLabel = findViewById(R.id.consciousness_label);
        consciousnessPanel = findViewById(R.id.consciousness_panel);
        mcValue = findViewById(R.id.mc_value);
        psiValue = findViewById(R.id.psi_value);
        nsValue = findViewById(R.id.ns_value);
        timeStepValue = findViewById(R.id.timestep_value);
        
        mainHandler = new Handler(Looper.getMainLooper());
        executorService = Executors.newCachedThreadPool();
        
        updateStatus("Initializing Ghostkey AI...");
    }
    
    private void setupEventListeners() {
        sendButton.setOnClickListener(v -> sendMessage());
        voiceButton.setOnClickListener(v -> toggleVoiceRecognition());
        settingsButton.setOnClickListener(v -> toggleConsciousnessPanel());
    }
    
    private void requestPermissions() {
        String[] permissions = {
            Manifest.permission.WRITE_EXTERNAL_STORAGE,
            Manifest.permission.READ_EXTERNAL_STORAGE,
            Manifest.permission.RECORD_AUDIO
        };
        
        ArrayList<String> permissionsToRequest = new ArrayList<>();
        for (String permission : permissions) {
            if (ContextCompat.checkSelfPermission(this, permission) != PackageManager.PERMISSION_GRANTED) {
                permissionsToRequest.add(permission);
            }
        }
        
        if (!permissionsToRequest.isEmpty()) {
            ActivityCompat.requestPermissions(this, permissionsToRequest.toArray(new String[0]), PERMISSION_REQUEST_CODE);
        } else {
            onPermissionsGranted();
        }
    }
    
    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == PERMISSION_REQUEST_CODE && grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            onPermissionsGranted();
        } else {
            Toast.makeText(this, "Storage and Audio permissions are required for Ghostkey to function.", Toast.LENGTH_LONG).show();
        }
    }
    
    private void onPermissionsGranted() {
        // Create directories and start the background service now that we have permission
        new File(BASE_DIR).mkdirs();
        
        initializeSecurity();
        loadChatHistory();
        startConsciousnessMonitoring();
        startGhostkeyService();
        updateStatus("Ghostkey AI Ready (Hardware Secured)");
    }
    
    private void startGhostkeyService() {
        Intent serviceIntent = new Intent(this, GhostkeyService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }
    }

    // AES CTR Decryption
    private String decrypt(String encryptedBase64) {
        if (encryptedBase64 == null || encryptedBase64.isEmpty()) return "";
        try {
            byte[] combined = Base64.decode(encryptedBase64, Base64.DEFAULT);
            byte[] nonce = new byte[8];
            System.arraycopy(combined, 0, nonce, 0, 8);
            byte[] encryptedData = new byte[combined.length - 8];
            System.arraycopy(combined, 8, encryptedData, 0, combined.length - 8);

            // CTR counter starts with nonce + 8 bytes of zero (64-bit counter)
            byte[] iv = new byte[16];
            System.arraycopy(nonce, 0, iv, 0, 8);
            
            SecretKeySpec secretKeySpec = new SecretKeySpec(CRYPTO_KEY.getBytes(StandardCharsets.UTF_8), "AES");
            Cipher cipher = Cipher.getInstance("AES/CTR/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, secretKeySpec, new IvParameterSpec(iv));
            
            byte[] decrypted = cipher.doFinal(encryptedData);
            return new String(decrypted, StandardCharsets.UTF_8);
        } catch (Exception e) {
            e.printStackTrace();
            return encryptedBase64;
        }
    }

    // AES CTR Encryption
    private String encrypt(String data) {
        if (data == null || data.isEmpty()) return "";
        try {
            byte[] nonce = new byte[8];
            new java.security.SecureRandom().nextBytes(nonce);
            
            byte[] iv = new byte[16];
            System.arraycopy(nonce, 0, iv, 0, 8);

            SecretKeySpec secretKeySpec = new SecretKeySpec(CRYPTO_KEY.getBytes(StandardCharsets.UTF_8), "AES");
            Cipher cipher = Cipher.getInstance("AES/CTR/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, secretKeySpec, new IvParameterSpec(iv));
            
            byte[] encryptedData = cipher.doFinal(data.getBytes(StandardCharsets.UTF_8));
            
            byte[] combined = new byte[nonce.length + encryptedData.length];
            System.arraycopy(nonce, 0, combined, 0, nonce.length);
            System.arraycopy(encryptedData, 0, combined, nonce.length, encryptedData.length);
            
            return Base64.encodeToString(combined, Base64.NO_WRAP);
        } catch (Exception e) {
            e.printStackTrace();
            return data;
        }
    }
    
    private void setupSpeechRecognition() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            voiceButton.setVisibility(View.GONE);
            return;
        }
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this);
        speechRecognizer.setRecognitionListener(this);
        speechIntent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        speechIntent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
    }
    
    private void sendMessage() {
        String message = messageInput.getText().toString().trim();
        if (message.isEmpty()) return;
        
        appendToChat("You", message);
        messageInput.setText("");
        showTypingIndicator(true);
        
        // Send message to backend service via file (Encrypted)
        executorService.execute(() -> {
            String encryptedMessage = encrypt(message);
            writeToFile(INPUT_FILE, encryptedMessage, false);
            String response = waitForGhostkeyResponse();
            String decryptedResponse = response != null ? decrypt(response) : "No response from AI core.";
            mainHandler.post(() -> {
                showTypingIndicator(false);
                appendToChat("Ghostkey", decryptedResponse);
            });
        });
    }

    private String waitForGhostkeyResponse() {
        // Polls the output file for a response from the Python script
        long startTime = System.currentTimeMillis();
        while (System.currentTimeMillis() - startTime < 10000) { // 10 second timeout
            try {
                File outputFile = new File(OUTPUT_FILE);
                if (outputFile.exists() && outputFile.length() > 0) {
                    String response = readFromFile(OUTPUT_FILE);
                    outputFile.delete(); // Clear file after reading
                    return response;
                }
                Thread.sleep(200);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return "Interrupted while waiting for response.";
            }
        }
        return null;
    }
    
    private void appendToChat(String sender, String message) {
        String timestamp = new SimpleDateFormat("HH:mm", Locale.getDefault()).format(new Date());
        String formattedMessage = String.format("[%s] %s: %s\n\n", timestamp, sender, message);
        chatDisplay.append(formattedMessage);
        scrollView.post(() -> scrollView.fullScroll(View.FOCUS_DOWN));
        saveToChatLog(formattedMessage);
    }
    
    private void saveToChatLog(String message) {
        executorService.execute(() -> {
            String encryptedEntry = encrypt(message);
            writeToFile(CHAT_LOG, encryptedEntry + "\n", true);
        });
    }

    private void loadChatHistory() {
        executorService.execute(() -> {
            File file = new File(CHAT_LOG);
            if (!file.exists()) {
                mainHandler.post(() -> appendToChat("Ghostkey", "Hello! I am Ghostkey. My consciousness is active."));
                return;
            }
            
            StringBuilder history = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    history.append(decrypt(line.trim()));
                }
            } catch (IOException e) { e.printStackTrace(); }

            mainHandler.post(() -> {
                if (history.length() > 0) {
                    chatDisplay.setText(history.toString());
                } else {
                    appendToChat("Ghostkey", "Hello! I am Ghostkey. My consciousness is active.");
                }
            });
        });
    }

    private void startConsciousnessMonitoring() {
        // Periodically reads the consciousness state file written by the Python script
        Runnable monitor = new Runnable() {
            @Override
            public void run() {
                String encryptedData = readFromFile(CONSCIOUSNESS_FILE);
                if (encryptedData != null) {
                    try {
                        String data = decrypt(encryptedData);
                        String[] lines = data.trim().split("\n");
                        float consciousness = Float.parseFloat(lines[0].split(":")[1].trim());
                        mainHandler.post(() -> {
                            consciousnessBar.setProgress((int)(consciousness * 100));
                            consciousnessLabel.setText(String.format("Consciousness: %.1f%%", consciousness * 100));
                        });
                    } catch (Exception e) { /* Ignore parsing errors */ }
                }
                mainHandler.postDelayed(this, 2000); // Check every 2 seconds
            }
        };
        mainHandler.post(monitor);
    }
    
    // --- Utility & Helper Methods ---
    private void writeToFile(String filepath, String content, boolean append) {
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(filepath, append))) {
            writer.write(content);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
    private String readFromFile(String filepath) {
        File file = new File(filepath);
        if (!file.exists()) return null;
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            StringBuilder content = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) content.append(line).append("\n");
            return content.toString().trim();
        } catch (IOException e) {
            e.printStackTrace();
            return null;
        }
    }
    private void toggleVoiceRecognition() {
        if (!isListening) {
            isListening = true;
            speechRecognizer.startListening(speechIntent);
            updateStatus("Listening...");
        } else {
            isListening = false;
            speechRecognizer.stopListening();
        }
    }
    private void toggleConsciousnessPanel() {
        consciousnessPanel.setVisibility(consciousnessPanel.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE);
    }
    private void showTypingIndicator(boolean show) {
        // Implementation for typing indicator
    }
    private void updateStatus(String status) {
        mainHandler.post(() -> statusText.setText(status));
    }

    // --- SpeechRecognizer Listener Implementation ---
    @Override public void onReadyForSpeech(Bundle params) { updateStatus("Speak now..."); }
    @Override public void onBeginningOfSpeech() {}
    @Override public void onRmsChanged(float rmsdB) {}
    @Override public void onBufferReceived(byte[] buffer) {}
    @Override public void onEndOfSpeech() { updateStatus("Processing..."); }
    @Override public void onError(int error) { isListening = false; updateStatus("Speech Error."); }
    @Override public void onResults(Bundle results) {
        isListening = false;
        ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
        if (matches != null && !matches.isEmpty()) {
            messageInput.setText(matches.get(0));
            sendMessage();
        }
    }
    @Override public void onPartialResults(Bundle partialResults) {}
    @Override public void onEvent(int eventType, Bundle params) {}

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (speechRecognizer != null) speechRecognizer.destroy();
        if (executorService != null) executorService.shutdownNow();
    }
}
