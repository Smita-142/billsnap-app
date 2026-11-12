import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
jest.mock('./lib/supabase', () => ({ supabase: null }));
import App from './App';

beforeEach(() => {
  window.history.replaceState({}, '', '/');
  window.localStorage.clear();
  window.sessionStorage.clear();
  URL.createObjectURL = jest.fn(() => 'blob:test-image');
  URL.revokeObjectURL = jest.fn();
});

async function renderDashboard() {
  const rendered = render(<App />);
  fireEvent.click(screen.getByRole('link', { name: /open bill snap app/i }));
  await screen.findByRole('heading', { name: /welcome|good evening,/i });
  return rendered;
}

const response = (body, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

const billOCR = (overrides = {}) => ({
  classification: {
    label: 'bill',
    message: 'Valid receipt detected.',
    should_continue_field_extraction: true,
    reasons: ['Receipt-like structure detected.'],
    warnings: [],
    confidence: 0.9,
  },
  fields: {
    merchant_name: { value: 'Fresh Market', confidence_level: 'high', uncertain: false },
    bill_date: { value: '2025-03-16', confidence_level: 'medium', uncertain: false },
    total_amount: { value: '125.50', confidence_level: 'high', uncertain: false },
    tax: { value: null, confidence_level: 'low', uncertain: true },
    invoice_number: { value: null, confidence_level: 'low', uncertain: true },
    currency: { value: 'INR', confidence_level: 'high', uncertain: false },
    ...overrides,
  },
  warnings: [],
  processing_time_ms: 88,
});

function authenticate() {
  window.localStorage.setItem('sb-demo-auth-token', JSON.stringify({ access_token: 'test-access-token' }));
}

test('shows the marketing landing page and opens the existing app', async () => {
  render(<App />);

  expect(screen.getByRole('heading', { name: /your bills\..*your money\..*your privacy/i })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /scan a bill/i })).toHaveAttribute('href', '/scan');
  expect(screen.queryByRole('navigation', { name: /mobile navigation/i })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('link', { name: /open bill snap app/i }));

  expect(await screen.findByRole('heading', { name: /welcome|good evening,/i })).toBeInTheDocument();
});

test('makes the sidebar brand and workspace return to the landing page', async () => {
  await renderDashboard();

  expect(screen.queryByText(/free plan/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /explore plus/i })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('link', { name: /bill snap home/i }));
  expect(await screen.findByRole('heading', { name: /your bills\..*your money\..*your privacy/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('link', { name: /open bill snap app/i }));
  await screen.findByRole('heading', { name: /welcome|good evening,/i });
  fireEvent.click(screen.getByRole('link', { name: /personal space home/i }));
  expect(await screen.findByRole('heading', { name: /your bills\..*your money\..*your privacy/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('link', { name: /open bill snap app/i }));
  await screen.findByRole('heading', { name: /welcome|good evening,/i });
  fireEvent.click(screen.getByRole('button', { name: /collapse sidebar/i }));
  expect(screen.getByRole('complementary')).toHaveClass('sidebar-collapsed');
  fireEvent.click(screen.getByRole('button', { name: /expand sidebar/i }));
  fireEvent.click(screen.getByRole('button', { name: /open account settings/i }));
  expect(await screen.findByRole('heading', { name: /your account. your control/i })).toBeInTheDocument();
});

test('provides login and signup entry points and routes', async () => {
  const landing = render(<App />);
  expect(screen.getByRole('heading', { name: /your bills\..*your money\..*your privacy/i })).toBeInTheDocument();
  expect(screen.getAllByRole('link', { name: /sign in|get started/i }).length).toBeGreaterThan(0);
  landing.unmount();

  for (const path of ['/login', '/signup']) {
    window.history.replaceState({}, '', path);
    const app = render(<App />);
    expect(await screen.findByRole('heading', { name: /sign in to bill snap|create your account/i })).toBeInTheDocument();
    app.unmount();
  }
});

test('does not seed bill history with demo transactions', async () => {
  await renderDashboard();

  fireEvent.click(screen.getByRole('link', { name: /my bills/i }));

  expect(await screen.findByRole('heading', { name: /your expense history/i })).toBeInTheDocument();
  expect(await screen.findByText(/no bills found/i)).toBeInTheDocument();
  expect(screen.queryByText(/the daily market|zomato|starbucks/i)).not.toBeInTheDocument();
});

test('opens the scan workspace from the primary action', async () => {
  await renderDashboard();

  fireEvent.click(screen.getByRole('button', { name: /add a bill/i }));

  expect(await screen.findByRole('heading', { name: /let.s scan your bill/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /analyze bill/i })).toBeDisabled();
});

test('sends the selected image with the authenticated token and reviews actual OCR fields', async () => {
  authenticate();
  const fetchMock = jest.fn((url, options) => {
    if (url.endsWith('/api/bills/?page_size=100')) return Promise.resolve(response({ items: [] }));
    if (url.endsWith('/api/bills/categories')) return Promise.resolve(response([{ id: 'cat-1', name: 'Groceries' }]));
    if (url.endsWith('/api/scanner/ocr')) return Promise.resolve(response(billOCR()));
    return Promise.reject(new Error(`Unexpected request: ${url}`));
  });
  global.fetch = fetchMock;
  const { container } = await renderDashboard();
  fireEvent.click(screen.getByRole('button', { name: /add a bill/i }));
  const image = new File(['image'], 'receipt.png', { type: 'image/png' });
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [image] } });
  fireEvent.click(screen.getByRole('button', { name: /analyze bill/i }));

  expect(await screen.findByRole('heading', { name: /does everything look right/i })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining('/api/scanner/ocr'),
    expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ Authorization: 'Bearer test-access-token' }) }),
  );
  expect(screen.getByLabelText(/merchant name/i)).toHaveValue('Fresh Market');
  expect(screen.getByLabelText(/bill date/i)).toHaveValue('2025-03-16');
  expect(screen.getByLabelText(/total amount/i)).toHaveValue('125.50');
  expect(screen.getByLabelText(/tax \/ gst/i)).toHaveValue('');
  expect(screen.getByLabelText(/invoice number/i)).toHaveValue('');
  expect(screen.getByLabelText(/payment method/i)).toHaveValue('');
  expect(screen.getByAltText(/uploaded bill preview/i)).toBeInTheDocument();
});

