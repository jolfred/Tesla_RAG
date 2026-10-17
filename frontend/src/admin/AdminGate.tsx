import React, { useState } from 'react';
import { useAuth } from '../auth/authContext';
export function AdminLogin(): React.JSX.Element {
  const { loginAdmin } = useAuth(); const [key, setKey] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const submit = async (): Promise<void> => { setBusy(true); setError(''); try { await loginAdmin(key); setKey('') ;} catch { setError('Не удалось войти. Проверьте ключ администратора.') ;} finally { setBusy(false) ;} };
  return <div className="tesla-admin"><div className="ta-main" style={{ margin: '60px auto', maxWidth: 520 }}><div className="ta-card"><h1 className="ta-title">Вход для редактора</h1><p className="ta-muted">Для редакции и администрирования нужен доступ администратора.</p><div className="ta-row"><input className="ta-input" type="password" value={key} onChange={e => setKey(e.target.value)} placeholder="Ключ администратора" onKeyDown={e => { if (e.key === 'Enter') void submit() ;}} /><button className="ta-btn" disabled={busy || !key} onClick={() => void submit()}>Войти</button></div>{error && <p className="ta-error">{error}</p>}</div></div></div>;
}
