# MentorBot on Kubernetes

## Build the image

### Option A: local kind/minikube (no registry)

Build locally:

```bash
docker build -t mentorbot:local .
```

Then load the image into your cluster:

- kind:

```bash
kind load docker-image mentorbot:local
```

- minikube:

```bash
minikube image load mentorbot:local
```

### Option B: push to a registry (recommended)

```bash
export IMAGE="shrikantnangare/mentorbot:0.1.0"
docker build -t "$IMAGE" .
docker push "$IMAGE"
```

Then update `k8s/deployment.yaml` `spec.template.spec.containers[0].image` to match.

## Deploy

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

Optional ingress:

```bash
kubectl apply -f k8s/ingress.yaml
```

## Deploy with Argo CD

1) Commit/push this repo to Git (Argo CD must be able to read it).

2) Edit `argocd/mentorbot-application.yaml` and set:
- `spec.source.repoURL` to your git repo URL
- `spec.source.targetRevision` if not `main`

3) Apply the Argo CD Application:

```bash
kubectl apply -f argocd/mentorbot-application.yaml
```

Argo CD will then sync the `k8s/` directory via Kustomize (`k8s/kustomization.yaml`).

## Verify

```bash
kubectl -n mentorbot get pods,svc,ingress
kubectl -n mentorbot logs deploy/mentorbot -f
```

Port-forward (quick local test):

```bash
kubectl -n mentorbot port-forward svc/mentorbot 8000:80
```

Open:

- `http://localhost:8000/`
- `http://localhost:8000/health`

## Configuration

Edit `k8s/configmap.yaml`:

- `MENTORBOT_LLM_API_STYLE`: set to `openai-completions` for llama.cpp `/v1/completions`
- `MENTORBOT_LLM_BASE_URL`: e.g. `http://192.168.1.215:8080`
- `MENTORBOT_LLM_MODEL`: must match one of `GET /v1/models`
- `MENTORBOT_LLM_TIMEOUT_S`: increase if the model is slow
- `MENTORBOT_DB_DIR`: keep as `/app/db` (PVC mount)

