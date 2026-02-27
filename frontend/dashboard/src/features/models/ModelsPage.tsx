import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { useAuth } from '../../app/state/auth-context';
import { fetchModelMetrics, fetchModels, trainModel, activateModel } from '../../shared/api/models';
import { formatDateTime } from '../../shared/lib/time';
import { Badge } from '../../shared/ui/badge';
import { Button } from '../../shared/ui/button';
import { Card } from '../../shared/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../../shared/ui/dialog';
import { Input } from '../../shared/ui/input';

export function ModelsPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();

  const [selectedVersion, setSelectedVersion] = useState<string>('');
  const [activateTarget, setActivateTarget] = useState<{ modelName: string; modelVersion: string } | null>(null);
  const [modelName, setModelName] = useState('risk_autoencoder');
  const [sampleCount, setSampleCount] = useState(256);
  const [epochs, setEpochs] = useState(12);
  const [batchSize, setBatchSize] = useState(32);
  const [notice, setNotice] = useState<string | null>(null);

  const modelsQuery = useQuery({
    queryKey: ['models'],
    queryFn: async () => fetchModels(token!),
    enabled: Boolean(token)
  });

  const metricsQuery = useQuery({
    queryKey: ['model-metrics', selectedVersion],
    queryFn: async () => fetchModelMetrics(token!, selectedVersion),
    enabled: Boolean(token && selectedVersion)
  });

  const trainMutation = useMutation({
    mutationFn: async () =>
      trainModel(token!, {
        model_name: modelName,
        sample_count: sampleCount,
        epochs,
        batch_size: batchSize
      }),
    onSuccess: (result) => {
      setNotice(`Trained ${result.model_name}:${result.model_version}`);
      queryClient.invalidateQueries({ queryKey: ['models'] });
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

  return (
    <section className="stack-lg">
      <Card>
        <div className="panel-header">
          <h2>Model Registry</h2>
          {modelsQuery.data?.active_model?.model_version ? (
            <Badge variant="success">
              active {modelsQuery.data.active_model.model_name}:{modelsQuery.data.active_model.model_version}
            </Badge>
          ) : (
            <Badge variant="warning">active model unavailable</Badge>
          )}
        </div>

        {notice && <p className="inline-success">{notice}</p>}

        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Version</th>
                <th>Threshold</th>
                <th>Anomaly hit rate</th>
                <th>Inference volume</th>
                <th>Updated</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {(modelsQuery.data?.items ?? []).map((item) => (
                <tr key={`${item.model_name}:${item.model_version}`}>
                  <td>{item.model_name}</td>
                  <td className="mono">{item.model_version}</td>
                  <td>{item.threshold.toFixed(4)}</td>
                  <td>{(item.anomaly_rate * 100).toFixed(2)}%</td>
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
                        disabled={item.active}
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
      </Card>

      <div className="grid-two">
        <Card>
          <h3>Train Model</h3>
          <div className="stack-sm">
            <Input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="Model name" />
            <Input
              type="number"
              value={sampleCount}
              onChange={(event) => setSampleCount(Number(event.target.value))}
              placeholder="Sample count"
            />
            <Input type="number" value={epochs} onChange={(event) => setEpochs(Number(event.target.value))} placeholder="Epochs" />
            <Input
              type="number"
              value={batchSize}
              onChange={(event) => setBatchSize(Number(event.target.value))}
              placeholder="Batch size"
            />
            <Button variant="primary" onClick={() => trainMutation.mutate()} disabled={trainMutation.isPending}>
              {trainMutation.isPending ? 'Training...' : 'Train model'}
            </Button>
          </div>
        </Card>

        <Card>
          <h3>Model Metrics</h3>
          {!selectedVersion && <p className="muted">Select a model version to view metrics.</p>}
          {selectedVersion && metricsQuery.isLoading && <p className="muted">Loading metrics...</p>}

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
                  <Tooltip />
                  <Line dataKey="threshold" stroke="var(--accent)" dot={false} />
                  <Line dataKey="score" stroke="var(--status-warning)" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </>
          )}
        </Card>
      </div>

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
    </section>
  );
}