test('does not navigate to review for a non-bill and keeps its image available', async () => {
  authenticate();
  global.fetch = jest.fn((url) => {
    if (url.endsWith('/api/bills/?page_size=100')) return Promise.resolve(response({ items: [] }));
    if (url.endsWith('/api/bills/categories')) return Promise.resolve(response([]));
    if (url.endsWith('/api/scanner/ocr')) return Promise.resolve(response({
      detail: {
        code: 'not_a_bill',
        classification: { label: 'non_bill', message: 'This image does not appear to be a bill.', reasons: ['No receipt structure.'], warnings: [] },
      },
    }, 422));
    return Promise.reject(new Error(`Unexpected request: ${url}`));
  });
  const { container } = await renderDashboard();
  fireEvent.click(screen.getByRole('button', { name: /add a bill/i }));
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(['image'], 'selfie.png', { type: 'image/png' })] } });
  fireEvent.click(screen.getByRole('button', { name: /analyze bill/i }));

  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/scanner/ocr'),
    expect.objectContaining({ method: 'POST' }),
  ));
  expect(await screen.findByRole('alert')).toHaveTextContent(/this image does not appear to be a bill/i);
  expect(screen.getByAltText(/selected bill preview/i)).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: /does everything look right/i })).not.toBeInTheDocument();
});

test('keeps an uncertain classification out of bill review', async () => {
  authenticate();
  global.fetch = jest.fn(url => {
    if (url.endsWith('/api/bills/?page_size=100')) return Promise.resolve(response({ items: [] }));
    if (url.endsWith('/api/bills/categories')) return Promise.resolve(response([]));
    if (url.endsWith('/api/scanner/ocr')) return Promise.resolve(response({
      classification: {
        label: 'uncertain',
        message: 'We could not confidently identify this image as a bill.',
        should_continue_field_extraction: false,
        reasons: ['Receipt structure is unclear.'],
        warnings: ['Try a clearer image.'],
      },
      fields: {},
      warnings: ['Try a clearer image.'],
    }));
    return Promise.reject(new Error(`Unexpected request: ${url}`));
  });
  const { container } = await renderDashboard();
  fireEvent.click(screen.getByRole('button', { name: /add a bill/i }));
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(['image'], 'uncertain.png', { type: 'image/png' })] } });
  fireEvent.click(screen.getByRole('button', { name: /analyze bill/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not confidently identify/i);
  expect(screen.getByAltText(/selected bill preview/i)).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: /does everything look right/i })).not.toBeInTheDocument();
});

test('does not fabricate missing OCR values and requires correction before save', async () => {
  authenticate();
  const fetchMock = jest.fn((url) => {
    if (url.endsWith('/api/bills/?page_size=100')) return Promise.resolve(response({ items: [] }));
    if (url.endsWith('/api/bills/categories')) return Promise.resolve(response([]));
    if (url.endsWith('/api/scanner/ocr')) return Promise.resolve(response(billOCR({
      merchant_name: { value: null, confidence_level: 'low', uncertain: true },
      bill_date: { value: null, confidence_level: 'low', uncertain: true },
      total_amount: { value: null, confidence_level: 'low', uncertain: true },
      currency: { value: null, confidence_level: 'low', uncertain: true },
    })));
    return Promise.reject(new Error(`Unexpected request: ${url}`));
  });
  global.fetch = fetchMock;
  const { container } = await renderDashboard();
  fireEvent.click(screen.getByRole('button', { name: /add a bill/i }));
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(['image'], 'partial.png', { type: 'image/png' })] } });
  fireEvent.click(screen.getByRole('button', { name: /analyze bill/i }));

  expect(await screen.findByRole('heading', { name: /does everything look right/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/merchant name/i)).toHaveValue('');
  expect(screen.getByLabelText(/bill date/i)).toHaveValue('');
  expect(screen.getByLabelText(/total amount/i)).toHaveValue('');
  fireEvent.click(screen.getByRole('button', { name: /confirm & save bill/i }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/merchant, date, total and currency are required/i);
  expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('/api/bills/'), expect.objectContaining({ method: 'POST' }));
});

