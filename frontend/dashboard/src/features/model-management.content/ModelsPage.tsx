import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { useAuth } from '../../app/state/auth-context';
import { fetchActiveModel, fetchModels, fetchTrainingRuns, trainModel } from '../../shared/api/models';
import { formatDateTime } from '../../shared/lib/time';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { DataPanel } from '../../shared/ui/DataPanel';
import { Input } from '../../shared/ui/input';
import { KpiCard } from '../../shared/ui/KpiCard';
import { DashboardPageFrame } from '../../widgets/layout/DashboardPageFrame';

export function ModelsPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();

  const [modelName, setModelName] = useState('behavior_autoencoder');
  const [lookbackHours, setLookbackHours] = useState(24);
  const [epochs, setEpochs] = useState(12);
  const [batchSize, setBatchSize] = useState(32);
  const [thresholdQuantile, setThresholdQuantile] = useState(0.99);
  const [notice, setNotice] = useState<string | null>(null);

  const modelsQuery = useQuery({
    queryKey: ['models'],
    queryFn: async () => fetchModels(token!),
    enabled: Boolean(token)
  });

  const activeModelQuery = useQuery({
    queryKey: ['active-model'],
    queryFn: async () => fetchActiveModel(token!),
    enabled: Boolean(token),
    retry: false
  });

  const trainingRunsQuery = useQuery({
    queryKey: ['training-runs'],
    queryFn: async () => fetchTrainingRuns(token!),
    enabled: Boolean(token)
  });

  const trainMutation = useMutation({
    mutationFn: async () =>
      trainModel(token!, {
        model_name: modelName,
        lookback_hours: lookbackHours,
        epochs,
        batch_size: batchSize,
        threshold_quantile: thresholdQuantile
      }),
    onSuccess: (result) => {
      setNotice(`Training run ${result.run_id} completed (${result.sample_count} samples)`);
      queryClient.invalidateQueries({ queryKey: ['models'] });
      queryClient.invalidateQueries({ queryKey: ['training-runs'] });
      queryClient.invalidateQueries({ queryKey: ['active-model'] });
    },
    onError: (error) => {
      setNotice(`Training failed: ${(error as Error).message}`);
    }
  });

  const modelItems = modelsQuery.data?.items ?? [];
  const trainingRuns = trainingRunsQuery.data?.items ?? [];
  const activeModel = activeModelQuery.data;

  return (
    <DashboardPageFrame
      chips={
        activeModel
          ? <Badge variant="success">active {activeModel.model_name}:{activeModel.model_version}</Badge>
          : <Badge variant="warning">no active model</Badge>
      }
    >
      <div className="kpi-grid">
        <KpiCard
          label="Active version"
          value={activeModel?.model_version ?? 'n/a'}
          meta="serving model"
        />
        <KpiCard
          label="Registered models"
          value={String(modelItems.length)}
          meta="in registry"
        />
        <KpiCard
          label="Feature dim"
          value={activeModel ? String(activeModel.feature_dim) : 'n/a'}
          meta="input features"
        />
        <KpiCard
          label="Threshold"
          value={activeModel ? activeModel.threshold.toFixed(4) : 'n/a'}
          meta="anomaly cutoff"
        />
      </div>

      <DataPanel title="Model registry" description="Registered model versions and their status.">
        {modelsQuery.isLoading && <p className="muted">Loading model registry...</p>}
        {modelsQuery.isError && <p className="inline-error">Unable to load model registry.</p>}

        {!modelsQuery.isLoading && !modelsQuery.isError && (
          <div className="table-wrap">
            <table className="data-table">
              <thead className="sticky-table-head">
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Version</th>
                  <th scope="col">Feature dim</th>
                  <th scope="col">Threshold</th>
                  <th scope="col">Status</th>
                  <th scope="col">Created</th>
                </tr>
              </thead>
              <tbody>
                {modelItems.map((item) => (
                  <tr key={`${item.model_name}:${item.model_version}`} className="interactive-row">
                    <td>{item.model_name}</td>
                    <td className="mono">{item.model_version}</td>
                    <td>{item.feature_dim}</td>
                    <td>{item.threshold.toFixed(4)}</td>
                    <td>
                      <Badge variant={item.status === 'active' ? 'success' : 'neutral'}>{item.status}</Badge>
                    </td>
                    <td>{formatDateTime(item.created_at, 'local')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataPanel>

      <div className="grid-two">
        <DataPanel title="Train model" description="Trigger server-side training from historical behavior events.">
          {notice && <p className="inline-success">{notice}</p>}
          <div className="stack-sm">
            <Input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="Model name" />
            <Input type="number" value={lookbackHours} onChange={(event) => setLookbackHours(Number(event.target.value))} placeholder="Lookback hours" />
            <Input type="number" value={epochs} onChange={(event) => setEpochs(Number(event.target.value))} placeholder="Epochs" />
            <Input type="number" value={batchSize} onChange={(event) => setBatchSize(Number(event.target.value))} placeholder="Batch size" />
            <Input type="number" step="0.001" min="0.5" max="0.999" value={thresholdQuantile} onChange={(event) => setThresholdQuantile(Number(event.target.value))} placeholder="Threshold quantile" />
            <Button variant="primary" onClick={() => trainMutation.mutate()} disabled={trainMutation.isPending}>
              {trainMutation.isPending ? 'Training...' : 'Train model'}
            </Button>
          </div>
        </DataPanel>

        <DataPanel title="Training history" description="Recent training runs and outcomes.">
          {trainingRunsQuery.isLoading && <p className="muted">Loading training history...</p>}
          {trainingRunsQuery.isError && <p className="inline-error">Unable to load training history.</p>}

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
                  </tr>
                </thead>
                <tbody>
                  {trainingRuns.map((run) => (
                    <tr key={run.run_id} className="interactive-row">
                      <td className="mono">{run.run_id.slice(0, 8)}</td>
                      <td>
                        <Badge
                          variant={
                            run.status === 'success' ? 'success'
                              : run.status === 'failed' ? 'critical'
                              : run.status === 'running' ? 'info'
                              : 'neutral'
                          }
                        >
                          {run.status}
                        </Badge>
                      </td>
                      <td className="mono">{run.model_version ?? '-'}</td>
                      <td>{run.sample_count ?? '-'}</td>
                      <td>{run.val_loss != null ? run.val_loss.toFixed(6) : '-'}</td>
                      <td>{formatDateTime(run.started_at, 'local')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataPanel>
      </div>
    </DashboardPageFrame>
  );
}
