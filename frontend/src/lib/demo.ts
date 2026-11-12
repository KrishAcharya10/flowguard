// Presenter state for the demo guide: which use case is active and which steps are ticked.
// Kept per browser tab (sessionStorage), so the coordinator tab drives the presentation.
import { useEffect, useState } from 'react'
import type { components } from '../api/schema'

export type UseCase = components['schemas']['DemoUseCase']
export type DemoGuide = components['schemas']['DemoGuideOut']
export interface DemoState { code: string; done: number[]; collapsed: boolean }

const KEY = 'flowguard.demo'
const listeners = new Set<() => void>()

export function getDemo(): DemoState | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setDemo(s: DemoState | null) {
  try {
    if (s) sessionStorage.setItem(KEY, JSON.stringify(s))
    else sessionStorage.removeItem(KEY)
  } catch { /* storage unavailable: panel just won't persist */ }
  listeners.forEach((l) => l())
}

export function useDemo(): DemoState | null {
  const [s, set] = useState<DemoState | null>(getDemo())
  useEffect(() => {
    const l = () => set(getDemo())
    listeners.add(l)
    return () => { listeners.delete(l) }
  }, [])
  return s
}

export function toggleStep(i: number) {
  const s = getDemo()
  if (!s) return
  setDemo({ ...s, done: s.done.includes(i) ? s.done.filter((x) => x !== i) : [...s.done, i] })
}

export const TAB_STYLE: Record<string, string> = {
  Coordinator: 'bg-navy-800 text-white',
  Customer: 'bg-green-700 text-white',
  Driver: 'bg-amber-600 text-white',
  'Relief driver': 'bg-amber-600 text-white',
}
