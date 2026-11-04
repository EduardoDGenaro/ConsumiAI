import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight, BookOpenText, Check, ChevronDown, ChevronRight, Clock, Copy, Eraser, ExternalLink, FileText, Info, Lightbulb, LoaderCircle, Menu, MessageSquare, Mic, Paperclip, Plus, RotateCcw, Scale, ShieldCheck, Square, Trash2, User, X, type LucideIcon } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import logo from './assets/brand/consumiai.png';
import { consultarComProgresso } from './api';

type AnswerStatus = 'fundamentada' | 'esclarecimento' | 'evidencia_insuficiente' | 'fora_escopo';
type QuickAction = 'orientacao' | 'reclamacao' | 'prazo' | 'procon';
type Message = { id: string; role: 'user' | 'assistant'; content: string; simpleContent?: string; detailedContent?: string; draftContent?: string; action?: QuickAction; context?: string; articles?: string[]; pages?: number[]; quote?: string; example?: boolean; status?: AnswerStatus; interpretation?: string; basis?: 'direta' | 'interpretacao' | 'nao_aplicavel'; limitations?: string[]; retrievalMode?: string };
type Conversation = { id: string; title: string; messages: Message[] };
type Status = { ready: boolean; detail: string; edition: string; retrieval_mode?: string };
type PendingRequest = { conversationId: string; question: string; history: { role: string; content: string }[]; action: QuickAction; caseContext: string };
type Attachment = { name: string; text: string };
type SpeechResult = { results: { transcript: string }[][] };
type SpeechRecognition = { lang: string; continuous: boolean; interimResults: boolean; onresult: ((event: SpeechResult) => void) | null; onerror: (() => void) | null; onend: (() => void) | null; start: () => void; stop: () => void };
type SpeechWindow = Window & { SpeechRecognition?: new () => SpeechRecognition; webkitSpeechRecognition?: new () => SpeechRecognition };

const exampleQuestion = 'Comprei um celular pela internet e ele chegou com defeito. A loja quer que eu pague o frete de devolucao. Isso esta correto?';
const exampleSimpleAnswer = `**Voce nao deve pagar esse frete.** Se o celular chegou com defeito, a loja ou o fabricante deve cuidar dos custos para resolver o problema.

Peca a loja um **codigo de devolucao gratuito**. Com ele, voce pode enviar o celular pelos Correios sem pagar. Guarde a conversa com a loja e o comprovante de envio.

Se recebeu uma compra pela internet ha ate 7 dias, voce tambem pode desistir dela e pedir a devolucao do dinheiro.`;
const exampleAnswer = `**Nao, a loja esta incorreta!** O consumidor nao deve pagar o frete para devolucao de produto com defeito.

Segundo o **Codigo de Defesa do Consumidor (CDC):**

1. **Responsabilidade do Fornecedor (Art. 18):** Em caso de produto com defeito (vicio), os custos necessarios de reparo, substituicao e transporte, como o frete, devem ser arcados pela loja ou fabricante. Voce nao deve ter nenhum onus.
2. **Direito de Devolucao (Art. 49):** Se estiver dentro de 7 dias do recebimento de uma compra pela internet, o direito de arrependimento tambem assegura a devolucao sem custos.

**O que fazer agora?**

Exija da loja um **Codigo de Logistica Reversa** para postar o produto nos Correios sem custo.

Posso ajudar voce a gerar um texto de reclamacao formal para enviar ao suporte deles?`;
const initialConversations: Conversation[] = [
  { id: 'example', title: 'Garantia de celular', messages: [
    { id: 'example-user', role: 'user', content: exampleQuestion, example: true },
    { id: 'example-answer', role: 'assistant', content: exampleAnswer, simpleContent: exampleSimpleAnswer, detailedContent: exampleAnswer, example: true },
  ] },
  ...['Voo cancelado', 'Atraso na entrega', 'Cobranca indevida'].map((title, index) => ({ id: `topic-${index}`, title, messages: [] })),
];

function readHistory(): Conversation[] {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem('consumiai-history') || 'null');
    if (Array.isArray(saved) && saved.length && saved.every(item => typeof item.id === 'string' && typeof item.title === 'string' && Array.isArray(item.messages) && item.messages.every((message: Message) => typeof message.id === 'string' && ['user', 'assistant'].includes(message.role) && typeof message.content === 'string'))) return saved;
  } catch {}
  return initialConversations;
}

