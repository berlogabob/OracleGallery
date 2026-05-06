# Firebase Setup for NejeDraw

## Prerequisites

- Flutter SDK installed
- Firebase project created

## 1. Install Firebase packages

Run the following command to install Firebase packages:

```bash
flutter pub add firebase_core
flutter pub add cloud_firestore
flutter pub add firebase_auth
flutter pub add firebase_storage
```

## 2. Configure Firebase for iOS

1. In Firebase Console, go to Project Settings
2. Add iOS app with bundle ID `com.example.nejedraw`
3. Download `GoogleService-Info.plist`
4. Place it in `ios/Runner/`
5. Add the following to `ios/Runner/Info.plist`:

```xml
<key>FirebaseAppDelegateProxyEnabled</key>
<false/>
```

## 3. Configure Firebase for Android

1. In Firebase Console, go to Project Settings
2. Add Android app with package name `com.example.neje_draw`
3. Download `google-services.json`
4. Place it in `android/app/`
5. Add the following to `android/build.gradle`:

```gradle
dependencies {
  implementation 'com.google.firebase:firebase-core:19.0.0'
  implementation 'com.google.firebase:firebase-firestore:24.0.0'
  implementation 'com.google.firebase:firebase-auth:23.0.0'
  implementation 'com.google.firebase:firebase-storage:11.8.0'
}
```

Add the following to `android/app/build.gradle`:

```gradle
apply plugin: 'com.google.gms.google-services'
```

## 4. Set up environment variables

Create a `.env` file in the project root with the following content:

```env
FIREBASE_API_KEY=your_api_key_here
FIREBASE_APP_ID=your_app_id_here
FIREBASE_PROJECT_ID=your_project_id_here
FIREBASE_MESSAGING_SENDER_ID=your_messaging_sender_id_here
FIREBASE_MEASUREMENT_ID=your_measurement_id_here
```

Replace `your_api_key_here`, `your_app_id_here`, etc. with actual values from Firebase Console.

## 5. Run the application

```bash
flutter pub get
flutter run
```

## Troubleshooting

- Make sure you have the latest Flutter SDK
- Check Firebase Console for any configuration errors
- Verify that the `.env` file is in the project root
- Ensure that the Firebase configuration files are in the correct locations

## Additional Notes

- For iOS, you may need to adjust the `GoogleService-Info.plist` file
- For Android, ensure that the `google-services.json` file is correctly placed
- Test the application on both iOS and Android devices
