/**
 * Shared query client factory.
 *
 * Extracted from the app mount point so tests can create isolated instances
 * without pulling in the full component tree.
 */
import { QueryClient } from '@tanstack/react-query'

/**
 * Financial data doesn't change on its own — only when the user imports a
 * statement or edits a transaction, and in those cases the mutation invalidates
 * the relevant cache. Disabling refetchOnWindowFocus avoids pointless requests.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        // 401 is handled by the global HTTP client handler — retrying just delays the login redirect.
        retry: (failureCount, error) => {
          if (error instanceof Error && error.message.includes('401')) return false
          return failureCount < 2
        },
      },
    },
  })
}

export const queryClient = createQueryClient()
