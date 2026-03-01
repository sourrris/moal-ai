# EKS Manifests

This directory contains Kustomize manifests for backend deployments, IRSA service accounts, and AWS Secrets Manager sync via External Secrets Operator.

## Layout

- `base/`: namespace, service accounts, External Secrets resources, and backend Deployments.
- `overlays/staging`: staging-specific IAM role ARNs and secret path.
- `overlays/prod`: production-specific IAM role ARNs and secret path.

## Prerequisites

1. External Secrets Operator installed in the cluster.
2. IAM roles created for each service account in the overlay.
3. AWS Secrets Manager secret values populated under:
   - `/aegis/staging/backend`
   - `/aegis/prod/backend`

Required secret keys should include at minimum:
- `DATABASE_URL`
- `REDIS_URL`
- `RABBITMQ_URL`
- `JWT_ALGORITHM`
- `JWT_SECRET` (for HS256 mode)
- `JWT_REFRESH_SECRET` (for HS256 mode)
- `JWT_PRIVATE_KEY_PEM` and `JWT_PUBLIC_KEY_PEM` (for RS256 mode)
- `JWT_KEY_ID`

## Apply

```bash
kubectl apply -k infra/eks/overlays/staging
kubectl apply -k infra/eks/overlays/prod
```