function BotAvatar({ small = false }: { small?: boolean }) {
  return <div className={`bot-avatar ${small ? 'small' : ''}`} aria-hidden="true"><img src={logo} alt="" width={47} height={47} /></div>;
}

function Sidebar({ conversations, active, onSelect, onNew, onDelete, onClear, busy, open, onClose, edition }: {
  conversations: Conversation[]; active: string; onSelect: (id: string) => void; onNew: () => void; onDelete: () => void; onClear: () => void; busy: boolean; open: boolean; onClose: () => void; edition: string;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const elements = [...document.querySelectorAll<HTMLElement>('.sidebar button')].filter(element => element.getClientRects().length);
        const first = elements[0]; const last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [open, onClose]);
  return <>
    {open && <button className="sidebar-backdrop" onClick={onClose} aria-label="Fechar menu" />}
    <aside id="sidebar" className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Conversas">
      <div className="brand"><img className="brand-logo" src={logo} alt="" width={38} height={38} /><span>Consumi<span className="text-emerald-400">AI</span></span><button ref={closeRef} className="icon-button mobile-close" onClick={onClose} aria-label="Fechar menu"><X size={20} /></button></div>
      <button className="new-chat" onClick={onNew}><Plus size={18} />Nova Duvida</button>
      <div className="history-label">Historico <span>{conversations.length.toString().padStart(2, '0')}</span><button className="icon-button" onClick={onClear} disabled={busy} title="Apagar todo o historico" aria-label="Apagar todo o historico"><Eraser size={15} /></button></div>
      <nav className="history-list">
        {conversations.map(conversation => <button key={conversation.id} className={`history-item ${active === conversation.id ? 'active' : ''}`} aria-current={active === conversation.id ? 'page' : undefined} onClick={() => onSelect(conversation.id)}><MessageSquare size={17} /><span>{conversation.title}</span>{active === conversation.id && <ChevronRight size={14} />}</button>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="privacy-note"><ShieldCheck size={17} /><span>Seus direitos em boas maos.</span></div>
        <div className="profile"><div className="user-avatar"><User size={20} /></div><div><strong>Meu espaco</strong><span>Historico neste navegador</span></div><button className="icon-button" onClick={onDelete} title="Excluir conversa atual" aria-label="Excluir conversa atual"><Trash2 size={16} /></button></div>
        <div className="edition-badge"><span className="status-dot" />{edition}<ShieldCheck size={14} /></div>
      </div>
    </aside>
  </>;
}

function AnswerSources({ message }: { message: Message }) {
  if (message.example || (!message.articles?.length && !message.pages?.length && !message.quote && !message.status)) return null;
  const hasSources = !!message.articles?.length || !!message.pages?.length || !!message.quote;
  return <details className="answer-detailed answer-sources">
    <summary><FileText size={17} aria-hidden="true" /><span>Fontes utilizadas</span><ChevronDown className="answer-chevron" size={16} aria-hidden="true" /></summary>
    <div className="answer-technical-text">
      {hasSources ? <>
        <p className="source-edition">Codigo de Defesa do Consumidor e decretos complementares | PROCON-SP 2025</p>
        <div className="citations">{message.articles?.map(article => <span key={article}><Scale size={12} />{article}</span>)}{message.pages?.map(page => <a key={page} href={`/api/sources/cdc.pdf#page=${page}`} target="_blank" rel="noopener noreferrer" aria-label={`Abrir PDF na pagina ${page}`}>Pagina {page}<ExternalLink size={11} /></a>)}</div>
        {message.quote && <blockquote>{message.quote}</blockquote>}
      </> : <p>Nenhuma fonte citada nesta resposta.</p>}
      {message.retrievalMode && <p className="source-edition">Modo de busca: {message.retrievalMode === 'lexical' ? 'por palavras. Busca semantica indisponivel nesta consulta.' : message.retrievalMode === 'hybrid' ? 'hibrida, por palavras e significado.' : 'nao realizada para esta resposta.'}</p>}
    </div>
  </details>;
}

function AnswerNotes({ message }: { message: Message }) {
  return <>
    {!!message.limitations?.length && <details><summary>Limites da analise</summary><ul>{message.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul></details>}
    {message.interpretation && <details><summary>Pergunta interpretada</summary><p>{message.interpretation}</p></details>}
  </>;
}

function ChatMessage({ message }: { message: Message }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(message.draftContent || message.content); setCopied(true); setCopyError(false); }
    catch { setCopyError(true); }
  }
  const assistant = message.role === 'assistant';
  const hasSections = assistant && !!message.simpleContent?.trim() && !!message.detailedContent?.trim();
  const statusLabels: Record<AnswerStatus, string> = { fundamentada: message.basis === 'interpretacao' ? 'Interpretacao fundamentada no CDC' : 'Fundamentado no CDC', esclarecimento: 'Preciso de mais detalhes', evidencia_insuficiente: 'Fundamento insuficiente na busca', fora_escopo: 'Fora do escopo do CDC' };
  const label = message.draftContent ? 'Rascunho para revisar e enviar' : message.example ? 'Exemplo ilustrativo' : message.status ? statusLabels[message.status] : 'Consulta ao documento CDC';
  return <article className={`message-row ${assistant ? 'assistant-row' : 'user-row'}`} aria-label={assistant ? 'Resposta do ConsumiAI' : 'Sua pergunta'}>
    {assistant && <BotAvatar small />}
    <div className="message-content">
      {assistant && <div className="message-author">ConsumiAI <span>{message.example ? 'Conversa de exemplo' : 'Assistente'}</span></div>}
      <div className={`message-bubble ${assistant ? 'assistant-bubble' : 'user-bubble'}`}>
        {message.draftContent ? <>
          <section className="complaint-document" aria-label="Texto de reclamacao">
            <h3><FileText size={17} aria-hidden="true" />Texto de reclamacao</h3>
            <p>{message.draftContent}</p>
          </section>
          <details className="answer-detailed">
            <summary><BookOpenText size={17} aria-hidden="true" /><span>Orientacoes sobre o texto</span><ChevronDown className="answer-chevron" size={16} aria-hidden="true" /></summary>
            <div className="answer-technical-text"><ReactMarkdown>{message.simpleContent || message.detailedContent || 'Revise o relato e preencha os campos entre colchetes antes de enviar.'}</ReactMarkdown><AnswerNotes message={message} /></div>
          </details>
        </> : hasSections ? <>
          <section className="answer-simple" aria-label="Em palavras simples">
            <h3><Lightbulb size={17} aria-hidden="true" />Em palavras simples</h3>
            <ReactMarkdown>{message.simpleContent}</ReactMarkdown>
          </section>
          <details className="answer-detailed">
            <summary><BookOpenText size={17} aria-hidden="true" /><span>Analise detalhada</span><ChevronDown className="answer-chevron" size={16} aria-hidden="true" /></summary>
            <div className="answer-technical-text"><ReactMarkdown>{message.detailedContent}</ReactMarkdown><AnswerNotes message={message} /></div>
          </details>
        </> : <><ReactMarkdown>{message.content}</ReactMarkdown><AnswerNotes message={message} /></>}
        {assistant && <AnswerSources message={message} />}
      </div>
      {assistant && <div className="message-meta"><span>{message.status && message.status !== 'fundamentada' ? <Info size={13} /> : <ShieldCheck size={13} />}{label}</span><button onClick={copy} className="copy-button" title={message.draftContent ? 'Copiar reclamacao' : 'Copiar resposta'} aria-label={message.draftContent ? 'Copiar reclamacao' : 'Copiar resposta'}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copiado' : copyError ? 'Falha ao copiar' : message.draftContent ? 'Copiar reclamacao' : 'Copiar'}</button></div>}
    </div>
  </article>;
}

function SuggestionChip({ icon: Icon, children, onClick, disabled }: { icon: LucideIcon; children: string; onClick: () => void; disabled: boolean }) {
  return <button className="suggestion-chip" onClick={onClick} disabled={disabled}><Icon size={16} strokeWidth={1.7} /><span>{children}</span><ChevronRight size={13} /></button>;
}

function ChatInput({ onSend, busy, onError }: { onSend: (text: string, attachment?: Attachment) => Promise<void>; busy: boolean; onError: (message: string) => void }) {
  const [draft, setDraft] = useState('');
  const [attachment, setAttachment] = useState<Attachment>();
  const [uploading, setUploading] = useState(false);
  const [listening, setListening] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const speechRef = useRef<SpeechRecognition | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => () => speechRef.current?.stop(), []);
  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!draft.trim() || busy || uploading) return;
    speechRef.current?.stop();
    const text = draft.trim(); const file = attachment;
    setDraft(''); setAttachment(undefined);
    await onSend(text, file);
    inputRef.current?.focus();
  }
  async function attach(file?: File) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { onError('O anexo deve ter no maximo 5 MB.'); return; }
    setUploading(true);
    try {
      const response = await fetch('/api/attachment', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Filename': encodeURIComponent(file.name), 'X-Privacy-Notice': 'displayed' }, body: file });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Nao foi possivel ler o anexo.');
      setAttachment({ name: file.name, text: result.text });
    } catch (error) { onError(error instanceof Error ? error.message : 'Falha no envio do anexo.'); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ''; }
  }
  function dictate() {
    if (listening) { speechRef.current?.stop(); return; }
    const Speech = (window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition;
    if (!Speech) { onError('Ditado indisponivel neste navegador. Utilize Chrome ou Edge com permissao de microfone.'); return; }
    const recognition = new Speech();
    recognition.lang = 'pt-BR'; recognition.continuous = false; recognition.interimResults = false;
    recognition.onresult = event => setDraft(value => `${value}${value ? ' ' : ''}${event.results[0][0].transcript}`);
    recognition.onerror = () => { setListening(false); onError('Nao foi possivel usar o microfone. Confira a permissao do navegador.'); };
    recognition.onend = () => setListening(false);
    speechRef.current = recognition;
    try { recognition.start(); setListening(true); } catch { onError('Nao foi possivel iniciar o ditado.'); }
  }
  return <div className="composer-wrapper">
    {attachment && <div className="attachment"><FileText size={14} /><span>{attachment.name}</span><button className="icon-button" aria-label="Remover anexo" onClick={() => setAttachment(undefined)}><X size={14} /></button></div>}
    <form className="composer" onSubmit={submit}>
      <label className="sr-only" htmlFor="question">Sua duvida sobre o CDC</label>
      <textarea id="question" ref={inputRef} rows={1} maxLength={8000} value={draft} onChange={event => setDraft(event.target.value)} placeholder="Digite sua duvida sobre o CDC aqui..." onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void submit(); } }} />
      <div className="composer-actions">
        <input ref={fileRef} type="file" accept=".pdf,.txt" hidden onChange={event => void attach(event.target.files?.[0])} />
        <button type="button" className="input-action attachment-button" title="Anexar PDF ou texto" aria-label="Anexar PDF ou texto" disabled={busy || uploading} onClick={() => fileRef.current?.click()}>{uploading ? <LoaderCircle size={20} className="animate-spin" /> : <Paperclip size={20} />}</button>
        <button type="button" className={`input-action ${listening ? 'recording' : ''}`} title={listening ? 'Parar ditado' : 'Ditar pergunta'} aria-label={listening ? 'Parar ditado' : 'Ditar pergunta'} aria-pressed={listening} disabled={busy} onClick={dictate}>{listening ? <Square size={18} /> : <Mic size={20} />}</button>
        <span className="composer-divider" />
        <button className="send-button" title="Enviar pergunta" aria-label="Enviar pergunta" disabled={!draft.trim() || busy || uploading}>{busy ? <LoaderCircle size={21} className="animate-spin" /> : <ArrowRight size={22} />}</button>
      </div>
    </form>
    {listening && <p className="listening-note" role="status">Ouvindo...</p>}
    <aside className="privacy-notice" aria-label="Aviso de privacidade e responsabilidade"><Info size={12} aria-hidden="true" /><p>Dados ao Google; evite dados sensiveis. Nao substitui orientacao juridica.</p></aside>
  </div>;
}

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>(readHistory);
  const [active, setActive] = useState(() => conversations[0].id);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [status, setStatus] = useState<Status>({ ready: false, detail: 'Verificando conexao', edition: 'Base CDC' });
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState('indexing');
  const [failedRequest, setFailedRequest] = useState<PendingRequest>();
  const [error, setError] = useState('');
  const [storageError, setStorageError] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const requestRef = useRef(false);
  const conversation = conversations.find(item => item.id === active) || conversations[0];
  const messages = conversation.messages;
  useEffect(() => {
    try { localStorage.setItem('consumiai-history', JSON.stringify(conversations)); setStorageError(false); }
    catch { setStorageError(true); }
  }, [conversations]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'instant' }); }, [active, messages.length, busy]);
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/status', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error();
      setStatus(await response.json());
    }).catch(() => { if (!controller.signal.aborted) setStatus({ ready: false, detail: 'Servidor indisponivel', edition: 'Base CDC' }); });
    return () => controller.abort();
  }, []);
  function closeSidebar() { setSidebarOpen(false); menuRef.current?.focus(); }
  function clearHistory() {
    if (!window.confirm('Apagar todas as conversas deste navegador? Isso nao exclui dados ja enviados ao provedor de IA.')) return;
    const item = { id: crypto.randomUUID(), title: 'Nova duvida', messages: [] };
    try { localStorage.removeItem('consumiai-history'); } catch {}
    setConversations([item]); setActive(item.id); setFailedRequest(undefined); setError(''); closeSidebar();
  }
  function newChat() {
    const item = { id: crypto.randomUUID(), title: 'Nova duvida', messages: [] };
    setConversations(previous => [item, ...previous]); setActive(item.id); setError(''); closeSidebar();
  }
  function deleteChat() {
    if (!window.confirm('Excluir esta conversa do historico deste navegador?')) return;
    const remaining = conversations.filter(item => item.id !== active);
    if (!remaining.length) { const item = { id: crypto.randomUUID(), title: 'Nova duvida', messages: [] }; remaining.push(item); }
    setConversations(remaining); setActive(remaining[0].id); setError('');
  }
  async function performQuery(pending: PendingRequest) {
    if (requestRef.current) return;
    requestRef.current = true; setBusy(true); setError(''); setStage('indexing'); setFailedRequest(undefined);
    try {
      const data = await consultarComProgresso({ question: pending.question, history: pending.history, action: pending.action, case_context: pending.caseContext }, setStage);
      const answer: Message = { id: crypto.randomUUID(), role: 'assistant', content: data.content, simpleContent: data.simple_content, detailedContent: data.detailed_content, draftContent: data.complaint_text, articles: data.articles, pages: data.pages, quote: data.quote, status: data.status, interpretation: data.interpretation, basis: data.basis, limitations: data.limitations, retrievalMode: data.diagnostics?.fallback ? 'lexical' : data.diagnostics?.retrieval_mode };
      setConversations(previous => previous.map(item => item.id === pending.conversationId ? { ...item, messages: [...item.messages, answer] } : item));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Nao foi possivel conectar ao assistente.');
      setFailedRequest(pending);
    } finally { setBusy(false); requestRef.current = false; }
  }
  async function send(text: string, attachment?: Attachment, action: QuickAction = 'orientacao') {
    if (requestRef.current) return;
    const conversationId = conversation.id;
    const question = attachment ? `${text}\n\nDocumento anexado (${attachment.name}):\n${attachment.text}` : text;
    const userMessage: Message = { id: crypto.randomUUID(), role: 'user', content: attachment ? `${text}\n\nAnexo: ${attachment.name}` : text, context: question, action };
    setConversations(previous => previous.map(item => item.id === conversationId ? { ...item, title: item.messages.length ? item.title : text.slice(0, 42), messages: [...item.messages, userMessage] } : item));
    const caseContext = action === 'orientacao' ? '' : messages.filter(item => item.role === 'user' && (!item.action || item.action === 'orientacao')).slice(-2).map(item => item.context || item.content).join('\n\n').slice(-12000);
    await performQuery({ conversationId, question, history: messages.slice(-4).map(item => ({ role: item.role, content: item.context || item.content })), action, caseContext });
  }
  const suggestions: { icon: LucideIcon; label: string; question: string; action: QuickAction }[] = [
    { icon: FileText, label: 'Gerar texto de reclamacao', question: 'Escreva a mensagem de reclamacao que vou enviar a empresa sobre o caso relatado. Quero o texto pronto, em primeira pessoa, com campos entre colchetes para os dados que faltam.', action: 'reclamacao' },
    { icon: Clock, label: 'Qual o prazo para resolver?', question: 'Qual prazo se aplica ao meu caso, a partir de quando ele e contado e o que posso fazer se nao for cumprido? Diferencie os prazos que forem relevantes.', action: 'prazo' },
    { icon: Scale, label: 'Como reclamar no PROCON?', question: 'Organize os passos para reclamar no PROCON sobre meu caso, os comprovantes que posso reunir e o que depende do meu estado ou municipio. Nao invente canais de atendimento.', action: 'procon' },
  ];
  return <div className="app-shell">
    <Sidebar conversations={conversations} active={active} onSelect={id => { setActive(id); setError(''); closeSidebar(); }} onNew={newChat} onDelete={deleteChat} onClear={clearHistory} busy={busy} open={sidebarOpen} onClose={closeSidebar} edition={status.edition} />
    <main className="chat-panel" inert={sidebarOpen ? true : undefined}>
      <header className="chat-header">
        <button ref={menuRef} className="icon-button menu-button" aria-label="Abrir historico" aria-controls="sidebar" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(true)}><Menu size={22} /></button>
        <BotAvatar />
        <div className="header-title"><h1>ConsumiAI</h1><p>Assistente de Direito do Consumidor <span className={`connection ${status.ready ? 'online' : ''}`} title={status.detail}><span className="status-dot" />{status.ready ? 'Online' : status.detail}</span></p></div>
        <div className="header-seal"><ShieldCheck size={17} /><span>Informacao que protege.</span></div>
      </header>
      <div className="chat-scroll" role="region" aria-label="Mensagens da conversa" tabIndex={0}>
        <div className="chat-thread">
          <div className="conversation-date"><span />{conversation.id === 'example' ? 'Seus direitos, com clareza' : 'Sua conversa com o ConsumiAI'}<span /></div>
          {!messages.length && <div className="empty-state"><BotAvatar /><h2>Como posso ajudar voce?</h2><p>{conversation.title === 'Nova duvida' ? 'Conte o que aconteceu. Vamos entender seus direitos.' : `Vamos conversar sobre ${conversation.title.toLocaleLowerCase('pt-BR')}.`}</p><div className="empty-topics">{['Produto com defeito', 'Compra pela internet', 'Cobranca indevida'].map(topic => <button key={topic} onClick={() => void send(`Quais sao meus direitos em caso de ${topic.toLowerCase()}?`)} disabled={busy}>{topic}<ArrowRight size={15} /></button>)}</div></div>}
          {messages.map(message => <ChatMessage key={message.id} message={message} />)}
          {busy && <div className="pending-message" role="status" aria-live="polite"><BotAvatar small /><LoaderCircle size={16} className="animate-spin" /><span>{{ indexing: 'Preparando a base do CDC...', understanding: 'Entendendo sua duvida...', retrieving: 'Buscando fundamentos...', selecting: 'Conferindo os trechos relevantes...', preparing: 'Preparando as duas respostas...' }[stage] || 'Consultando o CDC...'}</span></div>}
          {!!messages.length && messages.at(-1)?.role === 'assistant' && (!messages.at(-1)?.status || messages.at(-1)?.status === 'fundamentada') && <div className="suggestions">{suggestions.filter(item => !messages.at(-1)?.draftContent || item.action !== 'reclamacao').map(item => <SuggestionChip key={item.label} icon={item.icon} disabled={busy} onClick={() => void send(item.question, undefined, item.action)}>{item.label}</SuggestionChip>)}</div>}
          <div ref={bottomRef} />
        </div>
      </div>
      <footer className="chat-footer">
        {(error || storageError) && <div className="error-notice" role="alert"><Info size={16} /><span>{error || 'Armazenamento local indisponivel. O historico sera mantido apenas nesta sessao.'}</span>{error && failedRequest?.conversationId === active && <button className="retry-button" disabled={busy} onClick={() => void performQuery(failedRequest)}><RotateCcw size={14} />Tentar novamente</button>}{error && <button className="icon-button" aria-label="Fechar aviso" onClick={() => setError('')}><X size={16} /></button>}</div>}
        <ChatInput onSend={send} busy={busy} onError={setError} />
      </footer>
    </main>
  </div>;
}