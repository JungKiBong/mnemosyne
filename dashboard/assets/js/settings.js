// dashboard/assets/js/settings.js
const PROVIDER_DEFAULTS = {
  ollama:   { url: 'http://localhost:11434/v1', model: 'qwen2.5:32b', hint: "For Ollama, use any non-empty value (e.g., 'ollama')" },
  vllm:     { url: 'http://localhost:8000/v1', model: 'Qwen/Qwen2.5-32B-Instruct', hint: "For vLLM, use any non-empty value (e.g., 'vllm')" },
  openai:   { url: 'https://api.openai.com/v1', model: 'gpt-4o', hint: 'Enter your OpenAI API key (sk-...)' },
  gemini:   { url: 'https://generativelanguage.googleapis.com/v1beta/openai/', model: 'gemini-2.0-flash', hint: 'Enter your Google AI API key (AIza...)' },
  anthropic:{ url: 'https://api.anthropic.com/v1', model: 'claude-3-5-sonnet-20241022', hint: 'Requires an OpenAI-compatible proxy for Anthropic' },
  azure:    { url: 'https://{resource}.openai.azure.com/openai/deployments/{deploy}/v1', model: 'gpt-4o', hint: 'Enter your Azure OpenAI API key' },
  groq:     { url: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile', hint: 'Enter your Groq API key (gsk-...)' },
  together: { url: 'https://api.together.xyz/v1', model: 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo', hint: 'Enter your Together AI API key' },
  custom:   { url: '', model: '', hint: 'Enter API key for your custom OpenAI-compatible endpoint' },
};

function onProviderChange() {
  const provider = document.getElementById('setting-llm-provider').value;
  const defaults = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.custom;
  document.getElementById('setting-llm-baseurl').placeholder = defaults.url;
  document.getElementById('setting-llm-model').placeholder = defaults.model;
  document.getElementById('apikey-hint').textContent = defaults.hint;
}

async function loadSettings() {
  try {
    const s = await window.moriesApi.get('settings');
    if (!s) return;
    
    if (s.llm) {
      const sel = document.getElementById('setting-llm-provider');
      if(sel) {
          for (let opt of sel.options) { if (opt.value === s.llm.provider) opt.selected = true; }
      }
      const baseUrlEl = document.getElementById('setting-llm-baseurl');
      if(baseUrlEl) baseUrlEl.value = s.llm.base_url || '';
      const modelEl = document.getElementById('setting-llm-model');
      if(modelEl) modelEl.value = s.llm.model || '';
      
      const apkEl = document.getElementById('setting-llm-apikey');
      if(apkEl) apkEl.placeholder = s.llm.api_key_set ? '••••••••' : 'sk-...';
      
      const numSel = document.getElementById('setting-llm-numctx');
      if(numSel) {
          for (let opt of numSel.options) { if (opt.value === String(s.llm.num_ctx)) opt.selected = true; }
      }
    }
    if (s.embedding) {
      const embSel = document.getElementById('setting-emb-provider');
      if(embSel) {
          for (let opt of embSel.options) { if (opt.value === s.embedding.provider) opt.selected = true; }
      }
      const embUrlEl = document.getElementById('setting-emb-baseurl');
      if(embUrlEl) embUrlEl.value = s.embedding.base_url || '';
      const embModelEl = document.getElementById('setting-emb-model');
      if(embModelEl) embModelEl.value = s.embedding.model || '';
    }
    if(document.getElementById('setting-llm-provider')) {
        onProviderChange();
    }
  } catch(e) { /* backend not available */ }
}

async function saveSettings() {
  const btn = document.getElementById('btn-save-settings');
  const resultDiv = document.getElementById('save-result');
  btn.textContent = '⏳ Saving...';

  const payload = {
    llm: {
      provider: document.getElementById('setting-llm-provider').value,
      base_url: document.getElementById('setting-llm-baseurl').value || undefined,
      model: document.getElementById('setting-llm-model').value || undefined,
      num_ctx: document.getElementById('setting-llm-numctx').value,
    },
    embedding: {
      provider: document.getElementById('setting-emb-provider').value,
      base_url: document.getElementById('setting-emb-baseurl').value || undefined,
      model: document.getElementById('setting-emb-model').value || undefined,
    },
  };
  const apikey = document.getElementById('setting-llm-apikey').value;
  if (apikey) payload.llm.api_key = apikey;

  try {
    const data = await window.moriesApi.put('settings', payload);
    resultDiv.style.display = 'block';
    resultDiv.style.background = 'rgba(34,197,94,0.12)';
    resultDiv.style.color = 'var(--accent-green)';
    resultDiv.textContent = `✅ ${data.message}`;
    document.getElementById('setting-llm-apikey').value = '';
    setTimeout(() => resultDiv.style.display = 'none', 4000);
  } catch(e) {
    resultDiv.style.display = 'block';
    resultDiv.style.background = 'rgba(239,68,68,0.12)';
    resultDiv.style.color = 'var(--accent-red)';
    resultDiv.textContent = `❌ Save failed: ${e.message}`;
  }
  btn.textContent = '💾 Save All Settings';
}

async function testLLM() {
  const btn = document.getElementById('btn-test-llm');
  const resultDiv = document.getElementById('llm-test-result');
  btn.textContent = '⏳ Testing...';
  resultDiv.style.display = 'block';
  resultDiv.style.background = 'rgba(74,125,255,0.08)';
  resultDiv.style.color = 'var(--text-secondary)';
  resultDiv.textContent = 'Connecting to LLM...';

  const payload = {};
  const urlVal = document.getElementById('setting-llm-baseurl').value;
  const modelVal = document.getElementById('setting-llm-model').value;
  const keyVal = document.getElementById('setting-llm-apikey').value;
  if (urlVal) payload.base_url = urlVal;
  if (modelVal) payload.model = modelVal;
  if (keyVal) payload.api_key = keyVal;

  try {
    const data = await window.moriesApi.post('settings/test/llm', payload);
    if (data.status === 'connected') {
      resultDiv.style.background = 'rgba(34,197,94,0.12)';
      resultDiv.style.color = 'var(--accent-green)';
      resultDiv.textContent = `✅ Connected — ${data.model} responded "${data.response}" in ${data.latency_ms}ms`;
    } else {
      resultDiv.style.background = 'rgba(239,68,68,0.12)';
      resultDiv.style.color = 'var(--accent-red)';
      resultDiv.textContent = `❌ ${data.error}`;
    }
  } catch(e) {
    resultDiv.style.background = 'rgba(239,68,68,0.12)';
    resultDiv.style.color = 'var(--accent-red)';
    resultDiv.textContent = `❌ Connection failed: ${e.message}`;
  }
  btn.textContent = '⚡ Test LLM Connection';
  setTimeout(() => resultDiv.style.display = 'none', 8000);
}

async function testEmbedding() {
  const btn = document.getElementById('btn-test-emb');
  const resultDiv = document.getElementById('emb-test-result');
  btn.textContent = '⏳ Testing...';
  resultDiv.style.display = 'block';
  resultDiv.style.background = 'rgba(139,92,246,0.08)';
  resultDiv.style.color = 'var(--text-secondary)';
  resultDiv.textContent = 'Generating test embedding...';

  const payload = {
    provider: document.getElementById('setting-emb-provider').value,
  };
  const urlVal = document.getElementById('setting-emb-baseurl').value;
  const modelVal = document.getElementById('setting-emb-model').value;
  if (urlVal) payload.base_url = urlVal;
  if (modelVal) payload.model = modelVal;

  try {
    const data = await window.moriesApi.post('settings/test/embedding', payload);
    if (data.status === 'connected') {
      resultDiv.style.background = 'rgba(34,197,94,0.12)';
      resultDiv.style.color = 'var(--accent-green)';
      resultDiv.textContent = `✅ Connected — ${data.model} generated ${data.dimensions}-dim vector in ${data.latency_ms}ms`;
    } else {
      resultDiv.style.background = 'rgba(239,68,68,0.12)';
      resultDiv.style.color = 'var(--accent-red)';
      resultDiv.textContent = `❌ ${data.error}`;
    }
  } catch(e) {
    resultDiv.style.background = 'rgba(239,68,68,0.12)';
    resultDiv.style.color = 'var(--accent-red)';
    resultDiv.textContent = `❌ Connection failed: ${e.message}`;
  }
  btn.textContent = '🧬 Test Embedding';
  setTimeout(() => resultDiv.style.display = 'none', 8000);
}

window.addEventListener('DOMContentLoaded', () => {
    loadSettings();
});

window.onProviderChange = onProviderChange;
window.saveSettings = saveSettings;
window.testLLM = testLLM;
window.testEmbedding = testEmbedding;
window.loadSettings = loadSettings;
