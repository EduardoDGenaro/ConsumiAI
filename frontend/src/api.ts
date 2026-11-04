export async function consultarComProgresso(payload: unknown, onProgress: (stage: string) => void): Promise<any> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 240_000);
  try {
    const response = await fetch('/api/chat/stream', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Privacy-Notice': 'displayed' },
      body: JSON.stringify(payload), signal: controller.signal,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Nao foi possivel iniciar a consulta.');
    }
    if (!response.body) throw new Error('O navegador nao recebeu o fluxo da resposta.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        if (done && buffer.trim()) lines.push(buffer);
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === 'progress') onProgress(event.stage);
          if (event.type === 'error') throw new Error(event.data?.detail || 'A consulta falhou.');
          if (event.type === 'result') return event.data;
        }
        if (done) throw new Error('A conexao foi interrompida antes da resposta. Tente novamente.');
      }
    } finally { reader.releaseLock(); }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw new Error('A consulta excedeu o tempo de espera. Tente novamente mais tarde.');
    throw error;
  } finally { clearTimeout(timeout); }
}