import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

export const characters = (value: string) => Array.from(value).length;
export const dateFormat = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' });

export function Icon({ name, size = 20 }: { name: 'chat' | 'plus' | 'close' | 'person' | 'pin'; size?: number }) {
  const paths = {
    pin: 'M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z M14.5 10a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0Z',
    chat: 'M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.4-3.2A7.5 7.5 0 1 1 20 11.5Z M9 11.5h.1 m3.4 0h.1 m3.4 0h.1',
    plus: 'M12 5v14M5 12h14',
    close: 'm6 6 12 12M18 6 6 18',
    person: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  };
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d={paths[name]} />
  </svg>;
}

export function Meta({ post }: { post: { nickname: string; created_at: string } }) {
  return <div className="meta">
    <span className="avatar" aria-hidden="true">{Array.from(post.nickname)[0]}</span>
    <span className="author">{post.nickname}</span>
    <time dateTime={post.created_at}>{dateFormat.format(new Date(post.created_at))}</time>
  </div>;
}

export function Modal({ title, close, busy = false, children }: {
  title: string; close: () => void; busy?: boolean; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  return <dialog ref={ref} aria-labelledby="modal-title" onCancel={(event) => {
    event.preventDefault();
    if (!busy) close();
  }}>
    <div className="section-head">
      <h2 id="modal-title">{title}</h2>
      <button type="button" className="icon-button" aria-label="关闭" disabled={busy} onClick={close}>
        <Icon name="close" />
      </button>
    </div>
    {children}
  </dialog>;
}

export function Field({ label, limit, value, onChange, multiline = false }: {
  label: string; limit: number; value: string; onChange: (value: string) => void; multiline?: boolean;
}) {
  const count = characters(value);
  const props = {
    value, required: true, 'aria-invalid': count > limit,
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(event.target.value),
  };
  return <label className="field">
    <span>{label}</span>
    {multiline ? <textarea {...props} rows={4} /> : <input {...props} />}
    <small className={count > limit ? 'error' : ''}>{count} / {limit}</small>
  </label>;
}
