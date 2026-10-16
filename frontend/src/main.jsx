import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

async function api(path, options) {
  const response = await fetch('/api' + path, options);
  let body = null;
  if (response.status !== 204) {
    try { body = await response.json(); }
    catch { throw new Error('API bağlantısı kurulamadı. Docker servislerinin çalıştığını kontrol edin.'); }
  }
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'İstek tamamlanamadı. Servis bağlantısını kontrol edin.');
  return body;
}

function DeleteChatDialog({ chat, busy, error, onCancel, onConfirm }) {
  const dialog = useRef(), cancel = useRef();
  useEffect(() => {
    if (chat && !dialog.current.open) { dialog.current.showModal(); cancel.current.focus(); }
    else if (!chat && dialog.current.open) dialog.current.close();
  }, [chat]);
  return <dialog ref={dialog} className="delete-dialog" aria-labelledby="delete-chat-title" aria-describedby="delete-chat-description" onCancel={e => { e.preventDefault(); if (!busy) onCancel(); }} onClick={e => { if (e.target === e.currentTarget && !busy) onCancel(); }}>
    <div className="delete-dialog-content">
      <button className="dialog-close" aria-label="Pencereyi kapat" disabled={busy} onClick={onCancel}>×</button>
      <div className="delete-dialog-icon"><svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg></div>
      <div className="dialog-eyebrow">SOHBETİ YÖNET</div>
      <h2 id="delete-chat-title">Bu sohbete veda edelim mi?</h2>
      <div className="delete-chat-preview"><span aria-hidden="true">◌</span><div><strong>{chat?.title}</strong><small>{chat?.message_count || 0} mesaj</small></div></div>
      <p id="delete-chat-description">Sohbet ve içindeki tüm mesajlar kalıcı olarak silinecek. Bu işlem geri alınamaz.</p>
      {error && <p className="dialog-error" role="alert">{error}</p>}
      <div className="dialog-actions"><button ref={cancel} className="dialog-cancel" disabled={busy} onClick={onCancel}>Vazgeç</button><button className="dialog-confirm" disabled={busy} onClick={onConfirm}>{busy ? 'Siliniyor…' : 'Sohbeti sil'}</button></div>
    </div>
  </dialog>;
}

