import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router'
import { isUnauthorized } from './api.ts'
import { AuthGate } from './auth/AuthGate.tsx'
import { loggedOut } from './auth/queries.ts'
import { AuthorizePage } from './oauth/AuthorizePage.tsx'
import './index.css'
import App from './App.tsx'

/** Any 401 means the session is gone (expired, logged out elsewhere, new password): back to login. */
function onError(error: Error) {
  if (isUnauthorized(error)) loggedOut(queryClient)
}

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
  defaultOptions: {
    queries: { staleTime: 30_000, retry: (failures, error) => failures < 1 && !isUnauthorized(error) },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthGate>
          <Routes>
            {/* Full-screen, outside the app's navigation, like the login screen. */}
            <Route path="/oauth/authorize" element={<AuthorizePage />} />
            <Route path="*" element={<App />} />
          </Routes>
        </AuthGate>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
