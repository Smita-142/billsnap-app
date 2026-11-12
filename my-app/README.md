# Bill Snap

A responsive React expense-tracking application with an authenticated FastAPI OCR and bill-save flow. Spending charts and the assistant still use demo analytics data.

## Run locally

Use Node.js 22 or newer.

```bash
npm install
npm start
```

The app runs at [http://localhost:3000](http://localhost:3000). Run the interaction tests with `npm test -- --watchAll=false`, and create a production build with `npm run build`.

## Configure OCR and authentication

Create an untracked `my-app/.env.local` file with the frontend's public Supabase configuration and backend API URL:

```dotenv
REACT_APP_SUPABASE_URL=https://your-project.supabase.co
REACT_APP_SUPABASE_ANON_KEY=your-public-anon-key
REACT_APP_API_URL=http://localhost:8000
```

Never put a Supabase service-role key in the frontend. The login and signup pages use Supabase Auth; the resulting access token is sent as a Bearer token to `POST /api/scanner/ocr`, `GET /api/bills/`, `GET /api/bills/categories`, and (only after confirmation) `POST /api/bills/`. Configure the backend CORS allowlist for the frontend origin. Restart the React development server after changing environment variables.

The scanner accepts JPEG and PNG images up to 10 MB, matching the backend defaults. Definite non-bills are rejected; uncertain classifications stay on the scan page and are not mapped into a bill review. Each new upload clears the previous OCR state. Uploaded images and OCR review data remain transient in memory; no bill is created until confirmation.

The current bill API schema does not persist subtotal, tax, invoice number, or phone number. These values are shown from OCR for review only. Category and payment method are manual choices unless the user selects them; undetected fields are left blank.

## Mobile and PWA

- Phone layouts use a fixed, safe-area-aware bottom bar; the tablet layout uses a compact sidebar.
- Bill images can be selected from the gallery or captured through `getUserMedia` where available. Camera access requires HTTPS or localhost; the mobile file-input camera is the fallback.
- In production, the service worker caches the app shell and static assets and provides an offline fallback. Serve the production build over HTTPS or localhost to install it.
- Preferences and chat history use browser storage. Bills are loaded from the authenticated backend; offline support does not perform OCR or save bills.

## Demo limitations

Spending charts and assistant responses still use sample analytics. The privacy page displays the original image and does not redact image pixels. OCR field confidence is not a correctness probability; review all extracted values before saving.
