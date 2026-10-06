import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'
import { initAppTheme } from './state/settings'
import { initTheme } from './ui/theme'

// The hidden component page (docs/ui-redesign-plan.md): open the app with ?ui. It is a separate chunk, so
// it adds nothing to the app's own load.
const UiKit = lazy(() => import('./ui/UiKit'));
const showKit = new URLSearchParams(window.location.search).has('ui');

// Put the theme on the page before anything draws. The kit page shows whatever was saved; the app shows dark until every
// screen has been converted to the tokens (see LIGHT_THEME_READY in state/settings.ts).
if (showKit) initTheme();
else initAppTheme();

const queryClient = new QueryClient();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {showKit ? (
      <Suspense fallback={null}>
        <UiKit />
      </Suspense>
    ) : (
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    )}
  </StrictMode>,
)
