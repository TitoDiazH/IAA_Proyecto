#!/bin/bash
set -e

echo "=== Testing Real Ollama Setup ==="

# Wait for model to be available
echo "Step 1: Waiting for Ollama model..."
for i in {1..30}; do
  MODELS=$(docker compose exec -T ollama ollama list 2>/dev/null | grep qwen2.5:14b || echo "")
  if [ ! -z "$MODELS" ]; then
    echo "✓ Model qwen2.5:14b is available"
    break
  fi
  echo "  Attempt $i/30: Model not ready yet..."
  sleep 10
done

# Test backend connectivity to Ollama
echo ""
echo "Step 2: Testing backend → Ollama connectivity..."
docker compose exec -T backend python -c "
import httpx
r = httpx.get('http://ollama:11434/api/tags', timeout=10)
models = r.json().get('models', [])
print(f'Status: {r.status_code}')
print(f'Available models: {len(models)}')
if models:
    for m in models:
        print(f'  - {m.get(\"name\", \"unknown\")}')
"

# Test simple completion
echo ""
echo "Step 3: Testing simple chat completion..."
docker compose exec -T backend python -c "
import httpx, json
payload = {
    'model': 'qwen2.5:14b',
    'messages': [{'role': 'user', 'content': 'Hola, di hola'}],
    'stream': False
}
r = httpx.post('http://ollama:11434/api/chat', json=payload, timeout=30)
print(f'Status: {r.status_code}')
result = r.json()
if 'message' in result:
    print(f'Response: {result[\"message\"][\"content\"][:100]}...')
else:
    print(f'Response: {result}')
"

# Test JSON completion with schema
echo ""
echo "Step 4: Testing JSON completion with schema..."
docker compose exec -T backend python -c "
import httpx, json
schema = {
    'type': 'object',
    'properties': {
        'greeting': {'type': 'string'},
        'count': {'type': 'integer'}
    }
}
payload = {
    'model': 'qwen2.5:14b',
    'messages': [{'role': 'user', 'content': 'Respond with greeting=hello and count=3'}],
    'stream': False,
    'format': schema
}
r = httpx.post('http://ollama:11434/api/chat', json=payload, timeout=30)
print(f'Status: {r.status_code}')
result = r.json()
content = result['message']['content']
print(f'Content: {content[:200]}')
"

echo ""
echo "=== All tests passed! ==="
