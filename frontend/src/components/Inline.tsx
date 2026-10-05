import { useState } from 'react'
import { copyText, shorten } from '../lib/format'

export function CopyValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <span className="copy-value">
      <code title={value}>{shorten(value, 12, 10)}</code>
      <button type="button" className="text-button" onClick={() => void copyText(value).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1400) })}>
        {copied ? 'Copied' : 'Copy'}
      </button>
    </span>
  )
}

export function LoadingBlock({ children = 'Loading…' }: { children?: React.ReactNode }) {
  return <div className="loading-block"><span className="spinner" />{children}</div>
}

export function ErrorNotice({ title = 'Something went wrong', children }: { title?: string; children: React.ReactNode }) {
  return <div className="notice notice-error" role="alert"><strong>{title}</strong><p>{children}</p></div>
}
