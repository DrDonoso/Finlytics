/**
 * Cliente de consultas compartido.
 *
 * Se extrae del punto de montaje para que los tests puedan crear su propia
 * instancia con la misma configuración sin arrastrar el árbol de la aplicación.
 */
import { QueryClient } from '@tanstack/react-query'

/**
 * Los datos financieros no cambian solos: sólo se mueven cuando el usuario
 * importa un extracto o edita algo, y en esos casos la mutación invalida lo que
 * corresponda. Por eso se desactiva el refetch automático al recuperar el foco,
 * que en una aplicación así sólo produce peticiones que nadie ha pedido.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        // Un 401 lo gestiona el manejador global del cliente HTTP; reintentarlo
        // sólo retrasa la redirección al login.
        retry: (failureCount, error) => {
          if (error instanceof Error && error.message.includes('401')) return false
          return failureCount < 2
        },
      },
    },
  })
}

export const queryClient = createQueryClient()
