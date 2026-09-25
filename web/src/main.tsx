import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './i18n'
import App from './App.tsx'
import type { DevTool } from './dev/DevApp.tsx'

/**
 * `?curate` opens the name-list curation review, `?areas` the dialect-area
 * review (see src/dev/), in place of the public map; `?curate` wins if both
 * are set. Dev only: `import.meta.env.DEV` is a build-time constant, so a
 * production build drops the lazy import below along with both tools, and
 * there the parameters do nothing.
 */
function devTool(): DevTool | null {
  if (!import.meta.env.DEV) return null
  const params = new URLSearchParams(window.location.search)
  if (params.has('curate')) return 'curate'
  if (params.has('areas')) return 'areas'
  return null
}

const tool = devTool()
// `import.meta.env.DEV &&` again right here, where the bundler can see it
// fold to `false` and drop the import without following devTool().
const DevApp = import.meta.env.DEV && tool ? lazy(() => import('./dev/DevApp.tsx')) : null

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {DevApp && tool ? (
      <Suspense>
        <DevApp tool={tool} />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
)
