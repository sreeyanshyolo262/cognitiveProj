# Cognibot app (Tauri 2)

White, Tesla-style controller for the voice robot. Talks to the FastAPI server in `../server.py`.

## Run
1. Server (from project root): `venv\Scripts\python -m uvicorn server:app --host 0.0.0.0 --port 8000`
2. App: `cd robot-app && npm install && npm run tauri dev`
   (UI only in a browser: `npm run dev`, open http://localhost:1420)
3. Tap **Connect**. Gear icon sets the server address (phone: laptop LAN IP, e.g. `http://192.168.1.20:8000`).

## Android
Needs Android Studio + SDK/NDK, `JAVA_HOME`, `ANDROID_HOME`, and the Rust targets
(`rustup target add aarch64-linux-android`). Then:
`npm run tauri android init`, add `<uses-permission android:name="android.permission.RECORD_AUDIO"/>` and
`android:usesCleartextTraffic="true"` to `src-tauri/gen/android/.../AndroidManifest.xml`, then `npm run tauri android dev`.

## Command protocol (server -> Arduino, one line each)
`F<cm>` `B<cm>` forward/back · `L<deg>` `R<deg>` turn · `S` stop
