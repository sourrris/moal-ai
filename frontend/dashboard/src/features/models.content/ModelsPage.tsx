import { useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';

import { useAuth } from '../../app/state/auth-context';
import {
  activateModel,
  fetchActiveMLModel,
  fetchMLModels,
  fetchTrainingRuns,
  trainFromHistory
} from '../../shared/api/models';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { Input } from '../../shared/ui/input';
import { KpiCard } from '../../shared/ui/KpiCard';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

const CHART_COLORS = {
  ink: '#000000',
  inkSoft: '#777169',
  critical: '#9c4139',
  success: '#2f7f56',
  grid: '#e5e5e5'
};

function formatDateTime(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${(seconds / 60).toFixed(1)}m`;
}

export function ModelsPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();

  // Training form state
  const [lookbackHours, setLookbackHours] = useState(24);
  const [maxSamples, setMaxSamples] = useState(2048);
  const [epochs, setEpochs] = useState(12);
  const [batchSize, setBatchSize] = useState(32);
  const [thresholdQuantile, setThresholdQuantile] = useState(0.99);
  const [autoActivate, setAutoActivate] = useState(true);

  const modelsQuery = useQuery({
    queryKey: ['ml-models'],
    queryFn: async () => fetchMLModels(token!),
    enabled: Boolean(token),
    refetchInterval: 15_000
  });

  const activeQuery = useQuery({
    queryKey: ['ml-active'],
    queryFn: async () => fetchActiveMLModel(token!),
    enabled: Boolean(token),
    refetchInterval: 15_000
  });

  const runsQuery = useQuery({
    queryKey: ['training-runs'],
    queryFn: async () => fetchTrainingRuns(token!, 20),
    enabled: Boolean(token),
    refetchInterval: 10_000
  });

  const trainMutation = useMutation({
    mutationFn: async () =>
      trainFromHistory(token!, {
        lookback_hours: lookbackHours,
        max_samples: maxSamples,
        epochs,
        batch_size: batchSize,
        threshold_quantile: thresholdQuantile,
        auto_activate: autoActivate
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-models'] });
      queryClient.invalidateQueries({ queryKey: ['ml-active'] });
      queryClient.invalidateQueries({ queryKey: ['training-runs'] });
    }
  });

  const activateMutation = useMutation({
    mutationFn: async ({ name, version }: { name: string; version: string }) =>
      activateModel(token!, name, version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-models'] });
      queryClient.invalidateQueries({ queryKey: ['ml-active'] });
    }
  });

  const models = modelsQuery.data ?? [];
  const active = activeQuery.data;
  const runs = runsQuery.data ?? [];
  const lastCompleted = runs.find((r) => r.status === 'completed');

  // Build reconstruction error chart from last completed run
  const reconQuantiles = lastCompleted?.metrics?.reconstruction_error_quantiles;
  const reconData = reconQuantiles
    ? [
        { name: 'p50', value: reconQuantiles.p50 },
        { name: 'p90', value: reconQuantiles.p90 },
        { name: 'p95', value: reconQuantiles.p95 },
        { name: 'p99', value: reconQuantiles.p99 }
      ]
    : [];

  return (
    <DashboardPageFrame
      eyebrow="ML Operations"
      title="Models"
      subtitle="Train new autoencoder models, view training history, and manage the active model for inference."
      chips={
        <div className="inline-actions">
          {active && (
            <Badge variant="success">
              Active: {active.model_name} v{active.model_version}
            </Badge>
          )}
          <Badge variant="neutral">{models.length} models</Badge>
        </div>
      }
    >
      {/* Active model KPIs */}
      {active && (
        <div className="kpi-grid">
          <KpiCard label="Active model" value={active.model_version} meta={active.model_name} />
          <KpiCard label="Feature dim" value={String(active.feature_dim)} meta="input dimensions" />
          <KpiCard label="Threshold" value={active.threshold.toFixed(4)} meta="anomaly cutoff" />
          <KpiCard
            label="Training runs"
            value={String(runs.length)}
            meta={runs.filter((r) => r.status === 'completed').length + ' completed'}
          />
          {lastCompleted?.metrics?.duration_seconds && (
            <KpiCard
              label="Last train time"
              value={formatDuration(lastCompleted.metrics.duration_seconds)}
              meta={`${lastCompleted.metrics.sample_count ?? '?'} samples`}
            />
          )}
        </div>
      )}

      <div className="dashboard-grid">
        {/* Train new model */}
        <Card className="stack-md">
          <div className="panel-copy">
            <span className="panel-kicker">Train</span>
            <h2 className="panel-title">Train new model</h2>
            <p className="panel-summary">
              Train an autoencoder on historical event features stored in the database.
              The model will learn the normal behavior patterns and set a new anomaly threshold.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="stack-sm">
              <span>Lookback hours</span>
              <Input type="number" value={lookbackHours} onChange={(e) => setLookbackHours(Number(e.target.value))} min={1} max={720} />
            </label>
            <label className="stack-sm">
              <span>Max samples</span>
              <Input type="number" value={maxSamples} onChange={(e) => setMaxSamples(Number(e.target.value))} min={64} max={20000} />
            </label>
            <label className="stack-sm">
              <span>Epochs</span>
              <Input type="number" value={epochs} onChange={(e) => setEpochs(Number(e.target.value))} min={1} max={500} />
            </label>
            <label className="stack-sm">
              <span>Batch size</span>
              <Input type="number" value={batchSize} onChange={(e) => setBatchSize(Number(e.target.value))} min={1} max={2048} />
            </label>
            <label className="stack-sm">
              <span>Threshold quantile</span>
              <Input type="number" value={thresholdQuantile} onChange={(e) => setThresholdQuantile(Number(e.target.value))} min={0.5} max={0.9999} step={0.01} />
            </label>
            <label className="stack-sm flex items-end">
              <label className="flex items-center gap-2 text-[0.95rem] text-ink">
                <input type="checkbox" checked={autoActivate} onChange={(e) => setAutoActivate(e.target.checked)} />
                Auto-activate after training
              </label>
            </label>
          </div>

          <div className="inline-actions">
            <Button
              variant="warm"
              onClick={() => trainMutation.mutate()}
              disabled={trainMutation.isPending}
            >
              {trainMutation.isPending ? 'Training...' : 'Start training'}
            </Button>
          </div>

          {trainMutation.isError && (
            <p className="inline-error">
              Training failed: {(trainMutation.error as Error).message}
            </p>
          )}

          {trainMutation.isSuccess && trainMutation.data && (
            <div className="inline-success">
              Model trained successfully: v{trainMutation.data.model_version}
              {' '}&middot; {trainMutation.data.sample_count} samples
              {' '}&middot; threshold {trainMutation.data.threshold.toFixed(4)}
              {trainMutation.data.auto_activated && ' (auto-activated)'}
            </div>
          )}
        </Card>

        {/* Reconstruction error distribution */}
        <Card className="stack-md">
          <div className="panel-copy">
            <span className="panel-kicker">Model performance</span>
            <h2 className="panel-title">Reconstruction error</h2>
            <p className="panel-summary">
              Validation reconstruction error percentiles from the most recent completed training run.
              The p99 value becomes the anomaly threshold.
            </p>
          </div>

          {reconData.length > 0 ? (
            <div style={{ width: '100%', height: 200 }}>
              <ResponsiveContainer>
                <BarChart data={reconData} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
                  <XAxis dataKey="name" tick={{ fontSize: 12, fill: CHART_COLORS.ink }} stroke={CHART_COLORS.grid} />
                  <YAxis tick={{ fontSize: 11, fill: CHART_COLORS.inkSoft }} stroke={CHART_COLORS.grid} tickFormatter={(v: number) => v.toFixed(3)} />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null;
                      return (
                        <div className="rounded-panel border border-black/5 bg-white px-3 py-2 text-[0.82rem] shadow-outline">
                          <p className="text-ink-soft">{label}</p>
                          <p className="font-medium text-ink">{(payload[0].value as number).toFixed(6)}</p>
                        </div>
                      );
                    }}
                  />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]} barSize={40} fill={CHART_COLORS.ink} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="empty-state">No completed training runs yet.</div>
          )}

          {lastCompleted && (
            <div className="dashboard-note-list">
              <article className="dashboard-note">
                <span className="dashboard-note-label">Train loss</span>
                <span className="dashboard-note-value">{lastCompleted.metrics.train_loss?.toFixed(6) ?? 'n/a'}</span>
              </article>
              <article className="dashboard-note">
                <span className="dashboard-note-label">Val loss</span>
                <span className="dashboard-note-value">{lastCompleted.metrics.val_loss?.toFixed(6) ?? 'n/a'}</span>
              </article>
            </div>
          )}
        </Card>
      </div>

      {/* Model registry */}
      <Card className="stack-md">
        <div className="panel-header">
          <div className="panel-copy">
            <span className="panel-kicker">Registry</span>
            <h2 className="panel-title">Model versions</h2>
            <p className="panel-summary">All trained model versions. Click activate to switch the inference model.</p>
          </div>
        </div>

        {modelsQuery.isLoading ? (
          <p className="muted">Loading models...</p>
        ) : modelsQuery.isError ? (
          <p className="inline-error">Unable to load models from ML service.</p>
        ) : models.length === 0 ? (
          <div className="empty-state">No models registered. Train one to get started.</div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead className="sticky-table-head">
                <tr>
                  <th>Model</th>
                  <th>Version</th>
                  <th>Features</th>
                  <th>Threshold</th>
                  <th>Updated</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {models.map((model) => {
                  const isActive = active?.model_name === model.model_name && active?.model_version === model.model_version;
                  return (
                    <tr className="interactive-row" key={`${model.model_name}:${model.model_version}`}>
                      <td className="font-medium text-ink">{model.model_name}</td>
                      <td className="font-mono text-[0.88rem]">{model.model_version}</td>
                      <td>{model.feature_dim}</td>
                      <td className="tabular-nums">{model.threshold.toFixed(4)}</td>
                      <td>{formatDateTime(model.updated_at)}</td>
                      <td>
                        <Badge variant={isActive ? 'success' : 'neutral'}>
                          {isActive ? 'active' : 'inactive'}
                        </Badge>
                      </td>
                      <td>
                        {!isActive && (
                          <Button
                            variant="secondary"
                            onClick={() =>
                              activateMutation.mutate({ name: model.model_name, version: model.model_version })
                            }
                            disabled={activateMutation.isPending}
                          >
                            Activate
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Training runs history */}
      <Card className="stack-md">
        <div className="panel-header">
          <div className="panel-copy">
            <span className="panel-kicker">History</span>
            <h2 className="panel-title">Training runs</h2>
            <p className="panel-summary">Audit trail of model training jobs with parameters and metrics.</p>
          </div>
        </div>

        {runsQuery.isLoading ? (
          <p className="muted">Loading training runs...</p>
        ) : runs.length === 0 ? (
          <div className="empty-state">No training runs recorded yet.</div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead className="sticky-table-head">
                <tr>
                  <th>Started</th>
                  <th>Model</th>
                  <th>Version</th>
                  <th>Status</th>
                  <th>Samples</th>
                  <th>Epochs</th>
                  <th>Threshold</th>
                  <th>Duration</th>
                  <th>By</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr className="interactive-row" key={run.run_id}>
                    <td>{formatDateTime(run.started_at)}</td>
                    <td className="font-medium text-ink">{run.model_name}</td>
                    <td className="font-mono text-[0.88rem]">{run.model_version ?? '--'}</td>
                    <td>
                      <Badge
                        variant={
                          run.status === 'completed' ? 'success' : run.status === 'failed' ? 'critical' : 'warning'
                        }
                      >
                        {run.status}
                      </Badge>
                    </td>
                    <td>{run.parameters.sample_count ?? run.metrics.sample_count ?? '--'}</td>
                    <td>{run.parameters.epochs ?? '--'}</td>
                    <td className="tabular-nums">
                      {run.metrics.threshold != null ? Number(run.metrics.threshold).toFixed(4) : '--'}
                    </td>
                    <td>
                      {run.metrics.duration_seconds != null ? formatDuration(run.metrics.duration_seconds) : '--'}
                    </td>
                    <td>{run.initiated_by ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </DashboardPageFrame>
  );
}
