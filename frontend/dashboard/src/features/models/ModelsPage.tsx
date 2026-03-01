import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { useAuth } from '../../app/state/auth-context';
import { useUI } from '../../app/state/ui-context';
import { activateModel, fetchModelMetrics, fetchModels, fetchTrainingRuns, trainModel } from '../../shared/api/models';
import { formatDateTime } from '../../shared/lib/time';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { DataPanel } from '../../shared/ui/DataPanel';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../../shared/ui/dialog';
import { Input } from '../../shared/ui/input';
import { KpiCard } from '../../shared/ui/KpiCard';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

function renderBadge(modelsLoading: boolean, modelsError: boolean, activeLabel: string | null) {
  if (modelsLoading) {
    return <Badge variant="neutral">loading model status</Badge>;
  }
  if (modelsError) {
    return <Badge variant="critical">model status unavailable</Badge>;
  }
  if (activeLabel) {
    return <Badge variant="success">active {activeLabel}</Badge>;
  }
  return <Badge variant="warning">no active model configured</Badge>;
}

export function ModelsPage() {
  const { token } = useAuth();
  const { tenant } = useUI();
  const queryClient = useQueryClient();

  const [selectedVersion, setSelectedVersion] = useState<string>('');
  const [activateTarget, setActivateTarget] = useState<{ modelName: string; modelVersion: string } | null>(null);
  const [modelName, setModelName] = useState('risk_autoencoder');
  const [lookbackHours, setLookbackHours] = useState(24);
  const [maxSamples, setMaxSamples] = useState(2048);
  const [minSamples, setMinSamples] = useState(64);
  const [epochs, setEpochs] = useState(12);
  const [batchSize, setBatchSize] = useState(32);
  const [thresholdQuantile, setThresholdQuantile] = useState(0.99);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastTrainSummary, setLastTrainSummary] = useState<{
    candidateVersion: string;
    activeVersion: string | null;
    thresholdDelta: number | null;
  } | null>(null);

  const modelsQuery = useQuery({
    queryKey: ['models'],
    queryFn: async () => fetchModels(token!),
    enabled: Boolean(token)
  });

  const trainingRunsQuery = useQuery({
    queryKey: ['model-training-runs', modelName],
    queryFn: async () => fetchTrainingRuns(token!, modelName || undefined),
    enabled: Boolean(token)
  });

  useEffect(() => {
    const activeVersion = modelsQuery.data?.active_model?.model_version;
    const knownVersions = new Set((modelsQuery.data?.items ?? []).map((item) => item.model_version));
    if (!activeVersion && !selectedVersion) {
      return;
    }
    if (activeVersion && (!selectedVersion || !knownVersions.has(selectedVersion))) {
      setSelectedVersion(activeVersion);
    }
  }, [modelsQuery.data, selectedVersion]);

  const metricsQuery = useQuery({
    queryKey: ['model-metrics', selectedVersion],
    queryFn: async () => fetchModelMetrics(token!, selectedVersion),
    enabled: Boolean(token && selectedVersion)
  });

  const trainMutation = useMutation({
    mutationFn: async () =>
      trainModel(token!, {
        model_name: modelName,
        tenant_id: tenant === 'all' ? undefined : tenant,
        lookback_hours: lookbackHours,
        max_samples: maxSamples,
        min_samples: minSamples,
        epochs,
        batch_size: batchSize,
        threshold_quantile: thresholdQuantile,
        auto_activate: false
      }),
    onSuccess: (result) => {
      setNotice(
        `Training run ${result.run_id} completed for ${result.model_name}:${result.model_version ?? 'candidate'} (${result.sample_count} samples)`
      );
      const comparison =
        result.metrics && typeof result.metrics === 'object' ? (result.metrics.baseline_comparison as Record<string, unknown>) : null;
      setLastTrainSummary({
        candidateVersion: result.model_version ?? 'candidate',
        activeVersion: typeof comparison?.active_model_version === 'string' ? comparison.active_model_version : null,
        thresholdDelta: typeof comparison?.threshold_delta === 'number' ? comparison.threshold_delta : null
      });
      queryClient.invalidateQueries({ queryKey: ['models'] });
      queryClient.invalidateQueries({ queryKey: ['model-training-runs'] });
    },
    onError: (error) => {
      setNotice(`Training failed: ${(error as Error).message}`);
    }
  });

  const activateMutation = useMutation({
    mutationFn: async () => {
      if (!activateTarget) {
        throw new Error('No model selected');
      }
      return activateModel(token!, activateTarget.modelName, activateTarget.modelVersion);
    },
    onSuccess: (result) => {
      setNotice(`Activated ${result.model_name}:${result.model_version}`);
      setActivateTarget(null);
      queryClient.invalidateQueries({ queryKey: ['models'] });
      queryClient.invalidateQueries({ queryKey: ['model-metrics'] });
    },
    onError: (error) => {
      setNotice(`Activation failed: ${(error as Error).message}`);
    }
  });

  const metricsSeries = useMemo(
    () =>
      (metricsQuery.data?.threshold_evolution ?? []).map((item) => ({
        time: item.bucket,
        threshold: item.avg_threshold,
        score: item.avg_score
      })),
    [metricsQuery.data]
  );

  const modelItems = modelsQuery.data?.items ?? [];
  const totalInferences = modelItems.reduce((sum, item) => sum + (item.inference_count ?? 0), 0);
  const highestAnomalyRate = modelItems.reduce((max, item) => Math.max(max, item.anomaly_rate ?? 0), 0);
  const activeModelVersion = modelsQuery.data?.active_model?.model_version ?? 'n/a';
  const activeLabel = modelsQuery.data?.active_model
    ? `${modelsQuery.data.active_model.model_name}:${modelsQuery.data.active_model.model_version}`
    : null;

  return (
    <DashboardPageFrame chips={renderBadge(modelsQuery.isLoading, modelsQuery.isError, activeLabel)}>
      <div className="kpi-grid">
        <KpiCard label="Active version" value={activeModelVersion} meta="serving model" />
        <KpiCard label="Registered models" value={String(modelItems.length)} meta="registry size" />
        <KpiCard label="Inference volume" value={String(totalInferences)} meta="total processed" />
        <KpiCard label="Highest anomaly rate" value={`${(highestAnomalyRate * 100).toFixed(2)}%`} meta="across versions" />
      </div>

      <DataPanel title="Model registry" description="Serving versions, thresholds, hit rates, provenance, and activation actions.">
        {notice && <p className="inline-success">{notice}</p>}
        {modelsQuery.isLoading && <p className="muted">Loading model registry...</p>}
        {modelsQuery.isError && (
          <p className="inline-error">Unable to load model registry. {(modelsQuery.error as Error).message}</p>
        )}

        {!modelsQuery.isLoading && !modelsQuery.isError && (
          <div className="table-wrap">
            <table className="data-table">
              <thead className="sticky-table-head">
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Version</th>
                  <th scope="col">Source</th>
                  <th scope="col">Threshold</th>
                  <th scope="col">Anomaly hit rate</th>
                  <th scope="col">Inference volume</th>
                  <th scope="col">Updated</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {modelItems.map((item) => (
                  <tr key={`${item.model_name}:${item.model_version}`} className="interactive-row">
                    <td>{item.model_name}</td>
                    <td className="mono">{item.model_version}</td>
                    <td>
                      <Badge variant={item.source === 'registry' ? 'info' : 'neutral'}>{item.source}</Badge>
                    </td>
                    <td>{item.threshold != null ? item.threshold.toFixed(4) : '-'}</td>
                    <td>{item.anomaly_rate != null ? `${(item.anomaly_rate * 100).toFixed(2)}%` : '-'}</td>
                    <td>{item.inference_count}</td>
                    <td>{item.updated_at ? formatDateTime(item.updated_at, 'local') : '-'}</td>
                    <td>
                      <div className="inline-actions">
                        <Button variant="secondary" onClick={() => setSelectedVersion(item.model_version)}>
                          Metrics
                        </Button>
                        <Button
                          variant="primary"
                          onClick={() => setActivateTarget({ modelName: item.model_name, modelVersion: item.model_version })}
                          disabled={!item.activate_capable || item.active}
                          title={!item.activate_capable ? 'Historical inference-only model cannot be re-activated.' : undefined}
                        >
                          Activate
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataPanel>

      <div className="grid-two">
        <DataPanel
          title="Train model"
          description="Server-side training uses historical feature vectors. New models are saved as candidates and require manual activation."
        >
          <div className="stack-sm">
            <Input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="Model name" />
            <Input
              type="number"
              value={lookbackHours}
              onChange={(event) => setLookbackHours(Number(event.target.value))}
              placeholder="Lookback hours"
            />
            <Input
              type="number"
              value={maxSamples}
              onChange={(event) => setMaxSamples(Number(event.target.value))}
              placeholder="Max samples"
            />
            <Input
              type="number"
              value={minSamples}
              onChange={(event) => setMinSamples(Number(event.target.value))}
              placeholder="Minimum samples"
            />
            <Input type="number" value={epochs} onChange={(event) => setEpochs(Number(event.target.value))} placeholder="Epochs" />
            <Input
              type="number"
              value={batchSize}
              onChange={(event) => setBatchSize(Number(event.target.value))}
              placeholder="Batch size"
            />
            <Input
              type="number"
              step="0.001"
              min="0.5"
              max="0.999"
              value={thresholdQuantile}
              onChange={(event) => setThresholdQuantile(Number(event.target.value))}
              placeholder="Threshold quantile"
            />
            <p className="muted">
              Context: `lookback` and `max/min samples` control dataset size; `epochs` controls optimization passes; `batch size`
              controls update granularity; `threshold quantile` defines anomaly cutoff from reconstruction errors.
            </p>
            {lastTrainSummary && (
              <p className="muted">
                Candidate <strong>{lastTrainSummary.candidateVersion}</strong> compared to active{' '}
                <strong>{lastTrainSummary.activeVersion ?? 'n/a'}</strong>
                {lastTrainSummary.thresholdDelta != null && (
                  <>
                    {' '}
                    · threshold delta <strong>{lastTrainSummary.thresholdDelta.toFixed(6)}</strong>
                  </>
                )}
                .
              </p>
            )}
            <Button variant="primary" onClick={() => trainMutation.mutate()} disabled={trainMutation.isPending}>
              {trainMutation.isPending ? 'Training...' : 'Train model'}
            </Button>
          </div>
        </DataPanel>

        <DataPanel
          title="Model metrics"
          description="Inference-time score/threshold trend for the selected model version."
          badge={selectedVersion ? <Badge variant="info">{selectedVersion}</Badge> : undefined}
        >
          {!selectedVersion && <p className="muted">No model selected for metrics.</p>}
          {selectedVersion && metricsQuery.isLoading && <p className="muted">Loading metrics...</p>}
          {selectedVersion && metricsQuery.isError && (
            <p className="inline-error">Unable to load metrics. {(metricsQuery.error as Error).message}</p>
          )}

          {selectedVersion && metricsQuery.data && (
            <>
              <p>
                Version <strong>{metricsQuery.data.model_version}</strong> · anomaly hit rate{' '}
                <strong>{(metricsQuery.data.anomaly_hit_rate * 100).toFixed(2)}%</strong>
              </p>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={metricsSeries}>
                  <XAxis dataKey="time" hide />
                  <YAxis width={50} />
                  <Tooltip contentStyle={{ borderRadius: 12, borderColor: '#e4e4e7', fontSize: 12 }} />
                  <Line dataKey="threshold" stroke="var(--accent)" dot={false} />
                  <Line dataKey="score" stroke="var(--status-warning)" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </>
          )}
        </DataPanel>
      </div>

      <DataPanel title="Training history" description="Recent training runs, parameters, and resulting model/metric summaries.">
        {trainingRunsQuery.isLoading && <p className="muted">Loading training history...</p>}
        {trainingRunsQuery.isError && (
          <p className="inline-error">Unable to load training history. {(trainingRunsQuery.error as Error).message}</p>
        )}

        {trainingRunsQuery.data && (
          <div className="table-wrap">
            <table className="data-table">
              <thead className="sticky-table-head">
                <tr>
                  <th scope="col">Run</th>
                  <th scope="col">Status</th>
                  <th scope="col">Version</th>
                  <th scope="col">Samples</th>
                  <th scope="col">Val loss</th>
                  <th scope="col">Started</th>
                  <th scope="col">Finished</th>
                </tr>
              </thead>
              <tbody>
                {trainingRunsQuery.data.map((run) => {
                  const metrics = (run.metrics ?? {}) as Record<string, unknown>;
                  const parameters = (run.parameters ?? {}) as Record<string, unknown>;
                  const sampleCount =
                    typeof metrics.sample_count === 'number'
                      ? metrics.sample_count
                      : typeof parameters.effective_sample_count === 'number'
                        ? parameters.effective_sample_count
                        : '-';
                  const valLoss =
                    typeof metrics.val_loss === 'number'
                      ? Number(metrics.val_loss).toFixed(6)
                      : typeof metrics.train_loss === 'number'
                        ? Number(metrics.train_loss).toFixed(6)
                        : '-';

                  return (
                    <tr key={run.run_id} className="interactive-row">
                      <td className="mono">{run.run_id.slice(0, 8)}</td>
                      <td>
                        <Badge
                          variant={
                            run.status === 'success'
                              ? 'success'
                              : run.status === 'failed'
                                ? 'critical'
                                : run.status === 'running'
                                  ? 'info'
                                  : 'neutral'
                          }
                        >
                          {run.status}
                        </Badge>
                      </td>
                      <td className="mono">{run.model_version ?? '-'}</td>
                      <td>{String(sampleCount)}</td>
                      <td>{valLoss}</td>
                      <td>{formatDateTime(run.started_at, 'local')}</td>
                      <td>{run.finished_at ? formatDateTime(run.finished_at, 'local') : 'running'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </DataPanel>

      <Dialog open={Boolean(activateTarget)} onOpenChange={(open) => !open && setActivateTarget(null)}>
        <DialogContent>
          <DialogTitle>Confirm activation</DialogTitle>
          <DialogDescription>
            Activate {activateTarget?.modelName}:{activateTarget?.modelVersion} as the serving model.
          </DialogDescription>
          <div className="inline-actions">
            <Button onClick={() => setActivateTarget(null)}>Cancel</Button>
            <Button variant="primary" onClick={() => activateMutation.mutate()} disabled={activateMutation.isPending}>
              {activateMutation.isPending ? 'Activating...' : 'Confirm'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </DashboardPageFrame>
  );
}