test('saves only confirmed review values to the authenticated bill API', async () => {
  authenticate();
  const fetchMock = jest.fn((url, options) => {
    if (url.endsWith('/api/bills/?page_size=100')) return Promise.resolve(response({ items: [] }));
    if (url.endsWith('/api/bills/categories')) return Promise.resolve(response([{ id: 'cat-1', name: 'Groceries' }]));
    if (url.endsWith('/api/scanner/ocr')) return Promise.resolve(response(billOCR()));
    if (url.endsWith('/api/bills/') && options.method === 'POST') return Promise.resolve(response({
      merchant_name: 'Fresh Market',
      bill_date: '2025-03-16',
      total_amount: '125.50',
      currency: 'INR',
      category_id: null,
      payment_method: null,
      review_status: 'pending',
    }));
    return Promise.reject(new Error(`Unexpected request: ${url}`));
  });
  global.fetch = fetchMock;
  const { container } = await renderDashboard();
  fireEvent.click(screen.getByRole('button', { name: /add a bill/i }));
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(['image'], 'confirmed.png', { type: 'image/png' })] } });
  fireEvent.click(screen.getByRole('button', { name: /analyze bill/i }));
  await screen.findByRole('heading', { name: /does everything look right/i });
  fireEvent.click(screen.getByRole('button', { name: /confirm & save bill/i }));

  await waitFor(() => expect(fetchMock.mock.calls.some(([url, options]) => url.endsWith('/api/bills/') && options.method === 'POST')).toBe(true), { timeout: 10000 });
  expect(await screen.findByRole('heading', { name: /your expense history/i }, { timeout: 10000 })).toBeInTheDocument();
  expect(screen.getByText('Fresh Market')).toBeInTheDocument();
  const saveCall = fetchMock.mock.calls.find(([url, options]) => url.endsWith('/api/bills/') && options.method === 'POST');
  expect(saveCall).toBeDefined();
  expect(saveCall[1].headers.Authorization).toBe('Bearer test-access-token');
  expect(JSON.parse(saveCall[1].body)).toEqual({
    merchant_name: 'Fresh Market',
    bill_date: '2025-03-16',
    total_amount: '125.50',
    currency: 'INR',
    bill_type: 'receipt',
  });
}, 10000);

test('offers authenticated demo OCR and explains when Supabase is not configured', async () => {
  global.fetch = jest.fn();
  const { container } = await renderDashboard();
  fireEvent.click(screen.getByRole('button', { name: /add a bill/i }));
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(['image'], 'receipt.png', { type: 'image/png' })] } });

  expect(screen.getByRole('button', { name: /enable demo OCR/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /enable demo OCR/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/Supabase is not configured/i);
  expect(global.fetch).not.toHaveBeenCalledWith(expect.stringContaining('/api/scanner/ocr'), expect.anything());
});

test('opens the mobile menu and navigates to settings', async () => {
  await renderDashboard();

  fireEvent.click(screen.getByRole('button', { name: /open menu/i }));
  fireEvent.click(within(screen.getByRole('navigation', { name: /more navigation/i })).getByRole('link', { name: /settings & privacy/i }));

  expect(await screen.findByRole('heading', { name: /your account. your control/i })).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: /mobile navigation/i })).toBeInTheDocument();
});

test('shows user account profile and authentication controls', async () => {
  await renderDashboard();

  fireEvent.click(screen.getByRole('button', { name: /open account settings/i }));

  expect(await screen.findByRole('heading', { name: /user account/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/your name/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /sign in \/ sign up|sign out/i })).toBeInTheDocument();
});

test('uses the browser camera and stops its stream when cancelled', async () => {
  await renderDashboard();
  const stop = jest.fn();
  const stream = { getTracks: () => [{ stop }] };
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: jest.fn().mockResolvedValue(stream) },
  });
  fireEvent.click(screen.getByRole('button', { name: /add a bill/i }));
  const cameraButton = await screen.findByRole('button', { name: 'Take a photo' });
  fireEvent.click(cameraButton);
  expect(await screen.findByLabelText(/camera preview/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
  await waitFor(() => expect(stop).toHaveBeenCalled());
});

test('explains denied camera access and falls back to the device camera picker', async () => {
  await renderDashboard();
  const error = Object.assign(new Error('Permission denied'), { name: 'NotAllowedError' });
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: jest.fn().mockRejectedValue(error) },
  });
  const picker = jest.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => {});
  fireEvent.click(screen.getByRole('button', { name: /add a bill/i }));
  fireEvent.click(await screen.findByRole('button', { name: 'Take a photo' }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/camera access was denied/i);
  expect(picker).toHaveBeenCalled();
  picker.mockRestore();
});