function App() {
  const [docs, setDocs] = useState([]), [selected, setSelected] = useState([]);
  const [status, setStatus] = useState(null), [error, setError] = useState('');
  const [uploading, setUploading] = useState(false), [asking, setAsking] = useState(false);
  const [question, setQuestion] = useState(''), [messages, setMessages] = useState([]);
  const [dragging, setDragging] = useState(false), [deleting, setDeleting] = useState(null);
  const [chats, setChats] = useState([]), [activeId, setActiveId] = useState(null), [loadingChat, setLoadingChat] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState(null), [deleteError, setDeleteError] = useState('');
  const input = useRef(), bottom = useRef(), lastMessage = useRef();
  async function refresh() {
    const loaded = await api('/documents'); setDocs(loaded);
    setSelected(s => s.filter(id => loaded.some(d => d.id === id && d.status === 'ready')));
    return loaded;
  }
  async function refreshChats() { const loaded = await api('/conversations'); setChats(loaded); return loaded; }
  function remember(id) { try { localStorage.setItem('documind.activeChat', id); } catch {} }
  async function openChat(id, available = docs) {
    setLoadingChat(true); setError('');
    try {
      const chat = await api('/conversations/' + id);
      setActiveId(id); remember(id); setMessages(chat.messages); setQuestion('');
      setSelected(chat.document_ids.filter(ident => available.some(d => d.id === ident && d.status === 'ready')));
    } catch (e) { setError(e.message); } finally { setLoadingChat(false); }
  }
  async function newChat() {
    setLoadingChat(true); setError('');
    try {
      const chat = await api('/conversations', { method: 'POST' });
      setActiveId(chat.id); remember(chat.id); setMessages([]); setQuestion(''); await refreshChats();
    } catch (e) { setError(e.message); } finally { setLoadingChat(false); }
  }
  async function deleteChat(chat) {
    if (loadingChat) return;
    setLoadingChat(true); setError(''); setDeleteError('');
    try {
      await api('/conversations/' + chat.id, { method: 'DELETE' });
      setDeleteTarget(null);
      const remaining = await refreshChats();
      if (activeId === chat.id) {
        setActiveId(null); setMessages([]); setQuestion('');
        try { localStorage.removeItem('documind.activeChat'); } catch {}
        if (remaining.length) await openChat(remaining[0].id);
      }
    } catch (e) { setDeleteError(e.message); setError(e.message); } finally { setLoadingChat(false); }
  }
  useEffect(() => {
    (async () => {
      try {
        const loaded = await refresh(); const list = await refreshChats();
        let saved; try { saved = localStorage.getItem('documind.activeChat'); } catch {}
        const id = list.find(c => c.id === saved)?.id || list[0]?.id;
        if (id) await openChat(id, loaded);
      } catch (e) { setError(e.message); } finally { setLoadingChat(false); }
    })();
    const check = () => fetch('/api/health/ready').then(r => r.json()).then(setStatus).catch(() => setStatus({ ready: false }));
    check(); const timer = setInterval(check, 15000); return () => clearInterval(timer);
  }, []);
  const hasPending = docs.some(d => ['queued', 'processing', 'retrying'].includes(d.status));
  useEffect(() => {
    if (!hasPending) return;
    const timer = setInterval(() => refresh().catch(e => setError(e.message)), 2500);
    return () => clearInterval(timer);
  }, [hasPending]);
  useEffect(() => {
    if (messages.at(-1)?.role === 'assistant') lastMessage.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    else if (messages.length || asking) bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, asking]);
  async function upload(files) {
    if (uploading || !files?.length) return;
    setUploading(true); setError('');
    try {
      for (const file of files) {
        if (file.size > 20 * 1024 * 1024) throw new Error('Dosya sınırı 20 MB.');
        const form = new FormData(); form.append('file', file);
        await api('/documents', { method: 'POST', body: form });
        await refresh();
      }
    } catch (e) { setError(e.message); }
    finally { setUploading(false); if (input.current) input.current.value = ''; }
  }
  async function remove(doc) {
    if (!window.confirm(`“${doc.name}” ve indeksini silmek istiyor musunuz?`)) return;
    setDeleting(doc.id); setError('');
    try { await api('/documents/' + doc.id, { method: 'DELETE' }); setSelected(s => s.filter(id => id !== doc.id)); await refresh(); }
    catch (e) { setError(e.message); } finally { setDeleting(null); }
  }
  async function retry(doc) {
    setError('');
    try { await api('/documents/' + doc.id + '/retry', { method: 'POST' }); await refresh(); }
    catch (e) { setError(e.message); }
  }
  async function ask(e) {
    e.preventDefault(); if (!question.trim() || asking || loadingChat) return;
    const text = question.trim(); setQuestion(''); setAsking(true); setError('');
    try {
      let ident = activeId;
      if (!ident) { const chat = await api('/conversations', { method: 'POST' }); ident = chat.id; setActiveId(ident); remember(ident); }
      setMessages(m => [...m, { role: 'user', text }]);
      await api('/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: text, document_ids: selected, conversation_id: ident }) });
      const saved = await api('/conversations/' + ident); setMessages(saved.messages); await refreshChats();
    } catch (e) { setError(e.message); setQuestion(text); setMessages(m => m.at(-1)?.role === 'user' && m.at(-1)?.text === text ? m.slice(0, -1) : m); }
    finally { setAsking(false); }
  }
  return <div className="shell">
    <aside>
      <a className="brand" href="/" aria-label="DocuMind ana sayfa"><span className="brand-mark">d<span>m</span></span>DocuMind<span className="beta">LOCAL</span></a>
      <div className="section-label">KÜTÜPHANE <span>{docs.length.toString().padStart(2, '0')}</span></div>
      <button className={'upload-zone ' + (dragging ? 'dragging' : '')} disabled={uploading} onClick={() => input.current.click()} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); upload(e.dataTransfer.files); }}>
        <span className="upload-icon">{uploading ? '◌' : '↥'}</span><strong>{uploading ? 'Dosya yükleniyor…' : 'Belgelerini buraya bırak'}</strong><span>veya dosya seçmek için tıkla</span><small>PDF, MD, TXT · En fazla 20 MB</small>
      </button>
      <input ref={input} type="file" accept=".pdf,.md,.txt" multiple hidden onChange={e => upload(e.target.files)} />
      <div className="document-list">
        {docs.length === 0 ? <p className="muted empty-library">İlk belgenle başla.<br/>Bilgilerin burada bir araya gelsin.</p> : docs.map(doc => <div className="document" key={doc.id}><input aria-label={doc.name + ' seç'} disabled={doc.status !== 'ready' || asking} type="checkbox" checked={selected.includes(doc.id)} onChange={e => setSelected(s => e.target.checked ? [...s, doc.id] : s.filter(id => id !== doc.id))}/><div><strong title={doc.name}>{doc.name}</strong><small>{doc.status === 'ready' ? `${doc.chunks} metin parçası` : doc.status === 'processing' ? `İşleniyor · %${doc.progress}` : doc.status === 'retrying' ? 'Otomatik yeniden deneniyor' : doc.status === 'failed' ? 'İşlem başarısız' : 'İşlem kuyruğunda'}</small>{doc.error && <small className="document-error">{doc.error}</small>}{doc.status === 'failed' && <button className="retry-button" onClick={() => retry(doc)}>Yeniden dene</button>}</div><button className="icon-button" aria-label={doc.name + ' sil'} disabled={!!deleting || asking || ['queued', 'processing', 'retrying'].includes(doc.status)} onClick={() => remove(doc)}>×</button></div>)}
      </div>
      <div className="section-label chat-heading">SOHBETLER <span>{chats.length}</span></div>
      <nav className="chat-list" aria-label="Sohbet geçmişi">{chats.map(chat => <div className={'chat-row ' + (activeId === chat.id ? 'active' : '')} key={chat.id}><button className="chat-item" disabled={asking || loadingChat} onClick={() => openChat(chat.id)} title={chat.title}><span>◌</span><div><strong>{chat.title}</strong><small>{chat.message_count} mesaj</small></div></button><button className="chat-delete" aria-label={`${chat.title} sohbetini sil`} title="Sohbeti sil" disabled={asking || loadingChat} onClick={() => { setDeleteError(''); setDeleteTarget(chat); }}><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg></button></div>)}{!chats.length && <p className="muted empty-library">Sohbetlerin burada saklanacak.</p>}</nav>
      <div className="privacy"><span>◈</span><div>Bilgilerin sende kalır.<small>Yerel modeller. Buluta gönderim yok.</small></div></div>
    </aside>
    <main>
      <header><div><span className="breadcrumb">Çalışma alanı /</span> Belge asistanı</div><span className={'status ' + (status?.ready ? 'online' : '')}><i/>{status?.ready ? 'Sistem hazır' : status ? 'Kurulum bekleniyor' : 'Bağlantı kontrol ediliyor'}</span></header>
      <div className="toolbar"><span><span className="spark">✧</span> {chats.find(c => c.id === activeId)?.title || 'Belgelerine dayalı yanıtlar'}</span><button disabled={asking || loadingChat} onClick={newChat}>＋ Yeni sohbet</button></div>
      {status && !status.ready && <div className="setup-note">Servisler veya modeller henüz hazır değil. README’deki başlatma ve model indirme adımlarını tamamla.</div>}
      <section className="conversation" aria-label="Sohbet" aria-live="polite">
        {loadingChat && <div className="thinking">Sohbet yükleniyor…</div>}
        {!loadingChat && !messages.length && <div className="welcome"><div className="hero-mark">✳</div><div className="eyebrow">BELGELERİNDEN DAHA FAZLASINI KEŞFET</div><h1>Bilgi sende.<br/><em>Yanıtlar da öyle.</em></h1><p>Belgelerini yükle, sorunu sor.<br/>DocuMind, belgelerinden anlaşılır yanıtlar hazırlasın.</p><div className="suggestions">{['Bu belgenin ana fikirleri neler?', 'Önemli kavramları açıklar mısın?', 'Hangi sonuçlara ulaşılmış?'].map((s, i) => <button key={s} onClick={() => setQuestion(s)}><span>0{i + 1}</span>{s}<b>↗</b></button>)}</div><div className="steps"><span>01 Belge yükle</span><i>—</i><span>02 Sorunu sor</span><i>—</i><span>03 Yanıtı keşfet</span></div></div>}
        {messages.map((m, i) => <article ref={i === messages.length - 1 ? lastMessage : null} key={i} className={'message ' + m.role}><div className="message-label">{m.role === 'user' ? 'SİZ' : '✳ DOCUMIND'}</div><div className="message-text">{m.text}</div></article>)}
        {asking && <div className="thinking">✳ Belgeler inceleniyor, yanıt hazırlanıyor…</div>}<div ref={bottom}/>
      </section>
      <div className="composer-area">{error && <div className="error" role="alert">{error}<button aria-label="Uyarıyı kapat" onClick={() => setError('')}>×</button></div>}<form onSubmit={ask}><label htmlFor="question">{selected.length ? `${selected.length} seçili belge` : 'Tüm hazır belgeler'} <span>⌄</span></label><div className="input-row"><textarea id="question" value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); e.currentTarget.form.requestSubmit(); } }} maxLength={4000} placeholder="Belgelerin hakkında bir soru sor…" rows={2}/><button className="send" aria-label="Soruyu gönder" disabled={asking || loadingChat || !question.trim() || !docs.some(d => d.status === 'ready') || !status?.ready}>↑</button></div></form><div className="composer-footer"><span>◈ Yerel ve özel · Sohbetler kaydedilir</span><span>Yanıtları belgenle karşılaştır. Her soru bağımsız değerlendirilir.</span></div></div>
    </main>
    <DeleteChatDialog chat={deleteTarget} busy={loadingChat} error={deleteError} onCancel={() => setDeleteTarget(null)} onConfirm={() => deleteTarget && deleteChat(deleteTarget)}/>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
