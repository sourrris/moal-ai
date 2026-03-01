import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockFetchModels = vi.fn();
const mockFetchModelMetrics = vi.fn();
const mockFetchTrainingRuns = vi.fn();
const mockTrainModel = vi.fn();
const mockActivateModel = vi.fn();

vi.mock('../../../app/state/auth-context', () => ({
  useAuth: () => ({ token: 'test-token' })
}));

vi.mock('../../../app/state/ui-context', () => ({
  useUI: () => ({ tenant: 'tenant-alpha' })
}));

vi.mock('../../../shared/api/models', () => ({
  fetchModels: (...args: unknown[]) => mockFetchModels(...args),
  fetchModelMetrics: (...args: unknown[]) => mockFetchModelMetrics(...args),
  fetchTrainingRuns: (...args: unknown[]) => mockFetchTrainingRuns(...args),
  trainModel: (...args: unknown[]) => mockTrainModel(...args),
  activateModel: (...args: unknown[]) => mockActivateModel(...args)
}));

import { ModelsPage } from '../ModelsPage';

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/models']}>
        <ModelsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const baseModelsPayload = {
  active_model: {
    model_name: 'risk_autoencoder',
    model_version: '20260301000000',
    feature_dim: 8,
    threshold: 0.8
  },
  items: [
    {
      model_name: 'risk_autoencoder',
      model_version: '20260301000000',
      threshold: 0.8,
      updated_at: '2026-03-01T10:00:00Z',
      inference_count: 42,
      anomaly_rate: 0.1,
      active: true,
      activate_capable: true,
      source: 'registry' as const
    }
  ]
};

describe('ModelsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchModels.mockResolvedValue(baseModelsPayload);
    mockFetchModelMetrics.mockResolvedValue({
      model_version: '20260301000000',
      anomaly_hit_rate: 0.1,
      total_inferences: 42,
      inference_latency_ms: { p50: 12, p95: 45 },
      threshold_evolution: [],
      latest_training_summary: null
    });
    mockFetchTrainingRuns.mockResolvedValue([]);
    mockTrainModel.mockResolvedValue({
      run_id: '11111111-1111-1111-1111-111111111111',
      status: 'success',
      model_name: 'risk_autoencoder',
      model_version: '20260301112233',
      feature_dim: 8,
      threshold: 0.9,
      training_source: 'historical_events',
      sample_count: 80,
      auto_activated: false,
      metrics: {}
    });
    mockActivateModel.mockResolvedValue({
      model_name: 'risk_autoencoder',
      model_version: '20260301112233',
      feature_dim: 8,
      threshold: 0.9
    });
  });

  it('renders loading and then success state for models registry', async () => {
    renderPage();
    expect(screen.getByText('Loading model registry...')).toBeInTheDocument();
    await screen.findByText('Model registry');
    await screen.findByText('risk_autoencoder');
    expect(screen.getByText('active risk_autoencoder:20260301000000')).toBeInTheDocument();
  });

  it('renders error state when models query fails', async () => {
    mockFetchModels.mockRejectedValueOnce(new Error('boom'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Unable to load model registry\./)).toBeInTheDocument();
    });
  });

  it('disables activate button for inference-only models', async () => {
    mockFetchModels.mockResolvedValueOnce({
      active_model: null,
      items: [
        {
          model_name: 'risk_autoencoder',
          model_version: '20260225000000',
          threshold: 0.9,
          updated_at: '2026-03-01T10:00:00Z',
          inference_count: 22,
          anomaly_rate: 0,
          active: false,
          activate_capable: false,
          source: 'inference_only'
        }
      ]
    });
    renderPage();
    const activateButton = await screen.findByRole('button', { name: 'Activate' });
    expect(activateButton).toBeDisabled();
  });

  it('shows training success notice after train action', async () => {
    renderPage();
    const trainButton = await screen.findByRole('button', { name: 'Train model' });
    fireEvent.click(trainButton);
    await waitFor(() => {
      expect(screen.getByText(/Training run 11111111-1111-1111-1111-111111111111 completed/)).toBeInTheDocument();
    });
  });
});
