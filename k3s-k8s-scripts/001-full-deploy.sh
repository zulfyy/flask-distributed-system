#!/usr/bin/env bash
# 001-full-deploy.sh
# Full deploy akarstack: operator (cert-manager, CNPG, Dragonfly) + doppler token + semua manifest app.
# Jalankan dari folder yang sama dengan file 00-...yaml s/d 09-...yaml.
set -euo pipefail

NS=akarstack

# ============================================================
# WAJIB set via env var, jangan hardcode token di script ini:
#   DOPPLER_TOKEN=dp.st.xxxxxxx ./001-full-deploy.sh
# ============================================================
if [ -z "${DOPPLER_TOKEN:-}" ]; then
  echo "!! ERROR: env var DOPPLER_TOKEN belum di-set."
  echo "   Jalankan seperti ini:"
  echo "   DOPPLER_TOKEN='dp.st.xxxxxxx' ./001-full-deploy.sh"
  exit 1
fi

wait_secret () {
  local secret=$1
  local timeout=${2:-120}
  echo "   Menunggu secret '$secret' di namespace $NS (timeout ${timeout}s)..."
  local elapsed=0
  until kubectl get secret "$secret" -n "$NS" >/dev/null 2>&1; do
    sleep 3
    elapsed=$((elapsed+3))
    if [ "$elapsed" -ge "$timeout" ]; then
      echo "   !! Timeout menunggu secret '$secret'."
      return 1
    fi
  done
  echo "   OK, secret '$secret' sudah ada."
}

# ---------------------------------------------------------------
echo "=== [1/14] cert-manager ==="
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
echo "   Menunggu cert-manager siap..."
kubectl wait --namespace cert-manager --for=condition=Available deployment --all --timeout=180s

echo "=== [2/14] CloudNativePG operator ==="
kubectl apply --server-side -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.24/releases/cnpg-1.24.1.yaml
echo "   Menunggu CNPG operator siap..."
kubectl wait --namespace cnpg-system --for=condition=Available deployment --all --timeout=180s || true

echo "=== [3/14] Dragonfly operator ==="
kubectl apply -f https://raw.githubusercontent.com/dragonflydb/dragonfly-operator/main/manifests/dragonfly-operator.yaml

echo "=== [4/14] Doppler Kubernetes Operator ==="
kubectl apply -f https://github.com/DopplerHQ/kubernetes-operator/releases/latest/download/recommended.yaml
echo "   Menunggu Doppler operator siap..."
kubectl wait --namespace doppler-operator-system --for=condition=Available deployment --all --timeout=180s || true

echo "=== [5/14] Namespace akarstack ==="
kubectl apply -f 00-namespace.yaml

echo "=== [6/14] Doppler service token secret ==="
kubectl create secret generic doppler-app-token-secret \
  --namespace "$NS" \
  --from-literal=serviceToken="$DOPPLER_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "=== [7/14] DopplerSecret (app-env & pg-app-credentials) ==="
kubectl apply -f 02-doppler-secret-fix.yaml
wait_secret akarstack-app-env
wait_secret akarstack-pg-app-credentials

echo "=== [8/14] Storage (PV/PVC uploads & results) ==="
kubectl apply -f 03-storage.yaml

echo "=== [9/14] CloudNativePG Cluster ==="
# PERHATIAN: cluster ini butuh secret 'akarstack-pg-superuser' juga.
# Pastikan itu sudah dibuat (via Doppler processor tambahan atau manual) sebelum lanjut.
wait_secret akarstack-pg-superuser 30 || echo "   -> lanjut apply, tapi cluster kemungkinan Pending sampai secret ini ada."
kubectl apply -f 04-cloudnativepg-cluster.yaml

echo "=== [10/14] Dragonfly cache ==="
kubectl apply -f 05-dragonfly.yaml

echo "=== [11/14] cert-manager ClusterIssuer + Certificate ==="
kubectl apply -f 08-clusterissuer.yaml

echo "=== [12/14] Deployments ==="
kubectl apply -f 06-deployments.yaml

echo "=== [13/14] Services ==="
kubectl apply -f 07-services.yaml

echo "=== [14/14] IngressRoute ==="
kubectl apply -f 09-ingressroute.yaml

echo ""
echo "=== SELESAI! Cek status: ==="
echo "kubectl get pods -n $NS"
echo "kubectl get cluster -n $NS"
echo "kubectl get certificate -n $NS"
echo "kubectl get dragonfly -n $NS"